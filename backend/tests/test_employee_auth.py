"""Scoped employee identities, recovery boundaries and legacy identity preservation."""
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
import pytest

from fastapi.testclient import TestClient

from shiftproof.api import app
from shiftproof import identity
from test_organizations import account


PASSWORD = 'worker-example-passphrase'


def invitation(owner, org, employee_id='EMP-1'):
    response = owner.post(f'/organizations/{org}/worker-invitations', json={'name': 'Hindi Worker', 'employee_id': employee_id})
    assert response.status_code == 201, response.text
    return response.json()


def activate(inv, client=None, link_existing=False):
    client = client or TestClient(app)
    response = client.post('/auth/worker/activate', json={'token': inv['join_path'].split('/')[-1], 'password': PASSWORD, 'confirm_password': PASSWORD, 'link_existing': link_existing})
    assert response.status_code == 201, response.text
    client.headers['X-CSRF-Token'] = response.json()['csrf_token']
    return client, response.json()


def test_employee_activation_has_no_fake_email_and_scoped_session():
    owner, org, _ = account()
    inv = invitation(owner, org, 'emp-1')
    public = TestClient(app).get('/invitations/' + inv['join_path'].split('/')[-1]).json()
    assert public['kind'] == 'employee' and public['employee_id'] == 'EMP-1'
    worker, activated = activate(inv)
    session = worker.get('/auth/session').json()
    assert session['user']['email'] is None
    assert session['auth_kind'] == 'employee'
    assert session['scoped_organization_id'] == org
    assert session['capabilities']['create_organization'] is False
    assert session['organizations'][0]['role'] == 'operator'
    assert session['organizations'][0]['capabilities']['export_data'] is False
    with identity.database(write=False) as db:
        user = db.execute('SELECT * FROM users WHERE id=?', (session['user']['id'],)).fetchone()
        assert user['email'] is None and user['password'] is None
        credential = db.execute('SELECT * FROM employee_credentials WHERE org_id=?', (org,)).fetchone()
        assert credential['password'].startswith('$argon2')
    assert worker.post('/organizations', json={'name': 'Unexpected', 'industry': 'manufacturing'}).status_code == 403
    assert worker.post('/auth/worker/activate', json={'token': inv['join_path'].split('/')[-1], 'password': PASSWORD}).status_code == 410
    rows = owner.get(f'/organizations/{org}/worker-invitations').json()
    assert rows[0]['status'] == 'accepted' and 'token' not in rows[0]
    assert owner.post(f'/organizations/{org}/worker-invitations', json={'name': 'Duplicate', 'employee_id': 'EMP-1'}).status_code == 409


def test_same_employee_id_other_org_cannot_cross_and_login_errors_are_generic():
    owner_a, org_a, _ = account()
    owner_b, org_b, _ = account(email='second@example.com')
    worker_a, activated_a = activate(invitation(owner_a, org_a))
    worker_b, activated_b = activate(invitation(owner_b, org_b))
    assert worker_a.get(f'/organizations/{org_b}').status_code == 404
    assert worker_b.get(f'/organizations/{org_a}/workspace').status_code == 404
    login = TestClient(app)
    response = login.post('/auth/worker/login', json={'organization_code': activated_a['organization_code'].lower(), 'employee_id': 'emp-1', 'password': PASSWORD})
    assert response.status_code == 200
    assert response.json()['organization_id'] == org_a
    errors = []
    for code, employee_id, password in [('MISSING', 'EMP-1', PASSWORD), (activated_a['organization_code'], 'UNKNOWN', PASSWORD), (activated_a['organization_code'], 'EMP-1', 'incorrect')]:
        response = login.post('/auth/worker/login', json={'organization_code': code, 'employee_id': employee_id, 'password': password})
        assert response.status_code == 401
        errors.append(response.json())
    assert errors[0] == errors[1] == errors[2]


