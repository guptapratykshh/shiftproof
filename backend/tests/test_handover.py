from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
import io
import wave
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from shiftproof.fixtures import ACTORS as DEMO_ACTORS
from shiftproof.models import NoteCreate, ResolveRequest, AckRequest, Extraction
from shiftproof.repository import Conflict
from shiftproof.service import create_note, submit_transcript, process_note, resolve, acknowledge, seed, validate_audio, mark_queued
from shiftproof.engine import handover, answer_question
from shiftproof.providers import SAMPLES, ProviderError, validate_extraction

def add(repo, sample_id, role='operator', batch='B-17', key=None):
    actor = DEMO_ACTORS[role]
    body = NoteCreate(batch_id=batch, recorded_at=datetime.now(timezone.utc), idempotency_key=key or f'test-{sample_id}-{len(repo.load()["notes"])}')
    note = create_note(repo, body, actor)
    submit_transcript(repo, note['id'], next(s['text'] for s in SAMPLES if s['id']==sample_id), actor)
    process_note(repo, note['id'])
    return [c for c in repo.load()['claims'].values() if c['note_id']==note['id']]

def confirm(repo, claim, role='supervisor', supersedes=None):
    return resolve(repo, claim['id'], ResolveRequest(expected_version=repo.load()['version'], action='confirm', reason='Checked original report', supersedes=supersedes or []), DEMO_ACTORS[role])

def batch(repo):
    return handover(repo.load())['batches'][0]

def test_dispatch_never_clears_pending_quality(repo):
    for c in add(repo,'packing-hold'):
        confirm(repo,c)
    ready = add(repo,'dispatch','supervisor')[0]
    confirm(repo,ready)
    assert batch(repo)['status']=='hold'
    assert batch(repo)['quality']=='pending'
    assert any(c['type']=='unmet_condition' for c in batch(repo)['conflicts'])
    assert batch(repo)['clarification']['type']=='quality'

def test_only_quality_can_clear_or_reject_hold(repo):
    hold = add(repo,'packing-hold')[1]
    confirm(repo,hold)
    release = add(repo,'quality-clear','quality')[0]
    with pytest.raises(HTTPException) as error:
        confirm(repo,release,supersedes=[hold['id']])
    assert error.value.status_code==403
    with pytest.raises(HTTPException) as error:
        resolve(repo,hold['id'],ResolveRequest(expected_version=repo.load()['version'],action='reject',reason='Skip this hold'),DEMO_ACTORS['supervisor'])
    assert error.value.status_code==403
    assert repo.load()['claims'][hold['id']]['status']=='confirmed'

def test_release_requires_explicit_supersession(repo):
    packing,hold = add(repo,'packing-hold')
    confirm(repo,packing); confirm(repo,hold)
    release = add(repo,'quality-clear','quality')[0]
    with pytest.raises(HTTPException) as error:
        confirm(repo,release,'quality')
    assert error.value.status_code==409
    confirm(repo,release,'quality',[hold['id']])
    assert batch(repo)['status']=='verified'
    assert repo.load()['claims'][hold['id']]['status']=='superseded'
    assert repo.load()['notes'][hold['note_id']]['transcripts'][0]['text']

def test_quantity_correction_preserves_fifteen(repo):
    fifteen=add(repo,'quantity-15')[0]; confirm(repo,fifteen)
    fifty=add(repo,'quantity-50')[0]
    assert batch(repo)['quantity'] is None
    confirm(repo,fifty,supersedes=[fifteen['id']])
    assert batch(repo)['quantity']==50
    assert repo.load()['claims'][fifteen['id']]['value']==15
    assert repo.load()['claims'][fifteen['id']]['status']=='superseded'

def test_conditional_dispatch_cannot_establish_readiness(repo):
    c=add(repo,'conditional')[0];confirm(repo,c)
    assert batch(repo)['status']!='verified'
    assert batch(repo)['clarification']['type']=='condition'

