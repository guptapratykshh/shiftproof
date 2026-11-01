"""Voice delivery uses controlled providers. These tests do not claim ASR accuracy."""
import io
import wave
from datetime import datetime, timezone
import pytest
from shiftproof import providers, identity, service
from shiftproof.durable_jobs import run_once
from test_organizations import account
from test_employee_auth import invitation, activate
from test_pilot_scope import team_shift, assign, email_member, create_note, wav


def setup_team():
    owner, org, _ = account()
    team = team_shift(owner, org)
    worker, _ = activate(invitation(owner, org))
    worker_id = worker.get('/auth/session').json()['user']['id']
    supervisor, sid, _ = email_member(owner, org, 'supervisor@example.com', 'supervisor')
    assign(owner, org, team, [worker_id, sid], supervisor_id=sid)
    for c in (owner, worker, supervisor): c.headers['X-Shift-ID'] = team['shift_id']
    return owner, worker, supervisor, org, team, worker_id


def extraction(monkeypatch, claims=(), completion=None):
    def run(text, batch, reserve, context):
        return providers.validate_extraction({'claims':list(claims), 'task_completion':completion},text,context), 'controlled-model-response'
    monkeypatch.setattr(providers,'extract',run)


def version(client, base): return client.get(base+'/workspace').json()['version']


def task_setup(monkeypatch):
    owner, worker, supervisor, org, team, worker_id = setup_team()
    base = '/organizations/'+org
    note = create_note(worker,org,team,transcript='Check labels. Quality pending.')
    extraction(monkeypatch,[{'property':'task','value':'Check labels','excerpt':'Check labels'}, {'property':'quality','value':'pending','excerpt':'Quality pending'}])
    assert worker.post(base+'/notes/'+note+'/process',json={}).status_code == 202
    claims = worker.get(base+'/notes/'+note).json()['claims']
    task = next(c['id'] for c in claims if c['property']=='task')
    assert supervisor.post(base+'/claims/'+task+'/resolve',json={'action':'confirm','reason':'Checked original source','expected_version':version(supervisor,base)}).status_code == 200
    assert supervisor.post(base+'/tasks/'+task,json={'action':'assign','owner_id':worker_id,'reason':'Assigned worker','expected_version':version(supervisor,base)}).status_code == 200
    return owner,worker,supervisor,org,team,task


def task_note(worker,org,team,task,text,key='completion-note'):
    base='/organizations/'+org
    r=worker.post(base+'/notes',json={'batch_id':team['work_item'],'shift_id':team['shift_id'],'task_id':task,'recorded_at':datetime.now(timezone.utc).isoformat(),'idempotency_key':key})
    assert r.status_code == 201,r.text
    note=r.json()['note']['id']
    assert worker.post(base+'/notes/'+note+'/transcript',json={'transcript':text}).status_code==200
    return note


def test_silent_source_retained_without_spending_provider_call(monkeypatch):
    owner,worker,supervisor,org,team,_=setup_team();base='/organizations/'+org
    note=create_note(worker,org,team)
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*16000)
    assert worker.put(base+'/notes/'+note+'/audio',content=buffer.getvalue()).status_code==200
    monkeypatch.setattr(providers,'transcribe',lambda *_:pytest.fail('Silent input must not call Prisma'))
    assert worker.post(base+'/notes/'+note+'/process',json={'transcribe_only':True}).status_code==202
    for c in (worker,supervisor,owner):
        row=c.get(base+'/notes/'+note).json()
        assert row['error_category']=='silent_audio' and row['has_audio']
        assert row['audio_quality']['silent']
        assert row['status']=='failed' and not row['claim_ids']
        assert any(n['id']==note for n in c.get(base+'/workspace').json()['notes'])