def test_scoped_employee_reset_does_not_reset_linked_global_account():
    owner, org, _ = account()
    existing, other_org, _ = account(email='existing@example.com')
    identity_before = existing.get('/auth/session').json()['user']['id']
    inv = invitation(owner, org)
    worker, activated = activate(inv, existing, link_existing=True)
    session = worker.get('/auth/session').json()
    assert session['user']['id'] == identity_before
    assert [o['id'] for o in session['organizations']] == [org]
    assert worker.get(f'/organizations/{other_org}/workspace').status_code == 404
    response = owner.post(f'/organizations/{org}/members/{identity_before}/worker-reset', json={})
    assert response.status_code == 201
    first = response.json()['reset_path'].split('/')[-1]
    assert worker.get('/auth/session').status_code == 401
    second = owner.post(f'/organizations/{org}/members/{identity_before}/worker-reset', json={}).json()['reset_path'].split('/')[-1]
    assert TestClient(app).post('/auth/worker/reset', json={'token': first, 'password': 'changed-worker-password'}).status_code == 410
    reset_client = TestClient(app)
    response = reset_client.post('/auth/worker/reset', json={'token': second, 'password': 'changed-worker-password'})
    assert response.status_code == 200
    assert response.json()['organization_id'] == org
    assert reset_client.post('/auth/worker/reset', json={'token': second, 'password': 'changed-worker-password'}).status_code == 410
    email_login = TestClient(app)
    assert email_login.post('/auth/login', json={'email': 'existing@example.com', 'password': 'a-long-test-password'}).status_code == 200
    assert {o['id'] for o in email_login.get('/auth/session').json()['organizations']} == {org, other_org}


def test_worker_links_expiry_replacement_revocation_and_privilege_injection():
    owner, org, _ = account()
    base = f'/organizations/{org}/worker-invitations'
    assert owner.post(base, json={'name': 'Worker', 'employee_id': 'EMP-1', 'role': 'quality'}).status_code == 422
    inv = invitation(owner, org)
    replaced = owner.post(base + '/' + inv['id'] + '/replace', json={})
    assert replaced.status_code == 201
    assert TestClient(app).get('/invitations/' + inv['join_path'].split('/')[-1]).status_code == 410
    second = replaced.json()
    assert owner.delete(base + '/' + second['id']).status_code == 200
    assert owner.post(base + '/' + second['id'] + '/replace', json={}).status_code == 409
    third = invitation(owner, org, 'EMP-2')
    with identity.database() as db:
        db.execute('UPDATE employee_links SET expires=0 WHERE id=?', (third['id'],))
    assert TestClient(app).post('/auth/worker/activate', json={'token': third['join_path'].split('/')[-1], 'password': PASSWORD}).status_code == 410


def test_worker_removal_revokes_sessions_and_retains_employee_id_history():
    owner, org, _ = account()
    worker, activated = activate(invitation(owner, org))
    user_id = worker.get('/auth/session').json()['user']['id']
    assert owner.delete(f'/organizations/{org}/members/{user_id}').status_code == 200
    assert worker.get('/auth/session').status_code == 401
    assert worker.post('/auth/worker/login', json={'organization_code': activated['organization_code'], 'employee_id': 'EMP-1', 'password': PASSWORD}).status_code == 401
    assert owner.post(f'/organizations/{org}/worker-invitations', json={'name': 'New Worker', 'employee_id': 'EMP-1'}).status_code == 409


