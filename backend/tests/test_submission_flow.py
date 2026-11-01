from datetime import datetime, timezone
import pytest
from shiftproof import providers
from shiftproof.profiles import PROFILES
from test_voice_reporting import setup_team, extraction, version
from test_pilot_scope import create_note


def test_failed_clarification_is_received_not_reasked_and_holds_require_review(monkeypatch):
    owner, worker, supervisor, org, team, _ = setup_team()
    base = '/organizations/' + org
    note = create_note(worker, org, team, transcript='Packing complete. Quality pending.')
    extraction(monkeypatch, [dict(property='packing',value='complete',excerpt='Packing complete'), dict(property='quality',value='pending',excerpt='Quality pending')])
    worker.post(base+'/notes/'+note+'/process',json={})
    view = worker.get(base+'/workspace').json()
    question = view['batches'][0]['clarification']
    assert question['response_status']=='needs_answer'
    reply=worker.post(base+'/notes',json=dict(batch_id=team['work_item'],shift_id=team['shift_id'],recorded_at=datetime.now(timezone.utc).isoformat(),idempotency_key='clarification-reply',clarification_ref=question['id'],clarification_version=view['version'])).json()['note']['id']
    worker.post(base+'/notes/'+reply+'/transcript',json={'transcript':'Quality pending.'})
    # Transcription alone is not submission.
    assert worker.get(base+'/workspace').json()['batches'][0]['clarification']['response_status']=='needs_answer'
    def unavailable(*args,**kwargs): raise providers.ExtractionUnavailable('Controlled invalid output','invalid_output')
    monkeypatch.setattr(providers,'extract',unavailable)
    assert worker.post(base+'/notes/'+reply+'/process',json={}).status_code==202
    row=worker.get(base+'/notes/'+reply).json()
    assert row['submitted_at'] and row['submitted_revision']==row['revision']
    for client in [worker,supervisor,owner]:
        view=client.get(base+'/workspace').json()
        q=view['batches'][0]['clarification']
        assert q['response_status']=='needs_review' and q['response_note_ids']==[reply]
        assert reply in [n['id'] for n in view['acknowledgement_blockers']]
        assert view['batches'][0]['status']=='hold'
    ack=supervisor.post(base+f"/shifts/{team['shift_id']}/acknowledgements",json={'expected_version':version(supervisor,base),'readback':'Yes it is done'})
    assert ack.status_code==409
    interpreted=supervisor.post(base+'/notes/'+reply+'/review-transcript',json={'expected_version':version(supervisor,base),'reason':'Listened to the saved answer with its question','claims':[dict(property='quality',value='pending',excerpt='Quality pending')]})
    assert interpreted.status_code==200,interpreted.text
    claim=supervisor.get(base+'/notes/'+reply).json()['claims'][0]
    assert supervisor.post(base+'/claims/'+claim['id']+'/resolve',json={'action':'confirm','reason':'Verified the source reports pending inspection','expected_version':version(supervisor,base)}).status_code==200
    view=supervisor.get(base+'/workspace').json()
    assert view['batches'][0]['clarification']['response_status']=='reviewed'
    assert view['batches'][0]['status']=='hold'
    assert not view['acknowledgement_blockers']
    # An unrelated newer hold can require a new answer. Reviewing old evidence
    # must not hide the new report.
    newer=create_note(worker,org,team,key='new-inspection',transcript='Another inspection pending.')
    extraction(monkeypatch,[dict(property='quality',value='pending',excerpt='inspection pending')])
    worker.post(base+'/notes/'+newer+'/process',json={})
    assert worker.get(base+'/workspace').json()['batches'][0]['clarification']['response_status']=='needs_answer'


def test_clarification_schema_requires_question_reference_without_weakening_validation(monkeypatch):
    monkeypatch.setenv('EXTRACTION_PROVIDER','gemini')
    from shiftproof.config import settings
    settings.cache_clear()
    question={'id':'Batch02:quality','text':'Quality clear or pending?'}
    context={'workflow':PROFILES['manufacturing'],'clarification':question}
    def generate(system,payload,schema,reserve,validator):
        candidate=schema['$defs']['Candidate']
        assert 'context_refs' in candidate['required']
        assert candidate['properties']['context_refs']['items']['type']=='string'
        raw={'claims':[{'property':'quality','value':'pending','excerpt':'Still pending.'}]}
        with pytest.raises(ValueError,match='stored question'):validator(raw)
        raw['claims'][0]['context_refs']=['invented-question']
        with pytest.raises(ValueError,match='not supplied'):validator(raw)
        raw['claims'][0]['context_refs']=[question['id']]
        return validator(raw),'controlled'
    monkeypatch.setattr(providers,'generate_json',generate)
    result,_=providers.extract('Still pending.','Batch02',context=context)
    assert result.claims[0].context_refs==[question['id']]