def test_negation_produces_pending(repo):
    c=add(repo,'negative')[0];confirm(repo,c)
    assert c['value']=='pending'
    assert c['negated'] is True
    assert batch(repo)['packing']=='unverified'

def test_late_dated_upload_does_not_override_current_state(repo):
    new=add(repo,'quantity-50')[0]
    with repo.transaction() as s:
        s['claims'][new['id']]['reported_at']='2026-10-07T12:00:00+00:00'
    confirm(repo,new)
    old=add(repo,'quantity-15')[0]
    with repo.transaction() as s:
        s['claims'][old['id']]['reported_at']='2026-10-07T10:00:00+00:00'
    assert batch(repo)['quantity']==50
    assert old['id'] in repo.load()['claims']
    with pytest.raises(HTTPException):
        confirm(repo,repo.load()['claims'][old['id']],supersedes=[new['id']])

def test_missing_timestamp_is_not_invented(repo):
    c=add(repo,'quantity-15')[0]
    assert c['reported_at'] is None

def test_duplicate_delivery_does_not_duplicate_claims(repo):
    c=add(repo,'packing-hold')[0]
    before=repo.load()
    process_note(repo,c['note_id']);process_note(repo,c['note_id'])
    assert repo.load()==before

def test_duplicate_creation_is_idempotent(repo):
    body=NoteCreate(batch_id='B-17',recorded_at=datetime.now(timezone.utc),idempotency_key='same-note-key')
    one=create_note(repo,body,DEMO_ACTORS['operator']);two=create_note(repo,body,DEMO_ACTORS['operator'])
    assert one['id']==two['id']
    assert len(repo.load()['notes'])==1
    assert repo.load()['usage'][datetime.now(timezone.utc).date().isoformat()]['notes']==1

def test_idempotency_key_reuse_different_payload_fails(repo):
    body=NoteCreate(batch_id='B-17',recorded_at=datetime.now(timezone.utc),idempotency_key='same-note-key')
    create_note(repo,body,DEMO_ACTORS['operator'])
    body.batch_id='B-18'
    with pytest.raises(Conflict):create_note(repo,body,DEMO_ACTORS['operator'])

def test_two_reviewers_cannot_silently_overwrite(repo):
    c=add(repo,'quantity-15')[0]
    request=ResolveRequest(expected_version=repo.load()['version'],action='confirm',reason='Independently checked')
    def review(role):
        try:resolve(repo,c['id'],request,DEMO_ACTORS[role]);return 'saved'
        except Conflict:return 'stale'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(review,['supervisor','quality']))
    assert sorted(results)==['saved','stale']

def test_material_update_invalidates_acknowledgement(repo):
    seed(repo)
    version=repo.load()['version']
    acknowledge(repo,AckRequest(expected_version=version,readback='Quality clearance tak dispatch pending rahega'),DEMO_ACTORS['operator'])
    assert handover(repo.load())['acknowledgements'][0]['current']
    add(repo,'quantity-15')
    assert not handover(repo.load())['acknowledgements'][0]['current']
    with pytest.raises(Conflict):
        acknowledge(repo,AckRequest(expected_version=version,readback='Read this earlier version'),DEMO_ACTORS['operator'])

def test_unprocessed_note_blocks_verified_and_ack(repo):
    seed(repo)
    body=NoteCreate(batch_id='B-18',recorded_at=datetime.now(timezone.utc),idempotency_key='pending-note')
    create_note(repo,body,DEMO_ACTORS['operator'])
    assert handover(repo.load())['batches'][1]['status']!='verified'
    with pytest.raises(HTTPException):acknowledge(repo,AckRequest(expected_version=repo.load()['version'],readback='Everything checked'),DEMO_ACTORS['operator'])

def test_spoken_batch_mismatch_needs_review(repo):
    claims=add(repo,'packing-hold',batch='B-18')
    assert all(c['batch_mismatch'] for c in claims)
    with pytest.raises(HTTPException):confirm(repo,claims[0])

