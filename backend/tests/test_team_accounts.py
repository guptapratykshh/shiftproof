"""Account onboarding, invitation lifecycle and preserved organization evidence."""
import sqlite3
import time
from fastapi.testclient import TestClient
from shiftproof.api import app
from shiftproof import identity, providers
from test_organizations import account, item, state, extract, resolve


def test_minimal_signup_defaults_confirmation_and_existing_settings():
    client = TestClient(app)
    body = dict(name='Meera', email='meera@example.com', password='an-example-long-password',
                confirm_password='not-the-same-password', industry='manufacturing', timezone='Europe/London')
    assert client.post('/auth/signup', json=body).status_code == 422
    with identity.database() as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
    body['confirm_password'] = body['password']
    response = client.post('/auth/signup', json=body)
    assert response.status_code == 201, response.text
    org = client.get('/auth/session').json()['organizations'][0]
    assert (org['name'], org['timezone'], org['access'], org['role']) == ('Meera’s workspace', 'Europe/London', 'owner', 'supervisor')
    assert state(client, org['id'])['notes'] == []
    client.headers['X-CSRF-Token'] = response.json()['csrf_token']
    base = '/organizations/' + org['id']
    assert client.put(base+'/settings', json={'name': 'Meera Works', 'timezone': 'Asia/Kolkata'}).status_code == 200
    assert client.get(base).json()['name'] == 'Meera Works'
    assert client.put(base+'/settings', json={'name': 'Ignored', 'timezone': 'Invalid/Zone'}).status_code == 422
    assert client.get(base).json()['name'] == 'Meera Works'
    assert client.get(base+'/access-events').json()[0]['action'] == 'organization.updated'


def test_activation_link_replacement_revocation_and_status_history():
    owner, org, _ = account()
    base = f'/organizations/{org}/invitations'
    first = owner.post(base, json={'name': 'Shift Worker', 'email': 'worker@example.com', 'role': 'operator'}).json()
    response = owner.get('/invitations/' + first['join_path'].split('/')[-1])
    assert response.headers['cache-control'] == 'no-store'
    public = response.json()
    assert public['name'] == 'Shift Worker' and public['organization_name'] == 'Factory One'
    assert owner.post(base, json={'email': 'worker@example.com'}).status_code == 409
    replaced = owner.post(base+'/'+first['id']+'/replace', json={})
    assert replaced.status_code == 201
    second = replaced.json()
    assert owner.get('/invitations/'+first['join_path'].split('/')[-1]).status_code == 410
    rows = owner.get(base).json()
    assert {r['status'] for r in rows} == {'pending', 'revoked'}
    assert all('token' not in r and 'join_path' not in r for r in rows)
    assert owner.delete(base+'/'+second['id']).status_code == 200
    assert owner.get('/invitations/'+second['join_path'].split('/')[-1]).status_code == 410
    blocked = TestClient(app).post('/auth/signup', json={'name': 'Worker', 'email': 'worker@example.com', 'password': 'another-example-password', 'invitation_token': second['join_path'].split('/')[-1]})
    assert blocked.status_code == 410
    with identity.database() as db:
        assert not db.execute('SELECT id FROM users WHERE email=?', ('worker@example.com',)).fetchone()
    assert owner.post(base+'/'+second['id']+'/replace', json={}).status_code == 409
    third = owner.post(base, json={'email': 'worker@example.com', 'role': 'supervisor'}).json()
    with identity.database() as db:
        db.execute('UPDATE invitations SET expires=? WHERE id=?', (time.time()-1, third['id']))
    assert owner.get(base).json()[0]['status'] == 'expired'
    assert owner.post(base+'/'+third['id']+'/replace', json={}).status_code == 201
    actions = {e['action'] for e in owner.get(f'/organizations/{org}/access-events').json()}
    assert {'invitation.created', 'invitation.replaced', 'invitation.revoked'} <= actions


def test_existing_account_activation_permissions_removal_and_other_membership():
    owner, org, _ = account()
    worker, own_org, _ = account(email='worker@example.com')
    invitation = owner.post(f'/organizations/{org}/invitations', json={'name': 'Existing Worker', 'email': 'worker@example.com', 'role': 'operator'}).json()
    token = invitation['join_path'].split('/')[-1]
    assert worker.post('/invitations/accept', json={'token': token, 'role': 'quality'}).status_code == 422
    assert worker.post('/invitations/accept', json={'token': token}).status_code == 200
    user_id = worker.get('/auth/session').json()['user']['id']
    assert worker.get(f'/organizations/{org}/export').status_code == 403
    assert worker.get(f'/organizations/{org}/invitations').status_code == 403
    assert worker.put(f'/organizations/{org}/settings', json={'name': 'Takeover', 'timezone': 'UTC'}).status_code == 403
    assert worker.post(f'/organizations/{org}/work-items', json={'id': 'WORK', 'name': 'Work'}).status_code == 403
    assert owner.put(f'/organizations/{org}/members/{user_id}', json={'access': 'member', 'role': 'supervisor'}).status_code == 200
    # A role alone never grants access to another team's operational work.
    assert worker.post(f'/organizations/{org}/work-items', json={'id': 'WORK', 'name': 'Work'}).status_code == 403
    from test_pilot_scope import team_shift, assign
    assigned = team_shift(owner, org)
    assign(owner, org, assigned, [user_id], supervisor_id=user_id)
    assert worker.post(f'/organizations/{org}/work-items', json={'id': 'WORK', 'name': 'Work', 'team_id': assigned['team_id'], 'location_id': assigned['location_id']}).status_code == 201
    assert owner.get(f'/organizations/{org}/invitations').json()[0]['status'] == 'accepted'
    assert owner.delete(f'/organizations/{org}/invitations/{invitation["id"]}').status_code == 409
    assert owner.delete(f'/organizations/{org}/members/{user_id}').status_code == 200
    assert worker.get(f'/organizations/{org}/export').status_code == 404
    assert worker.get(f'/organizations/{own_org}/workspace').status_code == 200
    assert worker.post('/invitations/accept', json={'token': token}).status_code == 410
    events = owner.get(f'/organizations/{org}/access-events').json()
    assert {'invitation.accepted', 'membership.updated', 'membership.removed'} <= {e['action'] for e in events}
    assert all(e['actor_name'] and e['created_at'] for e in events)


