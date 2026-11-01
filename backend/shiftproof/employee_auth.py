"""Employee IDs authenticate one membership, never an owner's other organizations."""
import secrets
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from . import identity as ident
from .models import uid

router = APIRouter()


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class WorkerInvite(Input):
    name: str = Field(min_length=2, max_length=100)
    employee_id: str = Field(min_length=1, max_length=32)


class WorkerLogin(Input):
    organization_code: str = Field(min_length=1, max_length=64)
    employee_id: str = Field(min_length=1, max_length=32)
    password: str = Field(max_length=128)


class Activate(Input):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=12, max_length=128)
    confirm_password: str | None = Field(default=None, max_length=128)
    link_existing: bool = False


class Reset(Input):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=12, max_length=128)
    confirm_password: str | None = Field(default=None, max_length=128)


class EmailAccount(Input):
    email: str = Field(max_length=254)
    current_password: str = Field(max_length=128)
    password: str = Field(min_length=12, max_length=128)
    confirm_password: str | None = Field(default=None, max_length=128)


def audit(db, org_id, actor_id, action, target_id, details=None):
    from .accounts_api import event
    event(db, org_id, actor_id, action, target_id, details)


def status(row):
    return 'accepted' if row['used'] else 'revoked' if row['revoked'] else 'expired' if row['expires'] <= time.time() else 'pending'


def require_manager(request, org_id, owner_only=False):
    user, org = ident.tenant(request, org_id)
    allowed = ('owner',) if owner_only else ('owner', 'admin')
    if org['access'] not in allowed:
        raise HTTPException(403, 'Only an organization owner can manage worker recovery' if owner_only else 'Organization administrator required')
    return user, org


def issue_link(db, org_id, employee_id, actor_id, purpose='activate'):
    token = secrets.token_urlsafe(32)
    link_id = uid('employee-link')
    created = time.time()
    seconds = 72 * 3600 if purpose == 'activate' else 30 * 60
    db.execute('INSERT INTO employee_links(token,id,org_id,employee_id,purpose,expires,created_at,actor_id) VALUES (?,?,?,?,?,?,?,?)',
               (ident.digest(token), link_id, org_id, employee_id, purpose, created + seconds, created, actor_id))
    audit(db, org_id, actor_id, 'worker.invitation_created' if purpose == 'activate' else 'worker.reset_requested', link_id, {'employee_id': employee_id})
    path = f'/join/{token}' if purpose == 'activate' else f'/worker/reset/{token}'
    return {'id': link_id, 'join_path' if purpose == 'activate' else 'reset_path': path,
            'expires_in_hours': 72 if purpose == 'activate' else 0.5,
            'delivery': 'Share this single-use link privately with the worker. No email was sent.'}


def read_link(db, token, purpose):
    row = db.execute('SELECT l.*,e.user_id,e.name,e.active,o.name AS organization_name,o.login_code FROM employee_links l JOIN employee_credentials e ON e.org_id=l.org_id AND e.employee_id=l.employee_id JOIN organizations o ON o.id=l.org_id WHERE l.token=? AND l.purpose=?',
                     (ident.digest(token), purpose)).fetchone()
    if not row or status(row) != 'pending':
        raise HTTPException(410, 'Activation or recovery link expired, revoked or already used')
    return row


def public_invitation(token):
    with ident.database(write=False) as db:
        row = read_link(db, token, 'activate')
    return {'kind': 'employee', 'name': row['name'], 'employee_id': row['employee_id'],
            'organization_name': row['organization_name'], 'organization_code': row['login_code'],
            'role': 'operator', 'access': 'member'}


@router.post('/organizations/{org_id}/worker-invitations', status_code=201)
def invite_worker(org_id: str, body: WorkerInvite, request: Request):
    user, org = require_manager(request, org_id)
    employee_id = ident.employee_id(body.employee_id)
    name = body.name.strip()
    if len(name) < 2:
        raise HTTPException(422, 'Enter the worker’s name')
    with ident.database() as db:
        existing = db.execute('SELECT * FROM employee_credentials WHERE org_id=? AND employee_id=?', (org_id, employee_id)).fetchone()
        if existing and existing['user_id']:
            raise HTTPException(409, 'This employee ID belongs to an existing or former worker. Use recovery for an active member; retired IDs retain their history.')
        pending = db.execute("SELECT 1 FROM employee_links WHERE org_id=? AND employee_id=? AND purpose='activate' AND used=0 AND revoked=0 AND expires>?", (org_id, employee_id, time.time())).fetchone()
        if pending:
            raise HTTPException(409, 'This worker has a pending activation. Replace its link instead.')
        db.execute('INSERT INTO employee_credentials(org_id,employee_id,name,created_at) VALUES (?,?,?,?) ON CONFLICT(org_id,employee_id) DO UPDATE SET name=excluded.name', (org_id, employee_id, name, time.time()))
        return issue_link(db, org_id, employee_id, user['id'])