def test_durable_audio_to_review_visible_to_all_roles(monkeypatch):
    monkeypatch.setenv('SHIFTPROOF_DURABLE_JOBS','true')
    owner,worker,supervisor,org,team,_=setup_team();base='/organizations/'+org
    repo=identity.tenant_repo({'id':org,'industry':'manufacturing'})
    note=create_note(worker,org,team)
    assert worker.put(base+'/notes/'+note+'/audio',content=wav()).status_code==200
    monkeypatch.setattr(providers,'transcribe',lambda *_:('Packing complete. Quality pending.','controlled-prisma'))
    assert worker.post(base+'/notes/'+note+'/process',json={'transcribe_only':True}).status_code==202
    run_once(repo)
    monkeypatch.setattr(providers,'transcribe',lambda *_:pytest.fail('Do not retranscribe'))
    extraction(monkeypatch,[{'property':'packing','value':'complete','excerpt':'Packing complete'},{'property':'quality','value':'pending','excerpt':'Quality pending'}])
    assert worker.post(base+'/notes/'+note+'/process',json={}).status_code==202
    run_once(repo)
    for c in (worker,supervisor,owner):
        data=c.get(base+'/workspace').json();assert any(n['id']==note for n in data['notes'])
        assert data['batches'][0]['status']=='hold' and len(data['batches'][0]['claims'])==2
    claim=worker.get(base+'/notes/'+note).json()['claims'][0]['id']
    body={'action':'confirm','reason':'Reviewed source','expected_version':version(worker,base)}
    assert worker.post(base+'/claims/'+claim+'/resolve',json=body).status_code==403
    assert supervisor.post(base+'/claims/'+claim+'/resolve',json=body).status_code==200
    assert owner.get(base+'/workspace').json()['batches'][0]['status']=='hold'
    worker.post(base+'/notes/'+note+'/process',json={});run_once(repo)
    assert len(worker.get(base+'/notes/'+note).json()['claims'])==2


@pytest.mark.parametrize('text,outcome,modality,negated,status',[
    ('Labels check kar diya.','done','actual',False,'reported_complete'),
    ('Labels check nahi hua.','not_done','actual',True,'open'),
    ('Labels kal check karunga.','not_done','planned',False,'open'),
    ('Inspection ke baad karunga.','not_done','conditional',False,'open'),
    ('Haan.','unclear','actual',False,'open'),
])
def test_selected_task_report_never_verifies_or_clears_hold(monkeypatch,text,outcome,modality,negated,status):
    owner,worker,supervisor,org,team,task=task_setup(monkeypatch);base='/organizations/'+org
    note=task_note(worker,org,team,task,text)
    extraction(monkeypatch,completion={'task_id':task,'outcome':outcome,'excerpt':text,'modality':modality,'negated':negated})
    worker.post(base+'/notes/'+note+'/process',json={})
    for c in (worker,supervisor,owner):
        batch=c.get(base+'/workspace').json()['batches'][0]
        assert batch['status']=='hold'
        t=next(t for t in batch['tasks'] if t['id']==task)
        assert t['status']==status
        if status=='reported_complete': assert t['completion_note_id']==note and t['completion_note_revision']==1
    if status=='reported_complete':
        body={'action':'verify','reason':'Listened to source','expected_version':version(supervisor,base)}
        assert worker.post(base+'/tasks/'+task,json=body).status_code==403
        assert supervisor.post(base+'/tasks/'+task,json=body).status_code==200
        assert owner.get(base+'/workspace').json()['batches'][0]['status']=='hold'
        assert worker.post(base+'/notes/'+note+'/revisions',json={'transcript':'Correction: labels check nahi hua.','expected_version':version(worker,base)}).status_code==200
        t=next(t for t in owner.get(base+'/workspace').json()['batches'][0]['tasks'] if t['id']==task)
        assert t['status']=='open' and t['source_review_pending']
        body['expected_version']=version(supervisor,base)
        assert supervisor.post(base+'/tasks/'+task,json=body).status_code==409


