from datetime import datetime,timezone
import pytest
from test_organizations import account,state,extract
from test_pilot_scope import team_shift,assign,email_member,create_note
from shiftproof import identity,providers

def setup():
    owner,org,_=account('warehousing'); team=team_shift(owner,org)
    me=owner.get('/auth/session').json()['user']['id'];assign(owner,org,team,[me],supervisor_id=me)
    owner.headers['X-Shift-ID']=team['shift_id']
    return owner,org,team,me

def failed(c,org,team,text='Packing complete. Ready for dispatch.'):
    nid=create_note(c,org,team,key='source-'+str(datetime.now().timestamp()),transcript=text)
    repo=identity.tenant_repo({'id':org,'industry':'warehousing'})
    with repo.transaction() as s:s['notes'][nid].update(status='manual_review',processing_stage='review_required')
    return nid,repo

def post_review(c,org,nid,decisions,key='review-request-1'):
    return c.post(f'/organizations/{org}/notes/{nid}/review',json={'expected_version':state(c,org)['version'],'request_id':key,'decisions':decisions})

def test_empty_review_cannot_close_report_and_explicit_closure_can_reopen():
    c,org,team,me=setup();nid,repo=failed(c,org,team)
    path=f'/organizations/{org}/notes/{nid}'
    body={'expected_version':state(c,org)['version'],'claims':[],'reason':'Ready for dispatch'}
    assert c.post(path+'/review-transcript',json=body).status_code==422
    assert post_review(c,org,nid,[]).status_code==422
    body.update(no_operational_update=True,reason='Fictional microphone test, no work update')
    assert c.post(path+'/review-transcript',json=body).status_code==200
    progress=state(c,org)['notes'][0]['review_progress'];assert progress['can_reopen']
    assert c.post(path+'/reopen',json={'expected_version':state(c,org)['version'],'reason':'Earlier closure was mistaken'}).status_code==200
    old=repo.load();assert old['notes'][nid]['review_outcome']['action']=='no_operational_claims'
    decision={'candidate':{'property':'packing','value':'complete','excerpt':'Packing complete'},'action':'confirm','reason':'Checked against the recording'}
    r=post_review(c,org,nid,[decision]);assert r.status_code==200,r.text
    assert state(c,org)['notes'][0]['review_progress']['state']=='checked'
    assert len(repo.load()['resolutions'])>=3

def test_report_review_atomic_permission_failure_and_idempotent_retry():
    c,org,team,me=setup();nid,repo=failed(c,org,team,'Packing complete. Documents verified.')
    decisions=[{'candidate':{'property':p,'value':v,'excerpt':e},'action':'confirm','reason':'Checked the source and the supporting records'} for p,v,e in [('packing','complete','Packing complete'),('documents','verified','Documents verified')]]
    before=repo.load()
    assert post_review(c,org,nid,decisions).status_code==403
    assert repo.load()['claims']==before['claims']
    r=post_review(c,org,nid,decisions[:1]);assert r.status_code==200,r.text
    after=state(c,org)
    r=post_review(c,org,nid,decisions[:1]);assert r.status_code==200
    assert state(c,org)['version']==after['version']
    assert len(repo.load()['claims'])==1
    summary=after['summary'];assert any(i['kind']=='checked' and 'Packing' in i['text']['en'] for i in summary['items'])
    assert any('documents' in i['text']['en'].lower() and i['kind']=='outstanding' for i in summary['items'])

def test_speech_rechecks_version_after_provider_returns(monkeypatch):
    c,org,team,me=setup();nid,repo=failed(c,org,team)
    def synthesis(text):
        with repo.transaction() as s:
            s['notes'][nid]['revision']+=1
        return b'fake-audio'
    monkeypatch.setattr(providers,'synthesize',synthesis)
    r=c.post(f'/organizations/{org}/speech',json={'batch_id':team['work_item'],'kind':'handover','expected_version':state(c,org)['version']})
    assert r.status_code==409,r.text

