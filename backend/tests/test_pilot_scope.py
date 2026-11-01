from audio_fixture import pcm_frames
"""Real HTTP permission checks for dated shifts and assigned manufacturing work."""
import io
import wave
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from shiftproof.api import app
from shiftproof import identity, providers
from test_organizations import account
from test_employee_auth import invitation, activate


def team_shift(owner, org, prefix='A', *, starts=None, ends=None):
    base = f'/organizations/{org}'
    location = owner.post(base+'/locations', json={'name': 'Location '+prefix})
    assert location.status_code == 201, location.text
    location_id = location.json()['id']
    team = owner.post(base+'/teams', json={'name': 'Team '+prefix, 'location_id': location_id})
    assert team.status_code == 201, team.text
    team_id = team.json()['id']
    key = 'BATCH-'+prefix
    work = owner.post(base+'/work-items', json={'id': key, 'name': 'Cartons '+prefix, 'location_id': location_id, 'team_id': team_id})
    assert work.status_code == 201, work.text
    current = datetime.now(timezone.utc)
    shift = owner.post(base+'/shift-occurrences', json={'name': 'Shift '+prefix, 'location_id': location_id, 'team_id': team_id,
                       'starts_at': (starts or current-timedelta(hours=1)).isoformat(), 'ends_at': (ends or current+timedelta(hours=3)).isoformat()})
    assert shift.status_code == 201, shift.text
    return {'location_id': location_id, 'team_id': team_id, 'work_item': key, 'shift_id': shift.json()['id']}


def assign(owner, org, team, user_ids, supervisor_id=None, work_items=None):
    response = owner.put(f'/organizations/{org}/shift-occurrences/{team["shift_id"]}/assignments', json={
        'user_ids': user_ids, 'supervisor_id': supervisor_id, 'work_item_ids': work_items if work_items is not None else [team['work_item']]})
    assert response.status_code == 200, response.text
    return response


def email_member(owner, org, email, role='operator'):
    member, own_org, _ = account(email=email)
    inv = owner.post(f'/organizations/{org}/invitations', json={'name': 'Pilot Member', 'email': email, 'role': role}).json()
    response = member.post('/invitations/accept', json={'token': inv['join_path'].split('/')[-1]})
    assert response.status_code == 200, response.text
    return member, member.get('/auth/session').json()['user']['id'], own_org


def create_note(client, org, team, key='pilot-note', transcript=None, recorded_at=None):
    client.headers['X-Shift-ID'] = team['shift_id']
    response = client.post(f'/organizations/{org}/notes', json={
        'batch_id': team['work_item'], 'shift_id': team['shift_id'],
        'recorded_at': (recorded_at or datetime.now(timezone.utc)).isoformat(), 'idempotency_key': key})
    assert response.status_code == 201, response.text
    note_id = response.json()['note']['id']
    if transcript:
        response = client.post(f'/organizations/{org}/notes/{note_id}/transcript', json={'transcript': transcript})
        assert response.status_code == 200, response.text
    return note_id


def wav():
    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(16000)
        handle.writeframes(pcm_frames(16000))
    return output.getvalue()


def test_employee_no_assignment_sees_empty_work_then_only_assigned_team():
    owner, org, _ = account()
    a = team_shift(owner, org, 'A'); b = team_shift(owner, org, 'B')
    worker, _ = activate(invitation(owner, org))
    me = worker.get('/auth/session').json()['user']['id']
    base = f'/organizations/{org}'
    empty = worker.get(base+'/workspace')
    assert empty.status_code == 200, empty.text
    assert empty.json()['batches'] == [] and empty.json()['notes'] == []
    assert empty.json()['assignment_required']
    assert worker.get(base+'/operations').json()['shifts'] == []
    assert worker.get(base+'/members').status_code == 403
    assert worker.get(base+'/export').status_code == 403
    assert worker.get(base+'/workspace', params={'shift_id': a['shift_id']}).status_code == 404
    assign(owner, org, a, [me])
    workspace = worker.get(base+'/workspace').json()
    assert not workspace['assignment_required']
    assert [row['id'] for row in workspace['batches']] == [a['work_item']]
    assert [row['id'] for row in workspace['allowed_shifts']] == [a['shift_id']]
    assert worker.get(base+'/workspace', params={'shift_id': b['shift_id']}).status_code == 404