def test_operator_cannot_review(repo):
    c=add(repo,'quantity-15')[0]
    with pytest.raises(HTTPException) as error:confirm(repo,c,'operator')
    assert error.value.status_code==403

def test_unknown_question_abstains(repo):
    seed(repo)
    assert answer_question(repo.load(),'B-17','What is the weather tomorrow?')['abstained']

def test_grounded_answer_cites_real_claims(repo):
    seed(repo)
    answer=answer_question(repo.load(),'B-17','Why is this held?')
    assert answer['claim_ids']
    assert all(cid in repo.load()['claims'] for cid in answer['claim_ids'])

def test_extraction_cannot_fabricate_evidence():
    with pytest.raises(ValueError):
        validate_extraction({'claims':[{'property':'quality','value':'cleared','excerpt':'not actually said'}]},'quality pending')

def test_condition_requires_explicit_condition():
    with pytest.raises(ValueError):
        validate_extraction({'claims':[{'property':'dispatch','value':'ready','excerpt':'ready if','modality':'conditional'}]},'ready if')

def test_failed_provider_preserves_transcript(repo,monkeypatch):
    monkeypatch.setattr('shiftproof.providers.extract',lambda *args: (_ for _ in ()).throw(ProviderError('Provider credits exhausted')))
    add(repo,'quantity-15')
    note=next(iter(repo.load()['notes'].values()))
    assert note['status']=='manual_review'
    assert note['transcripts']
    assert not repo.load()['claims']
    assert note['error']=='Provider credits exhausted'

def test_transcript_revision_keeps_original_evidence(repo):
    c=add(repo,'quantity-15')[0];confirm(repo,c)
    note=repo.load()['notes'][c['note_id']]
    new=next(s['text'] for s in SAMPLES if s['id']=='quantity-50')
    submit_transcript(repo,note['id'],new,DEMO_ACTORS['operator'],repo.load()['version']);process_note(repo,note['id'])
    s=repo.load()
    assert len(s['notes'][note['id']]['transcripts'])==2
    assert s['claims'][c['id']]['status']=='confirmed'
    assert any(conf['type']=='quantity' for conf in batch(repo)['conflicts'])

