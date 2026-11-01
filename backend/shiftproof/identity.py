"""Local accounts and explicit tenant storage. No implicit adoption of legacy data."""
import hashlib
import json
import os
import secrets
import sqlite3
import time
import re
from contextlib import contextmanager
from pathlib import Path
from fastapi import HTTPException, Request
from pwdlib import PasswordHash
from .config import settings
from .models import Actor, uid
from .repository import LocalRepository
from .profiles import PROFILES

PASSWORDS = PasswordHash.recommended()
COOKIE = 'shiftproof_session'
SCHEMA_VERSION = 3
# Unknown accounts still pay the same password-verification cost. Never log inputs.
DUMMY_PASSWORD_HASH = PASSWORDS.hash(secrets.token_urlsafe(32))

def digest(value): return hashlib.sha256(value.encode()).hexdigest()

def root():
    base = settings().data_dir / 'accounts'
    base.mkdir(parents=True, exist_ok=True)
    return base

def _migrate(db, path):
    """Versioned, transactional upgrade; initialized reads never take a write lock."""
    if db.execute('PRAGMA user_version').fetchone()[0] >= SCHEMA_VERSION:
        version = sqlite3.sqlite_version_info
        patched = version >= (3, 51, 3) or ((3, 50, 7) <= version < (3, 51, 0)) or ((3, 44, 6) <= version < (3, 45, 0))
        if db.execute('PRAGMA journal_mode').fetchone()[0].lower() == 'wal' and not patched:
            raise RuntimeError('This identity database uses WAL on an unpatched SQLite runtime. Upgrade SQLite before startup, or convert to DELETE journal mode during maintenance.')
        return
    columns = {r['name']: r for r in db.execute('PRAGMA table_info(users)')}
    if columns and (columns['email']['notnull'] or columns['password']['notnull']):
        backup = path.parent / 'backups' / f'identity-before-employees-{time.time_ns()}.sqlite3'
        backup.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(backup) as destination:
            db.backup(destination)
    # Rollback journaling also permits readers while a writer holds RESERVED.
    # The bundled SQLite 3.50.4 is not eligible for WAL's recent safety fixes.
    db.execute('PRAGMA journal_mode=DELETE')
    db.execute('BEGIN IMMEDIATE')
    try:
        if db.execute('PRAGMA user_version').fetchone()[0] >= SCHEMA_VERSION:
            db.commit()
            return
        statements = '''
    CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE,name TEXT NOT NULL,password TEXT,recovery TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS organizations(id TEXT PRIMARY KEY,name TEXT NOT NULL,industry TEXT NOT NULL,timezone TEXT NOT NULL,setup TEXT NOT NULL DEFAULT '{}');
    CREATE TABLE IF NOT EXISTS memberships(org_id TEXT,user_id TEXT,access TEXT NOT NULL,role TEXT NOT NULL,PRIMARY KEY(org_id,user_id));
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL,csrf TEXT NOT NULL,expires REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS invitations(token TEXT PRIMARY KEY,org_id TEXT,email TEXT,access TEXT,role TEXT,expires REAL,used INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS limits(key TEXT PRIMARY KEY,count INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS migrations(source TEXT PRIMARY KEY,receipt TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS account_events(id TEXT PRIMARY KEY,org_id TEXT NOT NULL,actor_id TEXT NOT NULL,actor_name TEXT NOT NULL,action TEXT NOT NULL,target_id TEXT NOT NULL,created_at REAL NOT NULL,details TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS employee_credentials(org_id TEXT NOT NULL,employee_id TEXT NOT NULL,user_id TEXT,name TEXT NOT NULL,password TEXT,active INTEGER NOT NULL DEFAULT 0,created_at REAL NOT NULL,PRIMARY KEY(org_id,employee_id),UNIQUE(org_id,user_id));
    CREATE TABLE IF NOT EXISTS employee_links(token TEXT PRIMARY KEY,id TEXT UNIQUE NOT NULL,org_id TEXT NOT NULL,employee_id TEXT NOT NULL,purpose TEXT NOT NULL,expires REAL NOT NULL,used INTEGER NOT NULL DEFAULT 0,revoked INTEGER NOT NULL DEFAULT 0,created_at REAL NOT NULL,actor_id TEXT NOT NULL);
    '''
        for statement in statements.split(';'):
            if statement.strip():
                db.execute(statement)
        columns = {r['name']: r for r in db.execute('PRAGMA table_info(users)')}
        if columns['email']['notnull'] or columns['password']['notnull']:
            db.execute('CREATE TABLE users_upgrade(id TEXT PRIMARY KEY,email TEXT UNIQUE,name TEXT NOT NULL,password TEXT,recovery TEXT NOT NULL)')
            db.execute('INSERT INTO users_upgrade SELECT id,email,name,password,recovery FROM users')
            db.execute('DROP TABLE users')
            db.execute('ALTER TABLE users_upgrade RENAME TO users')
        columns = {r['name'] for r in db.execute('PRAGMA table_info(invitations)')}
        for name, definition in [('id', 'TEXT'), ('name', "TEXT NOT NULL DEFAULT ''"),
                                 ('revoked', 'INTEGER NOT NULL DEFAULT 0'),
                                 ('created_at', 'REAL NOT NULL DEFAULT 0')]:
            if name not in columns:
                db.execute(f'ALTER TABLE invitations ADD COLUMN {name} {definition}')
        for row in db.execute('SELECT token FROM invitations WHERE id IS NULL').fetchall():
            db.execute('UPDATE invitations SET id=? WHERE token=?', (secrets.token_hex(16), row['token']))
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS invitations_id ON invitations(id)')
        session_columns = {r['name'] for r in db.execute('PRAGMA table_info(sessions)')}
        for name, definition in [('auth_kind', "TEXT NOT NULL DEFAULT 'email'"), ('org_id', 'TEXT')]:
            if name not in session_columns:
                db.execute(f'ALTER TABLE sessions ADD COLUMN {name} {definition}')
        org_columns = {r['name'] for r in db.execute('PRAGMA table_info(organizations)')}
        if 'login_code' not in org_columns:
            db.execute('ALTER TABLE organizations ADD COLUMN login_code TEXT')
        for row in db.execute('SELECT id FROM organizations WHERE login_code IS NULL').fetchall():
            db.execute('UPDATE organizations SET login_code=? WHERE id=?', (organization_code(), row['id']))
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS organizations_login_code ON organizations(login_code)')
        db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        db.commit()
    except Exception:
        db.rollback()
        raise