def test_cross_team_source_audio_jobs_questions_and_directory_are_private(monkeypatch):
    owner, org, _ = account()
    a = team_shift(owner, org, 'A'); b = team_shift(owner, org, 'B')
    worker_a, _ = activate(invitation(owner, org, 'EMP-A'))
    worker_b, _ = activate(invitation(owner, org, 'EMP-B'))
    id_a = worker_a.get('/auth/session').json()['user']['id']; id_b = worker_b.get('/auth/session').json()['user']['id']
    assign(owner, org, a, [id_a]); assign(owner, org, b, [id_b])
    base = f'/organizations/{org}'
    note_id = create_note(worker_a, org, a)
    path = base+'/notes/'+note_id
    assert worker_a.put(path+'/audio', content=wav(), headers={'Content-Type': 'audio/wav'}).status_code == 200
    monkeypatch.setattr(providers, 'transcribe', lambda audio: ('Packing complete', 'controlled-prisma-test'))
    response = worker_a.post(path+'/process', json={'transcribe_only': True})
    assert response.status_code == 202, response.text
    job_id = response.json()['job_id']
    worker_b.headers['X-Shift-ID'] = b['shift_id']
    for suffix in ('', '/audio'):
        assert worker_b.get(path+suffix).status_code == 404
    assert worker_b.get(base+'/jobs/'+job_id).status_code == 404
    assert worker_b.post(path+'/process', json={}).status_code == 404
    assert worker_b.post(base+'/questions', json={'batch_id': a['work_item'], 'question': 'What is pending?'}).status_code == 404
    assert worker_b.get(base+'/export').status_code == 403
    assert worker_b.get(base+'/workspace').json()['notes'] == []
    directory = worker_b.get(base+'/directory').json()
    assert {row['id'] for row in directory} == {id_b}
    assert all(set(row) == {'id', 'name', 'role'} for row in directory)
    owner.headers['X-Shift-ID'] = a['shift_id']
    assert owner.get(path+'/audio').content == wav()
    assert owner.get(base+'/jobs/'+job_id).status_code == 200
    assert 'lease_token' not in owner.get(base+'/jobs/'+job_id).json()


def test_supervisor_assignment_limits_work_and_does_not_grant_people_access():
    owner, org, _ = account()
    a = team_shift(owner, org, 'A'); b = team_shift(owner, org, 'B')
    supervisor, person, _ = email_member(owner, org, 'supervisor@example.com', 'supervisor')
    base = f'/organizations/{org}'
    body = {'id': 'SUP-WORK', 'name': 'Supervisor batch', 'location_id': a['location_id'], 'team_id': a['team_id']}
    assert supervisor.post(base+'/work-items', json=body).status_code == 403
    assign(owner, org, a, [person], supervisor_id=person)
    assert supervisor.post(base+'/work-items', json=body).status_code == 201
    body.update(id='OTHER-WORK', location_id=b['location_id'], team_id=b['team_id'])
    assert supervisor.post(base+'/work-items', json=body).status_code == 403
    assert supervisor.get(base+'/members').status_code == 403
    assert supervisor.get(base+'/access-events').status_code == 403
    assert supervisor.get(base+'/export').status_code == 403
    assert supervisor.post(base+'/invitations', json={'email': 'new@example.com'}).status_code == 403
    assert supervisor.post(base+'/worker-invitations', json={'name': 'Worker', 'employee_id': 'STAFF-1'}).status_code == 403
    assert supervisor.put(base+'/shift-occurrences/'+b['shift_id']+'/assignments', json={'user_ids': [person]}).status_code == 404