def test_task_context_cannot_be_guessed_or_assigned_to_another_person(monkeypatch):
    owner,worker,supervisor,org,team,task=task_setup(monkeypatch);base='/organizations/'+org
    payload={'batch_id':team['work_item'],'shift_id':team['shift_id'],'task_id':task,'recorded_at':datetime.now(timezone.utc).isoformat(),'idempotency_key':'not-my-task'}
    assert supervisor.post(base+'/notes',json=payload).status_code==403
    for completion in [dict(task_id=task,outcome='done',excerpt='done',modality='planned'),dict(task_id='other',outcome='done',excerpt='done'),dict(task_id=task,outcome='done',excerpt='invented')]:
        with pytest.raises(ValueError):providers.validate_extraction({'claims':[],'task_completion':completion},'done',{'task':{'id':task}})
    with pytest.raises(ValueError):providers.validate_extraction({'claims':[],'task_completion':dict(task_id=task,outcome='done',excerpt='done')},'done')


def test_duplicate_completion_and_assignment_change_do_not_apply_twice(monkeypatch):
    owner,worker,supervisor,org,team,task=task_setup(monkeypatch);base='/organizations/'+org
    note=task_note(worker,org,team,task,'Task complete ho gaya.')
    extraction(monkeypatch,completion={'task_id':task,'outcome':'done','excerpt':'Task complete ho gaya.'})
    worker.post(base+'/notes/'+note+'/process',json={})
    before=owner.get(base+'/workspace').json()
    worker.post(base+'/notes/'+note+'/process',json={})
    after=owner.get(base+'/workspace').json()
    assert before['version']==after['version']
    assert len([r for r in after['resolutions'] if r['action']=='report_complete'])==1
    # A subsequent explicit negative report must not leave completion ready to verify.
    negative=task_note(worker,org,team,task,'Correction: task complete nahi hua.','negative-task-report')
    extraction(monkeypatch,completion={'task_id':task,'outcome':'not_done','excerpt':'task complete nahi hua.','negated':True})
    worker.post(base+'/notes/'+negative+'/process',json={})
    current=owner.get(base+'/workspace').json()
    assert next(t for t in current['batches'][0]['tasks'] if t['id']==task)['status']=='open'
    assert supervisor.post(base+'/tasks/'+task,json={'action':'verify','reason':'Should not verify','expected_version':current['version']}).status_code==409


def test_model_mislabels_future_or_negative_completion_is_rejected():
    for text in ['Task complete nahi hua.', 'Task will be complete tomorrow.', 'काम पूरा नहीं हुआ।', 'काम पूरा हो जाएगा।']:
        with pytest.raises(ValueError):
            providers.validate_extraction({'claims':[],'task_completion':{'task_id':'assigned','outcome':'done','excerpt':text}},text,{'task':{'id':'assigned'}})


def test_task_reassigned_during_model_call_does_not_complete(monkeypatch):
    owner,worker,supervisor,org,team,task=task_setup(monkeypatch);base='/organizations/'+org
    note=task_note(worker,org,team,task,'Task complete ho gaya.')
    def changed(text,batch,reserve,context):
        supervisor_id=supervisor.get('/auth/session').json()['user']['id']
        response=supervisor.post(base+'/tasks/'+task,json={'action':'assign','owner_id':supervisor_id,'reason':'Changed responsibility','expected_version':version(supervisor,base)})
        assert response.status_code==200
        return providers.validate_extraction({'claims':[],'task_completion':{'task_id':task,'outcome':'done','excerpt':text}},text,context),'controlled-reassignment'
    monkeypatch.setattr(providers,'extract',changed)
    worker.post(base+'/notes/'+note+'/process',json={})
    assert worker.get(base+'/notes/'+note).json()['status']=='manual_review'
    assert next(t for t in owner.get(base+'/workspace').json()['batches'][0]['tasks'] if t['id']==task)['status']=='open'
