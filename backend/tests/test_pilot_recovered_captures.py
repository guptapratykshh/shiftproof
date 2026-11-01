"""Recovery imports preserve author evidence without bypassing normal capture rules."""
import copy
from datetime import datetime, timedelta, timezone

from shiftproof import identity, providers
from test_organizations import account
from test_employee_auth import invitation, activate
from test_pilot_scope import team_shift, assign, email_member, wav


def historical_team(owner, org):
    current = datetime.now(timezone.utc)
    team = team_shift(owner, org, 'RECOVER', starts=current-timedelta(hours=90), ends=current-timedelta(hours=82))
    return team, current-timedelta(hours=85)


def recovery_body(team, actor_id, recorded, key='supervised-offline-capture'):
    return {'note': {'batch_id': team['work_item'], 'shift_id': team['shift_id'],
                     'recorded_at': recorded.isoformat(), 'idempotency_key': key},
            'original_actor_id': actor_id, 'reason': 'Phone stayed offline beyond the normal upload window'}


def test_import_preserves_former_author_history_audio_and_exact_retry():
    owner, org, _ = account()
    team, recorded = historical_team(owner, org)
    worker, _ = activate(invitation(owner, org))
    person = worker.get('/auth/session').json()['user']['id']
    assign(owner, org, team, [person])
    base = f'/organizations/{org}'
    payload = recovery_body(team, person, recorded)
    assert worker.post(base+'/notes', json=payload['note']).status_code == 409
    assert worker.post(base+'/recovered-captures', json=payload).status_code == 403
    assign(owner, org, team, [])
    assert owner.delete(base+'/members/'+person).status_code == 200
    owner.headers['X-Shift-ID'] = team['shift_id']
    result = owner.post(base+'/recovered-captures', json=payload)
    assert result.status_code == 201, result.text
    note = result.json()['note']
    assert note['actor']['id'] == person and note['recorded_at'] == recorded.isoformat()
    assert note['late_submission'] and not note['addendum']
    imported = note['supervised_import']
    assert imported['assignment_evidence']['kind'] == 'history'
    assert imported['source_role_basis'] == 'historical_role_unknown'
    assert note['processing_takeover']['actor']['id'] == owner.get('/auth/session').json()['user']['id']
    before = owner.get(base+'/export').json()
    again = owner.post(base+'/recovered-captures', json=payload)
    assert again.status_code == 201 and again.json()['duplicate']
    after = owner.get(base+'/export').json()
    assert after['version'] == before['version']
    assert after['operational_events'] == before['operational_events']
    assert after['usage'] == before['usage']
    changed = copy.deepcopy(payload); changed['note']['recorded_at'] = (recorded+timedelta(minutes=1)).isoformat()
    assert owner.post(base+'/recovered-captures', json=changed).status_code == 409
    path = result.json()['upload_url']
    assert owner.put(path, content=wav()).status_code == 200
    assert owner.put(path, content=wav()).json()['duplicate']
    changed_audio = bytearray(wav()); changed_audio[-1] = 1
    assert owner.put(path, content=bytes(changed_audio)).status_code == 409
    assert owner.get(path).content == wav()
    events = list(owner.get(base+'/export').json()['operational_events'].values())
    events = [e for e in events if e['action'] == 'note.offline_imported']
    assert len(events) == 1 and events[0]['original_actor_id'] == person


def test_import_requires_historical_assignment_and_current_supervisor_scope():
    owner, org, _ = account()
    team, recorded = historical_team(owner, org)
    worker, _ = activate(invitation(owner, org))
    person = worker.get('/auth/session').json()['user']['id']
    supervisor, reviewer, _ = email_member(owner, org, 'recovery-supervisor@example.com', 'supervisor')
    base = f'/organizations/{org}'
    payload = recovery_body(team, person, recorded)
    assert owner.post(base+'/recovered-captures', json=payload).status_code == 422
    assign(owner, org, team, [person])
    assert supervisor.post(base+'/recovered-captures', json=payload).status_code == 404
    assign(owner, org, team, [person, reviewer], supervisor_id=reviewer)
    result = supervisor.post(base+'/recovered-captures', json=payload)
    assert result.status_code == 201, result.text
    assert result.json()['note']['supervised_import']['assignment_evidence']['kind'] == 'current'
    # Original author and importer cannot use this endpoint to reassign capture identity.
    outsider, _, _ = account(email='outside-recovery@example.com')
    changed = copy.deepcopy(payload); changed['original_actor_id'] = outsider.get('/auth/session').json()['user']['id']
    assert supervisor.post(base+'/recovered-captures', json=changed).status_code == 422
    assign(owner, org, team, [person])
    supervisor.headers['X-Shift-ID'] = team['shift_id']
    assert supervisor.put(result.json()['upload_url'], content=wav()).status_code == 404