def test_reassignment_blocks_draft_upload_and_membership_removal_revokes_session():
    owner, org, _ = account()
    a = team_shift(owner, org, 'A')
    worker, activated = activate(invitation(owner, org))
    person = worker.get('/auth/session').json()['user']['id']
    assign(owner, org, a, [person])
    note_id = create_note(worker, org, a)
    assign(owner, org, a, [])
    path = f'/organizations/{org}/notes/{note_id}'
    assert worker.put(path+'/audio', content=wav()).status_code == 404
    assert worker.post(path+'/process', json={}).status_code == 404
    assert owner.delete(f'/organizations/{org}/members/{person}').status_code == 200
    assert worker.get('/auth/session').status_code == 401
    owner.headers['X-Shift-ID'] = a['shift_id']
    recovery = owner.post(path+'/recover', json={'action': 'cancel', 'reason': 'Worker left; recording was never uploaded'})
    assert recovery.status_code == 200, recovery.text
    assert owner.get(path).json()['status'] == 'discarded'
    assert owner.get(path).json()['actor']['id'] == person


def test_shift_assignment_rejects_outsiders_other_team_items_and_invalid_dates():
    owner, org, _ = account()
    outsider, _, _ = account(email='outsider@example.com')
    outsider_id = outsider.get('/auth/session').json()['user']['id']
    a = team_shift(owner, org, 'A'); b = team_shift(owner, org, 'B')
    base = f'/organizations/{org}'
    assert owner.put(base+'/shift-occurrences/'+a['shift_id']+'/assignments', json={'user_ids': [outsider_id]}).status_code == 422
    me = owner.get('/auth/session').json()['user']['id']
    assert owner.put(base+'/shift-occurrences/'+a['shift_id']+'/assignments', json={'user_ids': [me], 'work_item_ids': [b['work_item']]}).status_code == 422
    now = datetime.now(timezone.utc)
    body = {'name': 'Invalid', 'location_id': a['location_id'], 'team_id': a['team_id'], 'starts_at': now.isoformat(), 'ends_at': (now-timedelta(hours=1)).isoformat()}
    assert owner.post(base+'/shift-occurrences', json=body).status_code == 422
    body['ends_at'] = (now+timedelta(hours=25)).isoformat()
    assert owner.post(base+'/shift-occurrences', json=body).status_code == 422
    body['starts_at'] = now.replace(tzinfo=None).isoformat()
    assert owner.post(base+'/shift-occurrences', json=body).status_code == 422


def test_scoped_handover_version_is_unchanged_by_another_team():
    owner, org, _ = account()
    a = team_shift(owner, org, 'A'); b = team_shift(owner, org, 'B')
    owner.headers['X-Shift-ID'] = a['shift_id']
    base = f'/organizations/{org}'
    before = owner.get(base+'/workspace').json()['version']
    create_note(owner, org, b, key='other-team-report')
    owner.headers['X-Shift-ID'] = a['shift_id']
    assert owner.get(base+'/workspace').json()['version'] == before


def test_overnight_shift_and_late_capture_preserve_original_time():
    owner, org, _ = account()
    current = datetime.now(timezone.utc)
    team = team_shift(owner, org, 'NIGHT', starts=current-timedelta(hours=10), ends=current-timedelta(hours=2))
    recorded = current-timedelta(hours=3)
    note_id = create_note(owner, org, team, recorded_at=recorded)
    row = owner.get(f'/organizations/{org}/notes/{note_id}').json()
    assert row['late_submission'] is True
    assert datetime.fromisoformat(row['recorded_at']) == recorded