@router.get('/organizations/{org_id}/worker-invitations')
def worker_invitations(org_id: str, request: Request):
    require_manager(request, org_id)
    with ident.database(write=False) as db:
        rows = db.execute("SELECT l.id,l.employee_id,l.expires,l.created_at,l.used,l.revoked,e.name FROM employee_links l JOIN employee_credentials e ON e.org_id=l.org_id AND e.employee_id=l.employee_id WHERE l.org_id=? AND l.purpose='activate' ORDER BY l.created_at DESC", (org_id,)).fetchall()
    return [{**{k: row[k] for k in ('id', 'employee_id', 'name', 'expires', 'created_at')}, 'kind': 'employee', 'role': 'operator', 'access': 'member', 'status': status(row)} for row in rows]


@router.delete('/organizations/{org_id}/worker-invitations/{link_id}')
def revoke_worker_invitation(org_id: str, link_id: str, request: Request):
    user, _ = require_manager(request, org_id)
    with ident.database() as db:
        row = db.execute("SELECT * FROM employee_links WHERE org_id=? AND id=? AND purpose='activate'", (org_id, link_id)).fetchone()
        if not row:
            raise HTTPException(404, 'Activation not found')
        if row['used']:
            raise HTTPException(409, 'Manage an activated worker through their membership')
        db.execute('UPDATE employee_links SET revoked=1 WHERE id=?', (link_id,))
        audit(db, org_id, user['id'], 'worker.invitation_revoked', link_id, {'employee_id': row['employee_id']})
    return {'status': 'revoked'}


@router.post('/organizations/{org_id}/worker-invitations/{link_id}/replace', status_code=201)
def replace_worker_invitation(org_id: str, link_id: str, request: Request):
    user, _ = require_manager(request, org_id)
    with ident.database() as db:
        row = db.execute("SELECT * FROM employee_links WHERE org_id=? AND id=? AND purpose='activate'", (org_id, link_id)).fetchone()
        if not row:
            raise HTTPException(404, 'Activation not found')
        if status(row) not in ('pending', 'expired'):
            raise HTTPException(409, 'Only pending or expired activation links can be replaced')
        db.execute('UPDATE employee_links SET revoked=1 WHERE id=?', (link_id,))
        audit(db, org_id, user['id'], 'worker.invitation_replaced', link_id, {'employee_id': row['employee_id']})
        return issue_link(db, org_id, row['employee_id'], user['id'])


def confirmed_password(body):
    if body.confirm_password is not None and body.confirm_password != body.password:
        raise HTTPException(422, 'Passwords do not match')
    return ident.password(body.password)


@router.post('/auth/worker/activate', status_code=201)
def activate(body: Activate, request: Request, response: Response):
    ident.throttle(request, 'worker-activation', ident.digest(body.token))
    linked = ident.principal(request) if body.link_existing else None
    if linked:
        ident.require_email_session(linked)
    with ident.database(write=False) as db:
        read_link(db, body.token, 'activate')
    hashed = confirmed_password(body)
    with ident.database() as db:
        row = read_link(db, body.token, 'activate')
        if row['user_id'] or row['active']:
            raise HTTPException(409, 'This worker is already activated')
        user_id = linked['id'] if linked else uid('user')
        existing = db.execute('SELECT access,role FROM memberships WHERE org_id=? AND user_id=?', (row['org_id'], user_id)).fetchone()
        if existing and (existing['access'] != 'member' or existing['role'] != 'operator'):
            raise HTTPException(409, 'This account already has a different role in the organization')
        if linked and db.execute('SELECT 1 FROM employee_credentials WHERE org_id=? AND user_id=?', (row['org_id'], user_id)).fetchone():
            raise HTTPException(409, 'This account already has an employee ID here')
        if not linked:
            db.execute('INSERT INTO users(id,email,name,password,recovery) VALUES (?,NULL,?,NULL,?)', (user_id, row['name'], '[]'))
        db.execute("INSERT OR IGNORE INTO memberships(org_id,user_id,access,role) VALUES (?,?,'member','operator')", (row['org_id'], user_id))
        db.execute('UPDATE employee_credentials SET user_id=?,password=?,active=1 WHERE org_id=? AND employee_id=?', (user_id, hashed, row['org_id'], row['employee_id']))
        db.execute('UPDATE employee_links SET used=1 WHERE token=?', (ident.digest(body.token),))
        audit(db, row['org_id'], user_id, 'worker.activated', user_id, {'employee_id': row['employee_id'], 'linked_existing_identity': bool(linked)})
        csrf = ident.issue_session(db, user_id, response, request, 'employee', row['org_id'])
    return {'csrf_token': csrf, 'organization_id': row['org_id'], 'organization_code': row['login_code'],
            'employee_id': row['employee_id'], 'auth_kind': 'employee'}