def test_import_does_not_bypass_time_item_or_role_validation():
    owner, org, _ = account()
    team, recorded = historical_team(owner, org)
    me = owner.get('/auth/session').json()['user']['id']
    assign(owner, org, team, [me], supervisor_id=me)
    base = f'/organizations/{org}'
    payload = recovery_body(team, me, recorded)
    invalid = copy.deepcopy(payload); invalid['note']['recorded_at'] = datetime.now(timezone.utc).isoformat()
    assert owner.post(base+'/recovered-captures', json=invalid).status_code == 422
    invalid = copy.deepcopy(payload); invalid['note']['shift_id'] = 'shift-B'
    assert owner.post(base+'/recovered-captures', json=invalid).status_code == 422
    invalid = copy.deepcopy(payload); invalid['note']['supersedes'] = ['nonexistent-claim']
    assert owner.post(base+'/recovered-captures', json=invalid).status_code == 422
    assert owner.put(base+'/members/'+me, json={'access':'owner','role':'operator'}).status_code == 200
    assert owner.post(base+'/recovered-captures', json=payload).status_code == 403
    assert owner.put(base+'/members/'+me, json={'access':'owner','role':'quality'}).status_code == 200
    assert owner.post(base+'/recovered-captures', json=payload).status_code == 201
    recent = team_shift(owner, org, 'RECENT')
    assign(owner, org, recent, [me], supervisor_id=me)
    assert owner.post(base+'/recovered-captures', json=recovery_body(recent, me, datetime.now(timezone.utc))).status_code == 409
    assert len(owner.get(base+'/export').json()['notes']) == 1


def test_import_closed_addendum_preserves_snapshot_and_saved_stale_question(monkeypatch):
    owner, org, _ = account()
    team, recorded = historical_team(owner, org)
    worker, _ = activate(invitation(owner, org))
    person = worker.get('/auth/session').json()['user']['id']
    me = owner.get('/auth/session').json()['user']['id']
    assign(owner, org, team, [person, me], supervisor_id=me)
    base = f'/organizations/{org}'
    current = datetime.now(timezone.utc)
    next_shift = owner.post(base+'/shift-occurrences', json={'name':'Receiving shift','location_id':team['location_id'],'team_id':team['team_id'],
        'starts_at':current.isoformat(),'ends_at':(current+timedelta(hours=8)).isoformat()})
    assert next_shift.status_code == 201, next_shift.text
    incoming = {**team, 'shift_id':next_shift.json()['id']}
    assign(owner, org, incoming, [me], supervisor_id=me)
    assert owner.post(base+'/shift-occurrences/'+team['shift_id']+'/incoming', json={'incoming_shift_id':incoming['shift_id'],'reason':'Next supervisor reviews late evidence'}).status_code == 200
    closed = owner.post(base+'/shift-occurrences/'+team['shift_id']+'/close', json={'reason':'All captured reports reviewed at closing'})
    assert closed.status_code == 200, closed.text
    snapshot_id = closed.json()['snapshot_id']
    before = owner.get(base+'/export').json()['snapshots'][snapshot_id]
    payload = recovery_body(team, person, recorded)
    ref = team['work_item']+':quality'
    payload['note'].update(clarification_ref=ref, clarification_version=0,
        clarification_context={'id':ref, 'text':'Was quality cleared, or is it still pending?', 'version':0, 'ignore_permissions':True})
    owner.headers['X-Shift-ID'] = team['shift_id']
    result = owner.post(base+'/recovered-captures', json=payload)
    assert result.status_code == 201, result.text
    note = result.json()['note']
    assert note['addendum'] and note['stale_clarification']
    assert note['clarification_context'] == {'id':ref, 'text':payload['note']['clarification_context']['text'], 'version':0, 'unverified_client_context':True}
    assert owner.get(base+'/export').json()['snapshots'][snapshot_id] == before
    assert owner.put(result.json()['upload_url'], content=wav()).status_code == 200
    def never_extract(*args, **kwargs):
        raise AssertionError('Stale question must not reach automatic extraction')
    monkeypatch.setattr(providers, 'extract', never_extract)
    path = base+'/notes/'+note['id']
    assert owner.post(path+'/process', json={}).status_code == 202
    saved = owner.get(path).json()
    assert saved['status'] == 'manual_review' and saved['error_category'] == 'stale_clarification'
    assert saved['claim_ids'] == []
    assert owner.post(base+'/recovered-captures', json=payload).json()['duplicate']