def test_incoming_worker_can_read_outgoing_evidence_but_cannot_record_as_outgoing():
    owner, org, _ = account()
    current = datetime.now(timezone.utc)
    a = team_shift(owner, org, 'A', starts=current-timedelta(hours=2), ends=current+timedelta(hours=1))
    base = f'/organizations/{org}'
    incoming = owner.post(base+'/shift-occurrences', json={'name': 'Incoming', 'location_id': a['location_id'], 'team_id': a['team_id'],
        'starts_at': (current+timedelta(hours=1)).isoformat(), 'ends_at': (current+timedelta(hours=9)).isoformat()}).json()
    b = {**a, 'shift_id': incoming['id']}
    worker, _ = activate(invitation(owner, org))
    worker_id = worker.get('/auth/session').json()['user']['id']
    owner_id = owner.get('/auth/session').json()['user']['id']
    assign(owner, org, a, [owner_id], supervisor_id=owner_id)
    assign(owner, org, b, [worker_id, owner_id], supervisor_id=owner_id)
    assert owner.post(base+'/shift-occurrences/'+a['shift_id']+'/incoming', json={'incoming_shift_id': b['shift_id'], 'reason': 'Incoming team accepts outstanding work'}).status_code == 200
    note_id = create_note(owner, org, a, transcript='Quality remains pending')
    worker.headers['X-Shift-ID'] = a['shift_id']
    assert worker.get(base+'/notes/'+note_id).status_code == 200
    response = worker.post(base+'/notes', json={'batch_id': a['work_item'], 'shift_id': a['shift_id'], 'recorded_at': current.isoformat(), 'idempotency_key': 'wrong-outgoing-shift'})
    assert response.status_code == 403


def process_claim(client, org, team, monkeypatch, *, text='Packing complete', prop='packing', value='complete', key='processed-note'):
    note_id = create_note(client, org, team, key=key, transcript=text)
    def extract(transcript, batch_id, reserve, context):
        return providers.validate_extraction({'claims': [{'property': prop, 'value': value, 'excerpt': text}]}, transcript, context), 'controlled-extraction-test'
    monkeypatch.setattr(providers, 'extract', extract)
    response = client.post(f'/organizations/{org}/notes/{note_id}/process', json={})
    assert response.status_code == 202, response.text
    saved = client.get(f'/organizations/{org}/notes/{note_id}').json()
    assert saved['claim_ids'], saved
    return saved


def test_real_shift_voice_acknowledgement_version_and_owner_recipient_checks(monkeypatch):
    owner, org, _ = account()
    team = team_shift(owner, org)
    worker, _ = activate(invitation(owner, org))
    person = worker.get('/auth/session').json()['user']['id']
    assign(owner, org, team, [person])
    process_claim(owner, org, team, monkeypatch)
    worker.headers['X-Shift-ID'] = team['shift_id']
    base = f'/organizations/{org}'
    path = base+'/shifts/'+team['shift_id']+'/acknowledgements'
    version = worker.get(base+'/workspace').json()['version']
    voice = worker.post(path+'/audio', content=wav(), headers={'Content-Type': 'audio/wav'})
    assert voice.status_code == 201, voice.text
    assert voice.json()['version'] == version
    body = {'expected_version': version, 'readback': 'Packing reported complete; quality still needs review', 'audio_id': voice.json()['audio_id']}
    ack = worker.post(path, json=body)
    assert ack.status_code == 200, ack.text
    assert worker.post(path, json=body).json()['id'] == ack.json()['id']
    assert owner.post(path, json={'expected_version': version, 'readback': 'Owner without a recipient assignment'}).status_code == 403
    snapshot_path = base+'/shifts/'+team['shift_id']+'/snapshots/'+str(version)
    snapshot = worker.get(snapshot_path).json()
    assert snapshot['version'] == version
    assert worker.get(path+'/audio/'+voice.json()['audio_id']).content == wav()
    create_note(owner, org, team, key='new-material-report')
    assert worker.post(path, json=body).status_code == 409
    latest = worker.get(base+'/workspace').json()['version']
    assert latest != version
    assert worker.get(snapshot_path).json() == snapshot
    assert not worker.get(base+'/workspace').json()['acknowledgements'][0]['current']

    process_claim(owner, org, team, monkeypatch, key='another-reviewed-report')
    # Cancel the earlier empty upload so the audio-version check is reached.
    pending = next(n for n in owner.get(base+'/workspace').json()['notes'] if n['status']=='awaiting_upload')
    assert owner.post(base+'/notes/'+pending['id']+'/recover', json={'action':'cancel','reason':'Empty duplicate capture'}).status_code == 200
    latest = worker.get(base+'/workspace').json()['version']
    wrong_voice = worker.post(path, json={**body,'expected_version':latest})
    assert wrong_voice.status_code == 409
    assert 'Record acknowledgement for this handover version' in wrong_voice.text