def test_invalid_audio_rejected():
    with pytest.raises(HTTPException):validate_audio(b'not wav')
    buf=io.BytesIO()
    with wave.open(buf,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\x00\x00'*16000)
    assert validate_audio(buf.getvalue())==1

def test_oversized_audio_rejected():
    with pytest.raises(HTTPException):validate_audio(b'x'*4_500_001)

def test_api_rejects_forged_role_headers(repo):
    from shiftproof.api import app
    seed(repo)
    client=TestClient(app)
    cid=next(iter(repo.load()['claims']))
    r=client.post(f'/organizations/unknown/claims/{cid}/resolve',headers={'X-Role':'quality'},json={'expected_version':repo.load()['version'],'action':'confirm','reason':'Skip auth'})
    assert r.status_code==401

def test_api_full_text_workflow(organization_api):
    client,org,repo=organization_api
    base=f'/organizations/{org}'
    body={'batch_id':'B-17','recorded_at':datetime.now(timezone.utc).isoformat(),'idempotency_key':'api-workflow-001'}
    response=client.post(base+'/notes',json=body);assert response.status_code==201
    nid=response.json()['note']['id']
    assert client.post(base+f'/notes/{nid}/transcript',json={'transcript':SAMPLES[0]['text']}).status_code==200
    assert client.post(base+f'/notes/{nid}/process',json={}).status_code==202
    note=client.get(base+f'/notes/{nid}').json()
    assert note['status']=='processed'
    assert len(note['claims'])==2

def test_other_author_cannot_replace_transcript(repo):
    c=add(repo,'quantity-15')[0]
    with pytest.raises(HTTPException) as error:
        submit_transcript(repo,c['note_id'],'fake edit',DEMO_ACTORS['quality'],repo.load()['version'])
    assert error.value.status_code==403

def test_unknown_scripted_input_is_not_fake_ai(repo):
    body=NoteCreate(batch_id='B-17',recorded_at=datetime.now(timezone.utc),idempotency_key='unsupported-text')
    n=create_note(repo,body,DEMO_ACTORS['operator'])
    submit_transcript(repo,n['id'],'An unseen custom statement',DEMO_ACTORS['operator']);process_note(repo,n['id'])
    assert repo.load()['notes'][n['id']]['status']=='manual_review'
    assert not repo.load()['claims']

def test_invalid_bedrock_json_gets_one_repair_then_fails(monkeypatch):
    from shiftproof.config import settings
    from shiftproof.providers import extract
    monkeypatch.setenv('EXTRACTION_PROVIDER','bedrock');settings.cache_clear()
    calls=[]
    class FakeClient:
        def converse(self,**kwargs):
            calls.append(kwargs)
            return {'output':{'message':{'content':[{'text':'not json'}]}},'ResponseMetadata':{'RequestId':'fake'}}
    monkeypatch.setattr('boto3.client',lambda *a,**k:FakeClient())
    with pytest.raises(ProviderError,match='failed validation within'):
        extract('packing pending','B-17')
    assert len(calls)==2

def test_transcription_denial_preserves_audio_error(monkeypatch):
    import httpx
    from shiftproof.providers import transcribe
    from shiftproof.config import settings
    monkeypatch.setattr(settings(),'gnani_key',lambda:'test-not-a-real-key')
    response=httpx.Response(403,request=httpx.Request('POST','https://api.vachana.ai/stt/v3'))
    monkeypatch.setattr('httpx.post',lambda *a,**k:response)
    with pytest.raises(ProviderError,match='remaining programme credits'):
        transcribe(b'fictional-audio')

def test_daily_model_quota_stops_new_calls(repo,monkeypatch):
    from shiftproof.service import reserve_usage
    reserve_usage(repo,limit=1)
    with pytest.raises(ProviderError,match='Daily model calls limit'):
        reserve_usage(repo,limit=1)

def test_task_requires_owner_before_completion_and_records_actor(organization_api):
    from test_organizations import item
    client,org,repo=organization_api
    item(client,org,'B-19');seed(repo)
    base=f'/organizations/{org}'
    me=client.get('/auth/session').json()['user']['id']
    task=next(c for c in repo.load()['claims'].values() if c['property']=='task')
    request={'expected_version':repo.load()['version'],'action':'complete','reason':'Checked the labels'}
    assert client.post(base+f'/tasks/{task["id"]}',json=request).status_code==422
    request.update(action='assign',owner_id=me)
    assert client.post(base+f'/tasks/{task["id"]}',json=request).status_code==200
    request.update(action='complete',expected_version=repo.load()['version'])
    assert client.post(base+f'/tasks/{task["id"]}',json=request).status_code==200
    state=repo.load()
    assert state['claims'][task['id']]['task_status']=='completed'
    assert any(r['action']=='complete' and r['actor']['id']==me for r in state['resolutions'].values())

def test_rejecting_mismatched_claims_finishes_manual_review(repo):
    claims=add(repo,'packing-hold',batch='B-18')
    note_id=claims[0]['note_id']
    assert repo.load()['notes'][note_id]['status']=='manual_review'
    for c in claims:
        resolve(repo,c['id'],ResolveRequest(expected_version=repo.load()['version'],action='reject',reason='Wrong batch; original note retained for correction.'),DEMO_ACTORS['quality'])
    state=repo.load()
    assert state['notes'][note_id]['status']=='processed'
    assert state['notes'][note_id]['review_outcome']['previous_error']
    acknowledge(repo,AckRequest(expected_version=state['version'],readback='Wrong-batch report was rejected; new note needed.'),DEMO_ACTORS['operator'])