def test_owner_only_privilege_appointments_and_employee_promotion_requires_email():
    owner, org, _ = account()
    admin, _, _ = account(email='admin@example.com')
    inv = owner.post(f'/organizations/{org}/invitations', json={'email': 'admin@example.com', 'access': 'admin'}).json()
    assert admin.post('/invitations/accept', json={'token': inv['join_path'].split('/')[-1]}).status_code == 200
    for role in ('supervisor', 'quality'):
        assert admin.post(f'/organizations/{org}/invitations', json={'email': role + '@example.com', 'role': role}).status_code == 403
    worker, _ = activate(invitation(owner, org))
    user_id = worker.get('/auth/session').json()['user']['id']
    assert owner.put(f'/organizations/{org}/members/{user_id}', json={'access': 'member', 'role': 'supervisor'}).status_code == 422
    assert admin.post(f'/organizations/{org}/members/{user_id}/worker-reset', json={}).status_code == 403
    assert worker.get(f'/organizations/{org}/members').status_code == 403
    linked = worker.post('/auth/worker/email-account', json={'email': 'worker-new@example.com', 'current_password': PASSWORD, 'password': 'new-global-passphrase'})
    assert linked.status_code == 200, linked.text
    assert linked.json()['recovery_codes'] and not linked.json()['email_verified']
    assert owner.put(f'/organizations/{org}/members/{user_id}', json={'access': 'member', 'role': 'supervisor'}).status_code == 200


def test_email_session_without_membership_has_explicit_safe_state():
    owner, org, _ = account()
    token = owner.post(f'/organizations/{org}/invitations', json={'email': 'worker@example.com'}).json()['join_path'].split('/')[-1]
    worker = TestClient(app)
    response = worker.post('/auth/signup', json={'name': 'Worker', 'email': 'worker@example.com', 'password': PASSWORD, 'invitation_token': token})
    worker.headers['X-CSRF-Token'] = response.json()['csrf_token']
    user_id = worker.get('/auth/session').json()['user']['id']
    owner.delete(f'/organizations/{org}/members/{user_id}')
    session = worker.get('/auth/session').json()
    assert session['organizations'] == [] and session['no_organization_access']
    assert session['capabilities']['create_organization']


def test_pilot_gate_blocks_unapproved_orgs_but_existing_team_invitations_work(monkeypatch):
    owner, org, _ = account()
    token = owner.post(f'/organizations/{org}/invitations', json={'email': 'invited@example.com'}).json()['join_path'].split('/')[-1]
    monkeypatch.setenv('PILOT_SIGNUP_APPROVAL_REQUIRED', 'true')
    monkeypatch.setenv('PILOT_APPROVED_OWNER_EMAILS', 'approved@example.com')
    client = TestClient(app)
    body = {'name': 'Pilot Owner', 'email': 'unapproved@example.com', 'password': PASSWORD}
    assert client.post('/auth/signup', json=body).status_code == 403
    assert owner.post('/organizations', json={'name': 'Another', 'industry': 'manufacturing'}).status_code == 403
    assert client.get('/auth/options').json()['pilot_approval_required']
    body['email'] = 'invited@example.com'; body['invitation_token'] = token
    assert client.post('/auth/signup', json=body).status_code == 201
    body.pop('invitation_token'); body['email'] = 'approved@example.com'
    assert TestClient(app).post('/auth/signup', json=body).status_code == 201


def test_legacy_identity_migration_preserves_ids_hashes_sessions_and_backups():
    path = identity.root() / 'identity.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,password TEXT NOT NULL,recovery TEXT NOT NULL)')
        db.execute('INSERT INTO users VALUES (?,?,?,?,?)', ('old-user', 'old@example.com', 'Original', 'unchanged-hash', '[]'))
        db.execute('CREATE TABLE sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL,csrf TEXT NOT NULL,expires REAL NOT NULL)')
        db.execute('INSERT INTO sessions VALUES (?,?,?,?)', ('old-token', 'old-user', 'old-csrf', time.time()+600))
    with identity.database(write=False) as db:
        user = dict(db.execute('SELECT * FROM users').fetchone())
        session = dict(db.execute('SELECT * FROM sessions').fetchone())
    assert user == {'id': 'old-user', 'email': 'old@example.com', 'name': 'Original', 'password': 'unchanged-hash', 'recovery': '[]'}
    assert session['auth_kind'] == 'email' and session['org_id'] is None
    backups = list((identity.root() / 'backups').glob('identity-before-employees-*.sqlite3'))
    assert len(backups) == 1
    with identity.database(write=False) as db:
        assert db.execute('SELECT id FROM users').fetchone()[0] == 'old-user'
    assert list((identity.root() / 'backups').glob('identity-before-employees-*.sqlite3')) == backups