def test_snapshot_read_cannot_restore_work_removed_from_current_assignment(monkeypatch):
    owner, org, _ = account()
    team = team_shift(owner, org)
    base = f'/organizations/{org}'
    second = {**team, 'work_item': 'BATCH-SECRET'}
    assert owner.post(base+'/work-items', json={'id': second['work_item'], 'name': 'Restricted order', 'location_id': team['location_id'], 'team_id': team['team_id']}).status_code == 201
    worker, _ = activate(invitation(owner, org))
    person = worker.get('/auth/session').json()['user']['id']
    assign(owner, org, team, [person], work_items=[team['work_item'], second['work_item']])
    process_claim(owner, org, team, monkeypatch, key='public-order-report')
    secret = process_claim(owner, org, second, monkeypatch, text='Confidential batch quantity', prop='quantity', value=75, key='restricted-order-report')
    worker.headers['X-Shift-ID'] = team['shift_id']
    version = worker.get(base+'/workspace').json()['version']
    response = worker.post(base+'/shifts/'+team['shift_id']+'/acknowledgements', json={'expected_version': version, 'readback': 'Both assigned orders received'})
    assert response.status_code == 200, response.text
    path = base+'/shifts/'+team['shift_id']+'/snapshots/'+str(version)
    snapshot = worker.get(path)
    assert snapshot.status_code == 200
    assign(owner, org, team, [person], work_items=[team['work_item']])
    assert worker.get(base+'/notes/'+secret['id']).status_code == 404
    assert [b['id'] for b in worker.get(base+'/workspace').json()['batches']] == [team['work_item']]
    restricted = worker.get(path)
    assert restricted.status_code in (403, 404), 'An immutable snapshot containing revoked work must not be disclosed through historical access'


def test_acknowledgement_audio_respects_narrowed_assignment():
    owner, org, _ = account()
    team = team_shift(owner, org)
    base = f'/organizations/{org}'
    second_id = 'BATCH-SECRET'
    assert owner.post(base+'/work-items', json={'id': second_id, 'name': 'Restricted order', 'location_id': team['location_id'], 'team_id': team['team_id']}).status_code == 201
    worker, _ = activate(invitation(owner, org))
    person = worker.get('/auth/session').json()['user']['id']
    assign(owner, org, team, [person], work_items=[team['work_item'], second_id])
    path = base+'/shifts/'+team['shift_id']+'/acknowledgements/audio'
    voice = worker.post(path, content=wav(), headers={'Content-Type':'audio/wav'})
    assert voice.status_code == 201, voice.text
    audio_id = voice.json()['audio_id']
    assert worker.get(path+'/'+audio_id).status_code == 200
    assign(owner, org, team, [person], work_items=[team['work_item']])
    assert worker.get(path+'/'+audio_id).status_code in (403,404), 'Voice receipts must not bypass current evidence scope'