@contextmanager
def database(write=True):
    path = root() / 'identity.sqlite3'
    db = sqlite3.connect(path, timeout=20)
    db.row_factory = sqlite3.Row
    try:
        _migrate(db, path)
        if write:
            db.execute('BEGIN IMMEDIATE')
        else:
            db.execute('PRAGMA query_only=ON')
        yield db
        db.commit()
    except Exception:
        db.rollback(); raise
    finally: db.close()

def email(value):
    v=value.strip().lower()
    if len(v)>254 or '@' not in v or '.' not in v.split('@')[-1]: raise HTTPException(422,'Enter a valid email address')
    return v

def password(value):
    if len(value)<12 or len(value)>128: raise HTTPException(422,'Use a password between 12 and 128 characters')
    return PASSWORDS.hash(value)

def verify_password(value, hashed):
    try:
        valid = PASSWORDS.verify(value, hashed or DUMMY_PASSWORD_HASH)
    except Exception:
        return False
    return bool(hashed) and valid

def organization_code():
    return ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(10))

def employee_id(value):
    value = value.strip().upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9._-]{0,31}', value):
        raise HTTPException(422, 'Use an employee ID of 1–32 letters, numbers, dots, hyphens or underscores')
    return value

def require_email_session(user):
    if user.get('auth_kind') != 'email' or not user.get('email'):
        raise HTTPException(403, 'Use an email account for organization administration')

def owner_signup_approved(address):
    if os.getenv('PILOT_SIGNUP_APPROVAL_REQUIRED', 'false').lower() == 'true':
        approved = {v.strip().lower() for v in os.getenv('PILOT_APPROVED_OWNER_EMAILS', '').split(',') if v.strip()}
        return address in approved
    return True

def signup_allowed(address):
    if not owner_signup_approved(address):
        raise HTTPException(403, 'New pilot organizations require approval. Use your team invitation or contact the pilot administrator.')

def recovery_codes():
    codes=[secrets.token_hex(10) for _ in range(5)]
    return codes,json.dumps([digest(c) for c in codes])