@router.post('/auth/worker/login')
def login(body: WorkerLogin, request: Request, response: Response):
    code = body.organization_code.strip().upper()
    employee_id = body.employee_id.strip().upper()
    ident.throttle(request, 'worker-login', f'{code}:{employee_id}')
    with ident.database(write=False) as db:
        row = db.execute("SELECT e.*,o.login_code FROM employee_credentials e JOIN organizations o ON o.id=e.org_id JOIN memberships m ON m.org_id=e.org_id AND m.user_id=e.user_id WHERE o.login_code=? AND e.employee_id=? AND e.active=1 AND m.role='operator' AND m.access='member'", (code, employee_id)).fetchone()
    if not ident.verify_password(body.password, row['password'] if row else None):
        raise HTTPException(401, 'Organization code, employee ID or password is incorrect')
    with ident.database() as db:
        current = db.execute("SELECT e.password FROM employee_credentials e JOIN memberships m ON m.org_id=e.org_id AND m.user_id=e.user_id WHERE e.org_id=? AND e.employee_id=? AND e.active=1 AND m.role='operator' AND m.access='member'", (row['org_id'], employee_id)).fetchone()
        if not current or current['password'] != row['password']:
            raise HTTPException(401, 'Organization code, employee ID or password is incorrect')
        csrf = ident.issue_session(db, row['user_id'], response, request, 'employee', row['org_id'])
    return {'csrf_token': csrf, 'organization_id': row['org_id'], 'auth_kind': 'employee'}


@router.post('/organizations/{org_id}/members/{user_id}/worker-reset', status_code=201)
def request_reset(org_id: str, user_id: str, request: Request):
    owner, _ = require_manager(request, org_id, owner_only=True)
    with ident.database() as db:
        row = db.execute("SELECT e.employee_id FROM employee_credentials e JOIN memberships m ON m.org_id=e.org_id AND m.user_id=e.user_id WHERE e.org_id=? AND e.user_id=? AND e.active=1 AND m.role='operator' AND m.access='member'", (org_id, user_id)).fetchone()
        if not row:
            raise HTTPException(404, 'Active employee credential not found')
        db.execute("UPDATE employee_links SET revoked=1 WHERE org_id=? AND employee_id=? AND purpose='reset' AND used=0", (org_id, row['employee_id']))
        # Invalidate only this organization credential. A global email password is untouched.
        db.execute('UPDATE employee_credentials SET password=NULL WHERE org_id=? AND user_id=?', (org_id, user_id))
        db.execute("DELETE FROM sessions WHERE org_id=? AND user_id=? AND auth_kind='employee'", (org_id, user_id))
        return issue_link(db, org_id, row['employee_id'], owner['id'], 'reset')


@router.get('/auth/worker/reset/{token}')
def reset_details(token: str):
    with ident.database(write=False) as db:
        row = read_link(db, token, 'reset')
    return {'name': row['name'], 'employee_id': row['employee_id'], 'organization_name': row['organization_name'], 'organization_code': row['login_code']}