def test_current_real_shift_clarification_and_stale_reply_replay(monkeypatch):
    owner, org, _ = account()
    team = team_shift(owner, org)
    process_claim(owner, org, team, monkeypatch, text='Quality pending', prop='quality', value='pending')
    base = f'/organizations/{org}'
    view = owner.get(base+'/workspace').json()
    question = view['batches'][0]['clarification']
    current = datetime.now(timezone.utc).isoformat()
    fresh = {'batch_id': team['work_item'], 'shift_id': team['shift_id'], 'recorded_at': current,
             'idempotency_key': 'fresh-context-reply', 'clarification_ref': question['id'], 'clarification_version': view['version']}
    valid = owner.post(base+'/notes', json=fresh)
    assert valid.status_code == 201, valid.text
    saved = valid.json()['note']
    assert saved['clarification_context']['version'] == view['version']
    stale = {**fresh, 'idempotency_key': 'old-context-offline-reply', 'clarification_context': {**question, 'version': view['version']}}
    accepted = owner.post(base+'/notes', json=stale)
    assert accepted.status_code == 201, accepted.text
    note_id = accepted.json()['note']['id']
    replay = owner.post(base+'/notes', json=stale)
    assert replay.status_code == 201, replay.text
    assert replay.json()['note']['id'] == note_id
    assert replay.json()['note']['clarification_context']['text'] == question['text']
    assert owner.post(base+'/notes/'+note_id+'/transcript', json={'transcript': 'Haan, clear ho gaya'}).status_code == 200
    assert owner.post(base+'/notes/'+note_id+'/process', json={}).status_code == 202
    reviewed = owner.get(base+'/notes/'+note_id).json()
    assert reviewed['status'] == 'manual_review' and reviewed['error_category'] == 'stale_clarification'
    assert reviewed['claim_ids'] == []


def test_closed_snapshot_survives_late_addendum_and_capture_id_rejects_other_shift(monkeypatch):
    owner, org, _ = account()
    team = team_shift(owner, org)
    base = f'/organizations/{org}'
    owner_id = owner.get('/auth/session').json()['user']['id']
    now = datetime.now(timezone.utc)
    response = owner.post(base+'/shift-occurrences', json={'name': 'Next shift', 'location_id': team['location_id'], 'team_id': team['team_id'], 'starts_at': (now+timedelta(hours=3)).isoformat(), 'ends_at': (now+timedelta(hours=11)).isoformat()})
    assert response.status_code == 201
    incoming = {**team, 'shift_id': response.json()['id']}
    assign(owner, org, team, [owner_id], supervisor_id=owner_id)
    assign(owner, org, incoming, [owner_id], supervisor_id=owner_id)
    assert owner.post(base+'/shift-occurrences/'+team['shift_id']+'/incoming', json={'incoming_shift_id': incoming['shift_id'], 'reason': 'Next supervisor assigned'}).status_code == 200
    first = process_claim(owner, org, team, monkeypatch)
    closed = owner.post(base+'/shift-occurrences/'+team['shift_id']+'/close', json={'reason': 'Outgoing review complete'})
    assert closed.status_code == 200, closed.text
    snapshot_id = closed.json()['snapshot_id']
    snapshot = owner.get(base+'/export').json()['snapshots'][snapshot_id]
    addendum = create_note(owner, org, team, key='late-offline-addendum', recorded_at=now)
    assert owner.get(base+'/notes/'+addendum).json()['addendum'] is True
    assert owner.get(base+'/export').json()['snapshots'][snapshot_id] == snapshot
    # The same capture cannot be silently moved to a different shift on retry.
    # Use a second overlapping occurrence so its timestamp is valid independently.
    overlap = owner.post(base+'/shift-occurrences', json={'name': 'Overlapping team', 'location_id': team['location_id'], 'team_id': team['team_id'], 'starts_at': (now-timedelta(hours=1)).isoformat(), 'ends_at': (now+timedelta(hours=7)).isoformat()}).json()
    wrong = owner.post(base+'/notes', json={'batch_id': team['work_item'], 'shift_id': overlap['id'], 'recorded_at': now.isoformat(), 'idempotency_key': 'late-offline-addendum'})
    assert wrong.status_code == 409