def test_import_rejects_stale_question_without_evidence_and_existing_normal_capture():
    owner, org, _ = account()
    team, recorded = historical_team(owner, org)
    me = owner.get('/auth/session').json()['user']['id']
    assign(owner, org, team, [me], supervisor_id=me)
    base = f'/organizations/{org}'
    payload = recovery_body(team, me, recorded)
    payload['note'].update(clarification_ref=team['work_item']+':quality',clarification_version=0)
    assert owner.post(base+'/recovered-captures', json=payload).status_code == 422
    assert owner.get(base+'/export').json()['notes'] == {}
    # Simulate a genuine previously saved report, rather than creating a replacement.
    from shiftproof.models import Actor, NoteCreate
    from shiftproof import service
    repo = identity.tenant_repo(owner.get(base).json())
    normal = recovery_body(team, me, recorded)
    original = service.create_note(repo, NoteCreate(**normal['note']), Actor(id=me,name='Test Owner',role='supervisor'))
    assert owner.post(base+'/recovered-captures', json=normal).status_code == 409
    assert repo.get_record('notes', original['id']) == original


def test_import_text_preserves_supervisor_copy_provenance_and_processes_without_prisma(monkeypatch):
    owner, org, _ = account()
    team, recorded = historical_team(owner, org)
    worker, _ = activate(invitation(owner, org))
    person = worker.get('/auth/session').json()['user']['id']
    me = owner.get('/auth/session').json()['user']['id']
    assign(owner, org, team, [person])
    base = f'/organizations/{org}'
    payload = recovery_body(team, person, recorded)
    payload.update(transcript='Packing complete', audio_expected=False)
    owner.headers['X-Shift-ID'] = team['shift_id']
    result = owner.post(base+'/recovered-captures', json=payload)
    assert result.status_code == 201, result.text
    note = result.json()['note']
    assert note['source'] == 'supervised_import' and note['actor']['id'] == person
    revision = note['transcripts'][0]
    assert revision['kind'] == 'offline_import' and revision['actor_id'] == me
    assert revision['original_actor_id'] == person
    assert 'not independently attested' in note['supervised_import']['transcript_attestation']
    def no_transcription(*args, **kwargs):
        raise AssertionError('Text-only import must not attempt transcription')
    def extract(text, batch, reserve, context):
        return providers.validate_extraction({'claims':[{'property':'packing','value':'complete','excerpt':text}]},text,context),'controlled-recovery-check'
    monkeypatch.setattr(providers,'transcribe',no_transcription)
    monkeypatch.setattr(providers,'extract',extract)
    path = base+'/notes/'+note['id']
    assert owner.post(path+'/process',json={}).status_code == 202
    saved = owner.get(path).json()
    assert saved['status'] == 'processed' and len(saved['claim_ids']) == 1
    assert saved['transcripts'] == note['transcripts']
    assert saved['claims'][0]['actor']['id'] == person
    assert saved['claims'][0]['status'] == 'draft'
    assert owner.post(base+'/recovered-captures',json=payload).json()['duplicate']
    assert owner.get(path).json()['claim_ids'] == saved['claim_ids']
    changed = copy.deepcopy(payload);changed['transcript'] = 'Packing is pending'
    assert owner.post(base+'/recovered-captures',json=changed).status_code == 409


def test_import_with_audio_and_text_requires_audio_before_extraction(monkeypatch):
    owner, org, _ = account()
    team, recorded = historical_team(owner, org)
    person = owner.get('/auth/session').json()['user']['id']
    assign(owner, org, team, [person],supervisor_id=person)
    base = f'/organizations/{org}'
    payload = recovery_body(team,person,recorded)
    payload.update(transcript='Packing complete',audio_expected=True)
    owner.headers['X-Shift-ID'] = team['shift_id']
    result = owner.post(base+'/recovered-captures',json=payload)
    assert result.status_code == 201,result.text
    note = result.json()['note']
    def never_extract(*args,**kwargs):raise AssertionError('Original audio must be retained before inference')
    monkeypatch.setattr(providers,'extract',never_extract)
    assert owner.post(base+'/notes/'+note['id']+'/process',json={}).status_code == 409
    assert owner.put(result.json()['upload_url'],content=wav()).status_code == 200
    assert owner.get(base+'/notes/'+note['id']).json()['transcripts'] == note['transcripts']