def throttle(request, label, account_key=None):
    bucket = int(time.time()//300)
    keys = [(f'{label}:ip:{request.client.host if request.client else "local"}:{bucket}', 30)]
    if account_key:
        keys.append((f'{label}:account:{digest(account_key)}:{bucket}', 10))
    with database() as db:
        for key, limit in keys:
            count=db.execute('SELECT count FROM limits WHERE key=?',(key,)).fetchone()
            if count and count[0]>=limit: raise HTTPException(429,'Too many attempts. Try again in five minutes.')
        for key, _ in keys:
            db.execute('INSERT INTO limits VALUES (?,1) ON CONFLICT(key) DO UPDATE SET count=count+1',(key,))
        # Fixed-window rows carry their bucket; retain only recent windows.
        db.execute("DELETE FROM limits WHERE CAST(substr(key, length(rtrim(key, '0123456789'))+1) AS INTEGER) < ?", (bucket-2,))

def issue_session(db,user_id,response,request,auth_kind='email',org_id=None):
    token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
    db.execute('DELETE FROM sessions WHERE expires<=?', (time.time(),))
    db.execute('INSERT INTO sessions(token,user_id,csrf,expires,auth_kind,org_id) VALUES (?,?,?,?,?,?)',(digest(token),user_id,csrf,time.time()+28800,auth_kind,org_id))
    secure=request.url.scheme=='https' or os.getenv('COOKIE_SECURE','false').lower()=='true'
    response.set_cookie(COOKIE,token,max_age=28800,httponly=True,secure=secure,samesite='lax',path='/')
    return csrf

def principal(request: Request):
    token=request.cookies.get(COOKIE)
    if not token: raise HTTPException(401,'Sign in to your organization')
    with database(write=False) as db:
        row=db.execute('SELECT users.id,users.name,users.email,sessions.csrf,sessions.auth_kind,sessions.org_id AS scoped_organization_id FROM sessions JOIN users ON users.id=sessions.user_id WHERE token=? AND expires>?',(digest(token),time.time())).fetchone()
        if row and row['auth_kind']=='employee':
            active = db.execute("SELECT 1 FROM employee_credentials JOIN memberships USING(org_id,user_id) WHERE employee_credentials.org_id=? AND employee_credentials.user_id=? AND active=1 AND memberships.role='operator' AND memberships.access='member'", (row['scoped_organization_id'],row['id'])).fetchone()
            if not active:
                row = None
    if not row: raise HTTPException(401,'Your session expired. Sign in again.')
    if request.method not in ('GET','HEAD','OPTIONS') and not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),row['csrf']):
        raise HTTPException(403,'Refresh your session before submitting this change')
    return dict(row)

def memberships(user_id, scoped_organization_id=None):
    with database(write=False) as db:
        query='SELECT organizations.*,memberships.access,memberships.role FROM organizations JOIN memberships ON organizations.id=memberships.org_id WHERE user_id=?'
        args=[user_id]
        if scoped_organization_id:
            query+=' AND organizations.id=?'; args.append(scoped_organization_id)
        rows=db.execute(query,args).fetchall()
    return [organization(dict(r)) for r in rows]

def organization(row):
    row['setup']=json.loads(row['setup']);row['profile']=PROFILES[row['industry']]
    if 'access' in row:
        row['capabilities']=capabilities(row)
    return row

def capabilities(org):
    owner=org['access']=='owner'
    return {'manage_people':owner, 'manage_settings':owner, 'invite_workers':org['access'] in ('owner','admin'),
            'review_reports':org['role'] in ('supervisor','quality'), 'clear_holds':org['role']=='quality',
            'export_data':owner, 'manage_work':org['role']=='supervisor' or (owner and org['role']=='quality')}

def tenant(request: Request, org_id: str):
    user=principal(request)
    if user.get('scoped_organization_id') and user['scoped_organization_id']!=org_id:
        raise HTTPException(404,'Organization not found')
    with database(write=False) as db:
        row=db.execute('SELECT organizations.*,memberships.access,memberships.role FROM organizations JOIN memberships ON organizations.id=memberships.org_id WHERE user_id=? AND organizations.id=?',(user['id'],org_id)).fetchone()
    if not row: raise HTTPException(404,'Organization not found')
    return user,organization(dict(row))

def tenant_repo(org):
    path=root() / 'organizations' / org['id']
    path.mkdir(parents=True,exist_ok=True)
    repo=LocalRepository(path/'workspace.sqlite3');repo.data_dir=path;repo.organization_id=org['id']
    if 'profile' not in repo.load_index():
        with repo.transaction() as state:
            if 'profile' not in state:
                state.update(profile=org['industry'],profile_version=1,work_items={},shift_name='Current handover')
    return repo

def operational(request,org_id):
    user,org=tenant(request,org_id)
    if org['profile']['status']!='available': raise HTTPException(409,'This industry workflow is a preview; operational capture is not enabled')
    return user,org,tenant_repo(org),Actor(id=user['id'],name=user['name'],role=org['role'])

def reserve_global_usage(key, limit):
    from .providers import ProviderError
    # One ledger across local and public-preview processes using this installation.
    location=Path(os.getenv('SHIFTPROOF_SHARED_USAGE_DB') or str(Path(__file__).resolve().parents[2]/'.local'/'shared-usage.sqlite3'))
    location.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(location,timeout=20) as db:
        db.execute('CREATE TABLE IF NOT EXISTS usage(key TEXT PRIMARY KEY,count INTEGER NOT NULL)')
        db.execute('BEGIN IMMEDIATE')
        today=time.strftime('%Y-%m-%d',time.gmtime()); k=f'{today}:{key}'
        row=db.execute('SELECT count FROM usage WHERE key=?',(k,)).fetchone()
        if row and row[0]>=limit: raise ProviderError('Shared provider budget reached. Saved transcripts remain available.','quota_exhausted')
        db.execute('INSERT INTO usage VALUES (?,1) ON CONFLICT(key) DO UPDATE SET count=count+1',(k,))