def test_owner_reviewer_retains_coordination_but_operator_owner_cannot_review(monkeypatch):
    owner, org, _ = account()
    team = team_shift(owner, org)
    note = process_claim(owner, org, team, monkeypatch, text='Quality cleared', prop='quality', value='cleared')
    base = f'/organizations/{org}'
    person = owner.get('/auth/session').json()['user']['id']
    assert owner.put(base+'/members/'+person, json={'access': 'owner', 'role': 'quality'}).status_code == 200
    profile = owner.get(base).json()
    assert profile['capabilities']['manage_work'] and profile['capabilities']['clear_holds']
    assert owner.post(base+'/work-items', json={'id': 'OWNER-REVIEWER', 'name': 'Owner coordinator', 'location_id': team['location_id'], 'team_id': team['team_id']}).status_code == 201
    assert owner.put(base+'/members/'+person, json={'access': 'owner', 'role': 'operator'}).status_code == 200
    profile = owner.get(base).json()
    assert profile['capabilities']['manage_people']
    assert not profile['capabilities']['manage_work'] and not profile['capabilities']['clear_holds']
    version = owner.get(base+'/workspace').json()['version']
    assert owner.post(base+'/claims/'+note['claim_ids'][0]+'/resolve', json={'expected_version': version, 'action': 'confirm', 'reason': 'Ownership alone is insufficient'}).status_code == 403
    assert owner.post(base+'/work-items', json={'id': 'IMPLICIT', 'name': 'Implicit operational authority'}).status_code == 403


def test_limited_or_undesignated_supervisor_cannot_expand_assignment_or_close():
    owner, org, _ = account()
    team = team_shift(owner, org)
    base = f'/organizations/{org}'
    second_id = 'BATCH-RESTRICTED'
    assert owner.post(base+'/work-items', json={'id':second_id,'name':'Other work','location_id':team['location_id'],'team_id':team['team_id']}).status_code == 201
    supervisor, person, _ = email_member(owner, org, 'limited@example.com', 'supervisor')
    assign(owner, org, team, [person], supervisor_id=person, work_items=[team['work_item']])
    path = base+'/shift-occurrences/'+team['shift_id']
    expand = {'user_ids':[person],'supervisor_id':person,'work_item_ids':[]}
    assert supervisor.put(path+'/assignments', json=expand).status_code == 403
    assert supervisor.post(path+'/close', json={'reason':'Cannot close unassigned work'}).status_code == 403
    assert supervisor.post(path+'/incoming', json={'incoming_shift_id':team['shift_id'],'reason':'Cannot coordinate restricted scope'}).status_code == 403
    me = owner.get('/auth/session').json()['user']['id']
    assign(owner, org, team, [person,me], supervisor_id=me, work_items=[])
    # Full visibility alone does not replace explicit designation as coordinator.
    assert supervisor.put(path+'/assignments', json=expand).status_code == 403
    assert supervisor.post(path+'/close', json={'reason':'Only designated coordinator closes'}).status_code == 403


def test_owner_reviewers_can_be_explicit_outgoing_and_incoming_coordinators():
    owner, org, _ = account()
    second, second_id, _ = email_member(owner, org, 'second-owner@example.com', 'quality')
    base = f'/organizations/{org}'
    owner_id = owner.get('/auth/session').json()['user']['id']
    assert owner.put(base+'/members/'+second_id, json={'access':'owner','role':'quality'}).status_code == 200
    assert owner.put(base+'/members/'+owner_id, json={'access':'owner','role':'quality'}).status_code == 200
    outgoing = team_shift(owner, org)
    current = datetime.now(timezone.utc)
    response = owner.post(base+'/shift-occurrences', json={'name':'Next owner review','location_id':outgoing['location_id'],'team_id':outgoing['team_id'],
        'starts_at':(current+timedelta(hours=3)).isoformat(),'ends_at':(current+timedelta(hours=11)).isoformat()})
    assert response.status_code == 201
    incoming = {**outgoing,'shift_id':response.json()['id']}
    assign(owner, org, outgoing, [owner_id], supervisor_id=owner_id)
    assign(owner, org, incoming, [second_id], supervisor_id=second_id)
    assert owner.post(base+'/shift-occurrences/'+outgoing['shift_id']+'/incoming', json={'incoming_shift_id':incoming['shift_id'],'reason':'Named owner reviewer accepts next shift'}).status_code == 200
    result = owner.post(base+'/shift-occurrences/'+outgoing['shift_id']+'/close', json={'reason':'Incoming coordinator has explicit authority'})
    assert result.status_code == 200, result.text