def test_assisted_capture_requires_grant_assignment_and_live_membership():
    c,org,team,me=setup()
    worker,worker_id,_=email_member(c,org,'assisted-worker@example.com')
    assign(c,org,team,[me,worker_id],supervisor_id=me)
    base=f'/organizations/{org}'
    body={'batch_id':team['work_item'],'shift_id':team['shift_id'],'recorded_at':datetime.now(timezone.utc).isoformat(),'idempotency_key':'assisted-capture-1','reported_by_id':worker_id}
    assert c.post(base+'/notes',json=body).status_code==403
    assert c.put(base+'/assisted-capture',json={'user_id':me,'shift_ids':[team['shift_id']]}).status_code==200
    r=c.post(base+'/notes',json=body);assert r.status_code==201,r.text
    n=r.json()['note'];assert n['actor']['id']==me and n['reported_by']['id']==worker_id
    assert c.post(base+'/notes',json={**body,'reported_by_id':None}).status_code==409
    assert c.post(base+'/notes',json=body).status_code==201
    assert c.put(base+'/assisted-capture',json={'user_id':me,'shift_ids':[]}).status_code==200
    assert c.post(base+'/notes/'+n['id']+'/process',json={}).status_code==403
    worker.headers['X-CSRF-Token']=worker.get('/auth/session').json()['csrf_token']
    assert worker.put(base+'/assisted-capture',json={'user_id':worker_id,'shift_ids':[team['shift_id']]}).status_code==403

def test_foreign_report_and_stale_review_are_rejected():
    c,org,team,me=setup();nid,repo=failed(c,org,team)
    decision={'candidate':{'property':'packing','value':'complete','excerpt':'Packing complete'},'action':'confirm','reason':'Checked against the recording'}
    other,other_org,_=account('warehousing',email='other-reviewer@example.com')
    result=other.post(f'/organizations/{org}/notes/{nid}/review',json={'expected_version':state(c,org)['version'],'request_id':'foreign-review','decisions':[decision]})
    assert result.status_code in (403,404)
    version=state(c,org)['version']
    with repo.transaction() as s:s['notes'][nid]['revision']+=1
    result=c.post(f'/organizations/{org}/notes/{nid}/review',json={'expected_version':version,'request_id':'stale-review','decisions':[decision]})
    assert result.status_code==409
    assert not repo.load()['claims']

def test_spoken_summary_matches_checked_and_outstanding_screen_items(monkeypatch):
    c,org,team,me=setup();nid,repo=failed(c,org,team)
    decision={'candidate':{'property':'packing','value':'complete','excerpt':'Packing complete'},'action':'confirm','reason':'Checked against the recording'}
    assert post_review(c,org,nid,[decision]).status_code==200
    view=state(c,org);heard=[]
    monkeypatch.setattr(providers,'synthesize',lambda text:heard.append(text) or b'controlled-audio')
    r=c.post(f'/organizations/{org}/speech',json={'batch_id':team['work_item'],'kind':'handover','language':'hi','expected_version':view['version']})
    assert r.status_code==200
    assert r.headers['X-Summary-Version']==str(view['version'])
    assert 'रिपोर्ट की जाँच हो गई है' in heard[0]
    assert 'भेजने के दस्तावेज़ की जाँच अभी बाकी है' in heard[0]
    assert all(i['text']['hi'] in heard[0] for i in view['summary']['items'])

def test_assisted_task_completion_is_only_reported_complete(monkeypatch):
    from shiftproof.models import Extraction,TaskCompletion
    c,org,team,me=setup();worker,worker_id,_=email_member(c,org,'assisted-task@example.com')
    assign(c,org,team,[me,worker_id],supervisor_id=me)
    nid,repo=failed(c,org,team,'Check labels')
    decision={'candidate':{'property':'task','value':'Check labels','excerpt':'Check labels'},'action':'confirm','reason':'Checked against the recording'}
    assert post_review(c,org,nid,[decision]).status_code==200
    task=state(c,org)['batches'][0]['claims'][0]['id'];base=f'/organizations/{org}'
    assert c.post(base+'/tasks/'+task,json={'action':'assign','owner_id':worker_id,'expected_version':state(c,org)['version'],'reason':'Assigned to worker'}).status_code==200
    assert c.put(base+'/assisted-capture',json={'user_id':me,'shift_ids':[team['shift_id']]}).status_code==200
    r=c.post(base+'/notes',json={'batch_id':team['work_item'],'shift_id':team['shift_id'],'recorded_at':datetime.now(timezone.utc).isoformat(),'idempotency_key':'assisted-task-completion','reported_by_id':worker_id,'task_id':task})
    assert r.status_code==201,r.text
    reply=r.json()['note']['id'];assert c.post(base+'/notes/'+reply+'/transcript',json={'transcript':'Labels checked'}).status_code==200
    monkeypatch.setattr(providers,'extract',lambda *args:(Extraction(claims=[],task_completion=TaskCompletion(task_id=task,outcome='done',excerpt='Labels checked')),'controlled-inference'))
    assert c.post(base+'/notes/'+reply+'/process',json={}).status_code==202
    assert state(c,org)['batches'][0]['tasks'][0]['status']=='reported_complete'