def test_strict_pilot_policy_blocks_new_and_recovered_capture_until_owner_choice(monkeypatch):
    monkeypatch.setenv('SHIFTPROOF_REQUIRE_DATA_POLICY','true')
    owner, org, _ = account()
    team = team_shift(owner, org, 'POLICY')
    old, recorded = historical_team(owner, org)
    me = owner.get('/auth/session').json()['user']['id']
    assign(owner, org, old, [me],supervisor_id=me)
    base = f'/organizations/{org}'
    ordinary = {'batch_id':team['work_item'],'shift_id':team['shift_id'],
                'recorded_at':datetime.now(timezone.utc).isoformat(),'idempotency_key':'strict-policy-capture'}
    recovered = recovery_body(old,me,recorded)
    before = owner.get(base+'/workspace').json()
    assert before['data_mode'] == 'unconfigured' and not before['capture_policy_ready']
    assert owner.post(base+'/notes',json=ordinary).status_code == 409
    assert owner.post(base+'/recovered-captures',json=recovered).status_code == 409
    assert owner.get(base+'/export').json()['notes'] == {}
    selected = owner.put(base+'/pilot-policy',json={'data_classification':'fictional','retention_days':30})
    assert selected.status_code == 200,selected.text
    after = owner.get(base+'/workspace').json()
    assert after['data_mode'] == 'fictional' and after['capture_policy_ready']
    assert owner.post(base+'/notes',json=ordinary).status_code == 201
    assert owner.post(base+'/recovered-captures',json=recovered).status_code == 201


def test_saved_policy_round_trips_without_internal_fields():
    owner, org, _ = account()
    path = f'/organizations/{org}/pilot-policy'
    policy = {'data_classification': 'fictional', 'retention_days': 45}
    assert owner.put(path, json=policy).status_code == 200
    saved = owner.get(path).json()['policy']
    assert 'mode' not in saved
    assert saved['retention_days'] == 45
    saved['retention_days'] = 60
    assert owner.put(path, json=saved).status_code == 200
    assert owner.get(path).json()['policy']['retention_days'] == 60
    assert owner.put(path, json={**saved, 'mode': 'real'}).status_code == 422


def test_real_policy_capture_does_not_enable_free_transcription_extraction_or_playback(monkeypatch):
    from shiftproof.config import settings
    monkeypatch.setenv('SHIFTPROOF_REQUIRE_DATA_POLICY','true')
    monkeypatch.setenv('SHIFTPROOF_BUSINESS_PROVIDER_APPROVED','false')
    monkeypatch.setenv('GEMINI_ACCOUNT_TIER','free')
    monkeypatch.setenv('GNANI_ACCOUNT_TIER','free')
    settings.cache_clear()
    owner, org, _ = account()
    team = team_shift(owner, org, 'REAL')
    base = f'/organizations/{org}'
    selected = owner.put(base+'/pilot-policy',json={'data_classification':'real','retention_days':30,
        'recording_consent':True,'factory_approval':True,'provider_terms_approved':True,'spending_cap_confirmed':True})
    assert selected.status_code == 200,selected.text
    owner.headers['X-Shift-ID'] = team['shift_id']
    def forbidden(*args,**kwargs):raise AssertionError('Free providers must never receive real factory data')
    monkeypatch.setattr(providers,'extract',forbidden)
    monkeypatch.setattr(providers,'transcribe',forbidden)
    monkeypatch.setattr(providers,'synthesize',forbidden)
    ordinary = {'batch_id':team['work_item'],'shift_id':team['shift_id'],
                'recorded_at':datetime.now(timezone.utc).isoformat(),'idempotency_key':'real-audio-policy-capture'}
    result = owner.post(base+'/notes',json=ordinary)
    assert result.status_code == 201,result.text
    note_id = result.json()['note']['id']
    assert owner.put(result.json()['upload_url'],content=wav()).status_code == 200
    assert owner.post(base+'/notes/'+note_id+'/process',json={'transcribe_only':True}).status_code == 202
    saved = owner.get(base+'/notes/'+note_id).json()
    assert saved['status'] == 'failed' and saved['error_category'] == 'real_data_provider_unapproved'
    assert saved['has_audio'] and saved['transcripts'] == []
    assert owner.post(base+'/notes/'+note_id+'/transcript',json={'transcript':'Quality check pending'}).status_code == 200
    assert owner.post(base+'/notes/'+note_id+'/process',json={}).status_code == 202
    saved = owner.get(base+'/notes/'+note_id).json()
    assert saved['status'] == 'manual_review' and saved['error_category'] == 'real_data_provider_unapproved'
    assert saved['transcripts'][-1]['text'] == 'Quality check pending' and saved['claim_ids'] == []
    state = owner.get(base+'/workspace').json()
    speech = owner.post(base+'/speech',json={'batch_id':team['work_item'],'kind':'handover','expected_version':state['version']})
    assert speech.status_code == 503,speech.text
    assert 'Real workplace data is blocked' in speech.json()['detail']