@router.post('/auth/worker/reset')
def reset(body: Reset, request: Request, response: Response):
    ident.throttle(request, 'worker-reset', ident.digest(body.token))
    with ident.database(write=False) as db:
        read_link(db, body.token, 'reset')
    hashed = confirmed_password(body)
    with ident.database() as db:
        row = read_link(db, body.token, 'reset')
        member = db.execute("SELECT 1 FROM memberships WHERE org_id=? AND user_id=? AND role='operator' AND access='member'", (row['org_id'], row['user_id'])).fetchone()
        if not row['active'] or not member:
            raise HTTPException(410, 'This employee no longer has organization access')
        db.execute('UPDATE employee_credentials SET password=? WHERE org_id=? AND employee_id=?', (hashed, row['org_id'], row['employee_id']))
        db.execute('UPDATE employee_links SET used=1 WHERE token=?', (ident.digest(body.token),))
        db.execute("DELETE FROM sessions WHERE org_id=? AND user_id=? AND auth_kind='employee'", (row['org_id'], row['user_id']))
        audit(db, row['org_id'], row['user_id'], 'worker.password_reset', row['user_id'], {'employee_id': row['employee_id']})
        csrf = ident.issue_session(db, row['user_id'], response, request, 'employee', row['org_id'])
    return {'status': 'password_changed', 'csrf_token': csrf, 'organization_id': row['org_id'], 'auth_kind': 'employee'}


def change_employee_password(user, body, request, response):
    ident.throttle(request, 'worker-password', f'{user["scoped_organization_id"]}:{user["id"]}')
    with ident.database(write=False) as db:
        row = db.execute('SELECT * FROM employee_credentials WHERE org_id=? AND user_id=? AND active=1', (user['scoped_organization_id'], user['id'])).fetchone()
    if not ident.verify_password(body.current_password, row['password'] if row else None):
        raise HTTPException(403, 'Current password is incorrect')
    hashed = ident.password(body.password)
    with ident.database() as db:
        changed = db.execute('UPDATE employee_credentials SET password=? WHERE org_id=? AND user_id=? AND password=? AND active=1', (hashed, row['org_id'], user['id'], row['password'])).rowcount
        if not changed:
            raise HTTPException(409, 'Password changed. Sign in again.')
        db.execute("DELETE FROM sessions WHERE org_id=? AND user_id=? AND auth_kind='employee'", (row['org_id'], user['id']))
        db.execute("UPDATE employee_links SET revoked=1 WHERE org_id=? AND employee_id=? AND purpose='reset' AND used=0", (row['org_id'], row['employee_id']))
        audit(db, row['org_id'], user['id'], 'worker.password_changed', user['id'])
    response.delete_cookie(ident.COOKIE, path='/')
    return {'status': 'password_changed'}


@router.post('/auth/worker/email-account')
def add_email_account(body: EmailAccount, request: Request, response: Response):
    """A worker may establish their own email login; owners never choose its password."""
    user = ident.principal(request)
    if user['auth_kind'] != 'employee' or user['email']:
        raise HTTPException(409, 'Use your existing email account')
    address = ident.email(body.email)
    ident.throttle(request, 'link-email', address)
    with ident.database(write=False) as db:
        row = db.execute('SELECT password FROM employee_credentials WHERE org_id=? AND user_id=? AND active=1', (user['scoped_organization_id'], user['id'])).fetchone()
    if not ident.verify_password(body.current_password, row['password'] if row else None):
        raise HTTPException(403, 'Current password is incorrect')
    hashed = confirmed_password(body)
    codes, recovery = ident.recovery_codes()
    with ident.database() as db:
        current = db.execute('SELECT password FROM employee_credentials WHERE org_id=? AND user_id=? AND active=1', (user['scoped_organization_id'], user['id'])).fetchone()
        if not current or current['password'] != row['password']:
            raise HTTPException(409, 'Credential changed. Sign in again.')
        if db.execute('SELECT 1 FROM users WHERE email=?', (address,)).fetchone():
            raise HTTPException(409, 'This email already has an account. Accounts are not merged automatically.')
        changed = db.execute('UPDATE users SET email=?,password=?,recovery=? WHERE id=? AND email IS NULL', (address, hashed, recovery, user['id'])).rowcount
        if not changed:
            raise HTTPException(409, 'This identity already has an email account')
        audit(db, user['scoped_organization_id'], user['id'], 'worker.email_account_added', user['id'], {'email': address, 'email_verified': False})
        csrf = ident.issue_session(db, user['id'], response, request)
    return {'csrf_token': csrf, 'organization_id': user['scoped_organization_id'], 'recovery_codes': codes, 'email_verified': False}