def test_invitation_admin_and_organization_boundaries():
    owner, org, _ = account()
    other, other_org, _ = account(email='other@example.com')
    inv = owner.post(f'/organizations/{org}/invitations', json={'email': 'other@example.com', 'access': 'admin'}).json()
    assert other.post('/invitations/accept', json={'token': inv['join_path'].split('/')[-1]}).status_code == 200
    elevated = owner.post(f'/organizations/{org}/invitations', json={'email': 'administrator@example.com', 'access': 'admin'}).json()
    base = f'/organizations/{org}/invitations/{elevated["id"]}'
    assert other.delete(base).status_code == 403
    assert other.post(base+'/replace', json={}).status_code == 403
    assert other.put(f'/organizations/{org}/settings', json={'name': 'No', 'timezone': 'UTC'}).status_code == 403
    assert other.delete(f'/organizations/{other_org}/invitations/{elevated["id"]}').status_code == 404
    outsider, _, _ = account(email='outsider@example.com')
    for path in ('invitations', 'access-events'):
        assert outsider.get(f'/organizations/{org}/{path}').status_code == 404
    assert outsider.post(base+'/replace', json={}).status_code == 404


def test_legacy_invitation_schema_upgrade_is_additive_and_idempotent():
    path = identity.root() / 'identity.sqlite3'
    token = identity.digest('legacy-invite')
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE invitations(token TEXT PRIMARY KEY,org_id TEXT,email TEXT,access TEXT,role TEXT,expires REAL,used INTEGER DEFAULT 0)')
        db.execute('INSERT INTO invitations VALUES (?,?,?,?,?,?,?)', (token, 'old-org', 'old@example.com', 'member', 'operator', time.time()+3600, 0))
    with identity.database() as db:
        first = dict(db.execute('SELECT * FROM invitations').fetchone())
    with identity.database() as db:
        second = dict(db.execute('SELECT * FROM invitations').fetchone())
    assert first == second and first['id'] and first['token'] == token
    assert first['name'] == '' and first['revoked'] == 0


def test_revision_recovery_preserves_reviewed_claims_and_ack_snapshot(monkeypatch):
    owner, org, _ = account(); item(owner, org)
    original = extract(owner, org, monkeypatch, [{'property': 'quality', 'value': 'pending', 'excerpt': 'Pending'}], text='Pending')
    claim_id = original['claim_ids'][0]
    assert resolve(owner, org, claim_id).status_code == 200
    base = f'/organizations/{org}'
    before = owner.get(base+'/export').json()
    version = before['version']
    assert owner.post(base+'/shifts/shift-B/acknowledgements', json={'expected_version': version, 'readback': 'Quality inspection remains pending'}).status_code == 200
    snapshot = owner.get(base+f'/shifts/shift-B/snapshots/{version}').json()
    def unavailable(*args, **kwargs):
        raise providers.ProviderError('Test extraction outage')
    monkeypatch.setattr(providers, 'extract', unavailable)
    path = base+'/notes/'+original['id']
    revised = owner.post(path+'/revisions', json={'transcript': 'Inspection pending, packing complete', 'expected_version': state(owner, org)['version']})
    assert revised.status_code == 200
    assert owner.post(path+'/process', json={}).status_code == 202
    recovered = owner.post(path+'/review-transcript', json={
        'expected_version': state(owner, org)['version'], 'reason': 'Read the revised source',
        'claims': [{'property': 'packing', 'value': 'complete', 'excerpt': 'packing complete'}]})
    assert recovered.status_code == 200, recovered.text
    after = owner.get(base+'/export').json()
    original_claim = {k: v for k, v in before['claims'][claim_id].items() if not k.startswith('source_review')}
    assert {k: after['claims'][claim_id][k] for k in original_claim} == original_claim
    assert after['claims'][claim_id]['source_review_pending'] is True
    assert after['claims'][claim_id]['source_revision_pending'] == 2
    assert all(after['resolutions'][k] == v for k, v in before['resolutions'].items())
    assert len(after['notes'][original['id']]['transcripts']) == 2
    assert state(owner, org)['batches'][0]['status'] == 'hold'
    assert not state(owner, org)['acknowledgements'][0]['current']
    assert owner.get(base+f'/shifts/shift-B/snapshots/{version}').json() == snapshot
    assert owner.post(path+'/review-transcript', json={'expected_version': state(owner, org)['version'], 'reason': 'Duplicate recovery', 'claims': []}).status_code == 409