def test_initialized_identity_reads_do_not_wait_for_writer_or_allow_writes():
    account()
    with identity.database() as writer:
        writer.execute("UPDATE users SET name='Changed' WHERE email='owner@example.com'")
        with ThreadPoolExecutor(max_workers=1) as executor:
            def read():
                with identity.database(write=False) as reader:
                    value = reader.execute('SELECT name FROM users').fetchone()[0]
                    try:
                        reader.execute("UPDATE users SET name='Should not write'")
                    except sqlite3.OperationalError:
                        return value
                    raise AssertionError('Read connection permitted a write')
            assert executor.submit(read).result(timeout=2) == 'Test Owner'


def test_argon_verification_is_outside_identity_write_lock(monkeypatch):
    account()
    original = identity.verify_password
    def verify(value, hashed):
        # A different connection can take a write transaction while Argon2 runs.
        with identity.database() as db:
            assert db.execute('SELECT count(*) FROM users').fetchone()[0] == 1
        return original(value, hashed)
    monkeypatch.setattr(identity, 'verify_password', verify)
    assert TestClient(app).post('/auth/login', json={'email': 'owner@example.com', 'password': 'a-long-test-password'}).status_code == 200


def test_reset_expires_and_worker_password_change_revokes_only_scoped_sessions():
    owner, org, _ = account()
    existing, other_org, _ = account(email='global@example.com')
    worker, activated = activate(invitation(owner, org), existing, link_existing=True)
    user_id = worker.get('/auth/session').json()['user']['id']
    global_session = TestClient(app)
    assert global_session.post('/auth/login', json={'email': 'global@example.com', 'password': 'a-long-test-password'}).status_code == 200
    assert worker.post('/auth/password', json={'current_password': PASSWORD, 'password': 'changed-scoped-passphrase'}).status_code == 200
    assert worker.get('/auth/session').status_code == 401
    assert global_session.get(f'/organizations/{other_org}').status_code == 200
    reset_link = owner.post(f'/organizations/{org}/members/{user_id}/worker-reset', json={}).json()
    token = reset_link['reset_path'].split('/')[-1]
    with identity.database() as db:
        db.execute('UPDATE employee_links SET expires=0 WHERE id=?', (reset_link['id'],))
    assert TestClient(app).post('/auth/worker/reset', json={'token': token, 'password': PASSWORD}).status_code == 410


def test_employee_login_cannot_bypass_promotion_email_requirement():
    owner, org, _ = account()
    worker, activated = activate(invitation(owner, org))
    user_id = worker.get('/auth/session').json()['user']['id']
    response = worker.post('/auth/worker/email-account', json={'email': 'promoted@example.com', 'current_password': PASSWORD, 'password': 'supervisor-global-password'})
    assert response.status_code == 200
    assert owner.put(f'/organizations/{org}/members/{user_id}', json={'access': 'member', 'role': 'supervisor'}).status_code == 200
    assert TestClient(app).post('/auth/worker/login', json={'organization_code': activated['organization_code'], 'employee_id': 'EMP-1', 'password': PASSWORD}).status_code == 401
    assert TestClient(app).post('/auth/login', json={'email': 'promoted@example.com', 'password': 'supervisor-global-password'}).status_code == 200


def test_unsafe_runtime_rejects_preexisting_wal_database(monkeypatch):
    account()
    path = identity.root() / 'identity.sqlite3'
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
    monkeypatch.setattr(sqlite3, 'sqlite_version_info', (3, 50, 4))
    with pytest.raises(RuntimeError, match='unpatched SQLite'):
        with identity.database(write=False):
            pass
