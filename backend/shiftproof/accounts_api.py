import json
import secrets
import time
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Request, Response, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal
from . import identity as ident
from .models import uid
from .profiles import PROFILES

router=APIRouter()
class Input(BaseModel): model_config=ConfigDict(extra='forbid')
class Signup(Input):
    name:str=Field(min_length=2,max_length=100)
    email:str=Field(max_length=254)
    password:str=Field(min_length=12,max_length=128)
    confirm_password:str|None=Field(default=None,max_length=128)
    organization_name:str=Field(default='',max_length=120)
    industry:str='manufacturing'
    timezone:str='Asia/Kolkata'
    invitation_token:str|None=None
class Login(Input):
    email:str
    password:str=Field(max_length=128)
class Recover(Input):
    email:str
    code:str=Field(max_length=100)
    password:str=Field(min_length=12,max_length=128)
class ChangePassword(Input):
    current_password:str=Field(max_length=128)
    password:str=Field(min_length=12,max_length=128)
class OrgCreate(Input):
    name:str=Field(min_length=2,max_length=120)
    industry:str
    timezone:str='Asia/Kolkata'
class Setup(Input):
    locations:list[str]=Field(default_factory=list,max_length=30)
    teams:list[str]=Field(default_factory=list,max_length=30)
    shifts:list[str]=Field(default_factory=list,max_length=30)
class Invite(Input):
    name:str=Field(default='',max_length=100)
    email:str
    access:Literal['admin','member']='member'
    role:Literal['operator','supervisor','quality']='operator'
class Membership(Input):
    access:Literal['owner','admin','member']
    role:Literal['operator','supervisor','quality']
class Join(Input): token:str
class OrganizationSettings(Input):
    name:str=Field(min_length=2,max_length=120)
    timezone:str

def event(db, org_id, actor_id, action, target_id, details=None):
    actor=db.execute('SELECT name FROM users WHERE id=?',(actor_id,)).fetchone()
    db.execute('INSERT INTO account_events VALUES (?,?,?,?,?,?,?,?)',
               (uid('event'),org_id,actor_id,actor['name'] if actor else 'Former member',action,target_id,time.time(),json.dumps(details or {})))

def invitation_status(row):
    return 'accepted' if row['used'] else 'revoked' if row['revoked'] else 'expired' if row['expires']<=time.time() else 'pending'

def invitation_admin(org, access='member', role='operator'):
    if org['access'] not in ('owner','admin') or (org['access']=='admin' and (access!='member' or role!='operator')):
        raise HTTPException(403,'Only an owner can appoint administrators, supervisors or authorized reviewers')

def issue_invitation(db, org_id, actor_id, body):
    token=secrets.token_urlsafe(32); invitation_id=uid('invite'); created=time.time()
    db.execute('INSERT INTO invitations(token,org_id,email,access,role,expires,id,name,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
               (ident.digest(token),org_id,ident.email(body.email),body.access,body.role,created+86400*3,invitation_id,body.name.strip(),created))
    event(db,org_id,actor_id,'invitation.created',invitation_id,{'name':body.name.strip(),'email':ident.email(body.email),'access':body.access,'role':body.role})
    return {'id':invitation_id,'join_path':f'/join/{token}','expires_in_hours':72,'delivery':'Copy this link and share it with the invited person; no email was sent.'}

def check_org(industry,timezone):
    if industry not in PROFILES: raise HTTPException(422,'Unknown organization type')
    try: ZoneInfo(timezone)
    except (ZoneInfoNotFoundError,ValueError): raise HTTPException(422,'Select a valid timezone')

def new_org(db,user_id,name,industry,timezone):
    check_org(industry,timezone)
    if len(name.strip())<2: raise HTTPException(422,'Enter an organization name')
    org_id=uid('org')
    db.execute('INSERT INTO organizations(id,name,industry,timezone,login_code) VALUES (?,?,?,?,?)',(org_id,name.strip(),industry,timezone,ident.organization_code()))
    # Membership administration never implicitly grants clearance permission.
    db.execute('INSERT INTO memberships VALUES (?,?,?,?)',(org_id,user_id,'owner','supervisor'))
    return org_id

def accept(db,token,user_id,email):
    row=db.execute('SELECT * FROM invitations WHERE token=?',(ident.digest(token),)).fetchone()
    if not row or invitation_status(row)!='pending': raise HTTPException(410,'Invitation expired, revoked or already used')
    if row['email']!=email: raise HTTPException(403,'Sign in with the email this invitation was issued to')
    if db.execute('SELECT 1 FROM memberships WHERE org_id=? AND user_id=?',(row['org_id'],user_id)).fetchone(): raise HTTPException(409,'Already a member of this organization')
    db.execute('INSERT INTO memberships VALUES (?,?,?,?)',(row['org_id'],user_id,row['access'],row['role']))
    db.execute('UPDATE invitations SET used=1 WHERE token=?',(ident.digest(token),))
    event(db,row['org_id'],user_id,'invitation.accepted',row['id'],{'name':row['name'],'email':row['email'],'access':row['access'],'role':row['role']})
    return row['org_id']

@router.get('/industries')
def industries(): return list(PROFILES.values())

@router.get('/auth/options')
def auth_options():
    return {'pilot_approval_required':os.getenv('PILOT_SIGNUP_APPROVAL_REQUIRED','false').lower()=='true',
            'employee_login_enabled':True,'email_verified':False}

@router.post('/auth/signup',status_code=201)
def signup(body:Signup,request:Request,response:Response):
    if len(body.name.strip())<2: raise HTTPException(422,'Enter your name')
    if body.confirm_password is not None and body.confirm_password!=body.password: raise HTTPException(422,'Passwords do not match')
    address=ident.email(body.email)
    ident.throttle(request,'signup',address)
    if not body.invitation_token: ident.signup_allowed(address)
    hashed=ident.password(body.password)
    codes,recovery=ident.recovery_codes(); user_id=uid('user')
    with ident.database() as db:
        if db.execute('SELECT id FROM users WHERE email=?',(address,)).fetchone(): raise HTTPException(409,'An account already uses this email. Sign in instead.')
        db.execute('INSERT INTO users VALUES (?,?,?,?,?)',(user_id,address,body.name.strip(),hashed,recovery))
        org_id=accept(db,body.invitation_token,user_id,address) if body.invitation_token else new_org(db,user_id,body.organization_name.strip() or f'{body.name.strip()}’s workspace',body.industry,body.timezone)
        csrf=ident.issue_session(db,user_id,response,request)
    return {'organization_id':org_id,'csrf_token':csrf,'recovery_codes':codes,'email_verified':False}

@router.post('/auth/login')
def login(body:Login,request:Request,response:Response):
    address=ident.email(body.email); ident.throttle(request,'login',address)
    with ident.database(write=False) as db:
        row=db.execute('SELECT * FROM users WHERE email=?',(address,)).fetchone()
    if not ident.verify_password(body.password,row['password'] if row else None):
        raise HTTPException(401,'Email or password is incorrect')
    with ident.database() as db:
        current=db.execute('SELECT password FROM users WHERE id=?',(row['id'],)).fetchone()
        if not current or current['password']!=row['password']: raise HTTPException(401,'Email or password is incorrect')
        csrf=ident.issue_session(db,row['id'],response,request)
    return {'csrf_token':csrf}

@router.get('/auth/session')
def session(request:Request):
    user=ident.principal(request)
    organizations=ident.memberships(user['id'],user.get('scoped_organization_id'))
    return {'user':{k:user[k] for k in ('id','name','email')},'csrf_token':user['csrf'],'organizations':organizations,'email_verified':False,
            'auth_kind':user['auth_kind'],'scoped_organization_id':user.get('scoped_organization_id'),
            'no_organization_access':not organizations,'capabilities':{'create_organization':user['auth_kind']=='email' and ident.owner_signup_approved(user['email']),'change_password':True}}

@router.post('/auth/logout')
def logout(request:Request,response:Response):
    ident.principal(request)
    with ident.database() as db: db.execute('DELETE FROM sessions WHERE token=?',(ident.digest(request.cookies[ident.COOKIE]),))
    response.delete_cookie(ident.COOKIE,path='/')
    return {'status':'signed_out'}

@router.post('/auth/recover')
def recover(body:Recover,request:Request,response:Response):
    ident.throttle(request,'recover',body.email.strip().lower()); hashed=ident.password(body.password)
    with ident.database() as db:
        row=db.execute('SELECT * FROM users WHERE email=?',(ident.email(body.email),)).fetchone()
        codes=json.loads(row['recovery']) if row else []
        code=ident.digest(body.code.strip())
        if code not in codes: raise HTTPException(400,'Email or recovery code is incorrect')
        codes.remove(code)
        db.execute('UPDATE users SET password=?,recovery=? WHERE id=?',(hashed,json.dumps(codes),row['id']))
        db.execute('DELETE FROM sessions WHERE user_id=?',(row['id'],))
    response.delete_cookie(ident.COOKIE,path='/')
    return {'status':'password_changed','remaining_recovery_codes':len(codes)}

@router.post('/auth/password')
def change_password(body:ChangePassword,request:Request,response:Response):
    user=ident.principal(request)
    if user['auth_kind']=='employee':
        from .employee_auth import change_employee_password
        return change_employee_password(user,body,request,response)
    with ident.database(write=False) as db:
        row=db.execute('SELECT password FROM users WHERE id=?',(user['id'],)).fetchone()
    if not ident.verify_password(body.current_password,row['password'] if row else None): raise HTTPException(403,'Current password is incorrect')
    hashed=ident.password(body.password)
    with ident.database() as db:
        current=db.execute('SELECT password FROM users WHERE id=?',(user['id'],)).fetchone()
        if not current or current['password']!=row['password']: raise HTTPException(409,'Password changed. Sign in again.')
        db.execute('UPDATE users SET password=? WHERE id=?',(hashed,user['id']))
        db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
    response.delete_cookie(ident.COOKIE,path='/')
    return {'status':'password_changed'}

@router.post('/organizations',status_code=201)
def create_org(body:OrgCreate,request:Request):
    user=ident.principal(request)
    ident.require_email_session(user); ident.signup_allowed(user['email'])
    with ident.database() as db: org_id=new_org(db,user['id'],body.name,body.industry,body.timezone)
    return {'organization_id':org_id}

@router.get('/organizations/{org_id}')
def get_org(org_id:str,request:Request): return ident.tenant(request,org_id)[1]

@router.put('/organizations/{org_id}/settings')
def organization_settings(org_id:str,body:OrganizationSettings,request:Request):
    user,org=ident.tenant(request,org_id)
    if org['access']!='owner': raise HTTPException(403,'Only an organization owner can change these settings')
    check_org(org['industry'],body.timezone)
    if len(body.name.strip())<2: raise HTTPException(422,'Enter an organization name')
    with ident.database() as db:
        db.execute('UPDATE organizations SET name=?,timezone=? WHERE id=?',(body.name.strip(),body.timezone,org_id))
        event(db,org_id,user['id'],'organization.updated',org_id,{'name':body.name.strip(),'timezone':body.timezone})
    return {'status':'saved'}

@router.put('/organizations/{org_id}/setup')
def setup(org_id:str,body:Setup,request:Request):
    user,org=ident.tenant(request,org_id)
    if org['access'] not in ('owner','admin'): raise HTTPException(403,'Organization administrator required')
    if any(not s.strip() or len(s)>120 for values in body.model_dump().values() for s in values): raise HTTPException(422,'Use nonempty names up to 120 characters')
    with ident.database() as db: db.execute('UPDATE organizations SET setup=? WHERE id=?',(body.model_dump_json(),org_id))
    return {'status':'saved'}

@router.get('/organizations/{org_id}/members')
def members(org_id:str,request:Request):
    _,org=ident.tenant(request,org_id)
    if org['access'] not in ('owner','admin'):
        raise HTTPException(403,'Use the operational directory; account details require administrator access')
    with ident.database(write=False) as db:
        rows=db.execute('SELECT users.id,users.name,users.email,memberships.access,memberships.role,employee_credentials.employee_id FROM memberships JOIN users ON users.id=memberships.user_id LEFT JOIN employee_credentials ON employee_credentials.org_id=memberships.org_id AND employee_credentials.user_id=memberships.user_id WHERE memberships.org_id=?',(org_id,)).fetchall()
    return [{**dict(r),'email':r['email'] if org['access'] in ('owner','admin') else None} for r in rows]

@router.post('/organizations/{org_id}/invitations',status_code=201)
def invite(org_id:str,body:Invite,request:Request):
    user,org=ident.tenant(request,org_id)
    invitation_admin(org,body.access,body.role)
    with ident.database() as db:
        address=ident.email(body.email)
        if db.execute('SELECT 1 FROM memberships JOIN users ON users.id=memberships.user_id WHERE org_id=? AND email=?',(org_id,address)).fetchone(): raise HTTPException(409,'This person is already a member')
        if db.execute('SELECT 1 FROM invitations WHERE org_id=? AND email=? AND used=0 AND revoked=0 AND expires>?',(org_id,address,time.time())).fetchone(): raise HTTPException(409,'This person has a pending invitation. Replace its link instead.')
        return issue_invitation(db,org_id,user['id'],body)

@router.get('/organizations/{org_id}/invitations')
def invitations(org_id:str,request:Request):
    _,org=ident.tenant(request,org_id); invitation_admin(org)
    with ident.database(write=False) as db: rows=db.execute('SELECT * FROM invitations WHERE org_id=? ORDER BY created_at DESC,id',(org_id,)).fetchall()
    return [{**{k:r[k] for k in ('id','name','email','access','role','expires','created_at')},'status':invitation_status(r)} for r in rows]

@router.get('/organizations/{org_id}/access-events')
def access_events(org_id:str,request:Request):
    _,org=ident.tenant(request,org_id); invitation_admin(org)
    with ident.database(write=False) as db: rows=db.execute('SELECT * FROM account_events WHERE org_id=? ORDER BY created_at DESC,id',(org_id,)).fetchall()
    return [{**dict(r),'details':json.loads(r['details'])} for r in rows]

@router.delete('/organizations/{org_id}/invitations/{invitation_id}')
def revoke_invitation(org_id:str,invitation_id:str,request:Request):
    user,org=ident.tenant(request,org_id); invitation_admin(org)
    with ident.database() as db:
        row=db.execute('SELECT * FROM invitations WHERE org_id=? AND id=?',(org_id,invitation_id)).fetchone()
        if not row: raise HTTPException(404,'Invitation not found')
        invitation_admin(org,row['access'],row['role'])
        if invitation_status(row)=='accepted': raise HTTPException(409,'Manage this person through their membership')
        if not row['revoked']:
            db.execute('UPDATE invitations SET revoked=1 WHERE id=?',(invitation_id,))
            event(db,org_id,user['id'],'invitation.revoked',invitation_id,{'name':row['name'],'email':row['email']})
    return {'status':'revoked'}

@router.post('/organizations/{org_id}/invitations/{invitation_id}/replace',status_code=201)
def replace_invitation(org_id:str,invitation_id:str,request:Request):
    user,org=ident.tenant(request,org_id); invitation_admin(org)
    with ident.database() as db:
        row=db.execute('SELECT * FROM invitations WHERE org_id=? AND id=?',(org_id,invitation_id)).fetchone()
        if not row: raise HTTPException(404,'Invitation not found')
        invitation_admin(org,row['access'],row['role'])
        if invitation_status(row) not in ('pending','expired'): raise HTTPException(409,'Only pending or expired invitations can be replaced')
        db.execute('UPDATE invitations SET revoked=1 WHERE id=?',(invitation_id,))
        event(db,org_id,user['id'],'invitation.replaced',invitation_id,{'name':row['name'],'email':row['email']})
        return issue_invitation(db,org_id,user['id'],Invite(**{k:row[k] for k in ('name','email','access','role')}))

@router.get('/invitations/{token}')
def invitation(token:str):
    with ident.database(write=False) as db: row=db.execute('SELECT invitations.*,organizations.name AS organization_name FROM invitations JOIN organizations ON organizations.id=invitations.org_id WHERE token=?',(ident.digest(token),)).fetchone()
    if not row:
        from .employee_auth import public_invitation
        return public_invitation(token)
    if not row or invitation_status(row)!='pending': raise HTTPException(410,'Invitation expired, revoked or already used')
    return {'kind':'email','organization_name':row['organization_name'],'name':row['name'],'role':row['role'],'access':row['access']}

@router.post('/invitations/accept')
def join(body:Join,request:Request):
    user=ident.principal(request)
    ident.require_email_session(user)
    with ident.database() as db: org_id=accept(db,body.token,user['id'],user['email'])
    return {'organization_id':org_id}

@router.put('/organizations/{org_id}/members/{user_id}')
def member_change(org_id:str,user_id:str,body:Membership,request:Request):
    user,org=ident.tenant(request,org_id)
    if org['access']!='owner': raise HTTPException(403,'Only an owner can change membership permissions')
    with ident.database() as db:
        row=db.execute('SELECT access FROM memberships WHERE org_id=? AND user_id=?',(org_id,user_id)).fetchone()
        if not row: raise HTTPException(404,'Member not found')
        target=db.execute('SELECT name,email FROM users WHERE id=?',(user_id,)).fetchone()
        if not target['email'] and (body.access!='member' or body.role!='operator'):
            raise HTTPException(422,'Link an email account before appointing an owner, administrator, supervisor or reviewer')
        if row[0]=='owner' and body.access!='owner' and db.execute("SELECT count(*) FROM memberships WHERE org_id=? AND access='owner'",(org_id,)).fetchone()[0]<=1: raise HTTPException(409,'Keep at least one organization owner')
        db.execute('UPDATE memberships SET access=?,role=? WHERE org_id=? AND user_id=?',(body.access,body.role,org_id,user_id))
        if body.access!='member' or body.role!='operator':
            db.execute("DELETE FROM sessions WHERE org_id=? AND user_id=? AND auth_kind='employee'",(org_id,user_id))
        event(db,org_id,user['id'],'membership.updated',user_id,{**body.model_dump(),**dict(target)})
    return {'status':'saved'}

@router.delete('/organizations/{org_id}/members/{user_id}')
def member_remove(org_id:str,user_id:str,request:Request):
    user,org=ident.tenant(request,org_id)
    if org['access']!='owner': raise HTTPException(403,'Only an owner can remove members')
    with ident.database() as db:
        row=db.execute('SELECT access FROM memberships WHERE org_id=? AND user_id=?',(org_id,user_id)).fetchone()
        if not row: raise HTTPException(404,'Member not found')
        if row[0]=='owner' and db.execute("SELECT count(*) FROM memberships WHERE org_id=? AND access='owner'",(org_id,)).fetchone()[0]<=1: raise HTTPException(409,'Keep at least one organization owner')
        db.execute('DELETE FROM memberships WHERE org_id=? AND user_id=?',(org_id,user_id))
        db.execute('UPDATE employee_credentials SET active=0 WHERE org_id=? AND user_id=?',(org_id,user_id))
        db.execute("DELETE FROM sessions WHERE user_id=? AND org_id=? AND auth_kind='employee'",(user_id,org_id))
        db.execute('UPDATE employee_links SET revoked=1 WHERE org_id=? AND employee_id IN (SELECT employee_id FROM employee_credentials WHERE org_id=? AND user_id=?) AND used=0',(org_id,org_id,user_id))
        target=db.execute('SELECT name,email FROM users WHERE id=?',(user_id,)).fetchone()
        event(db,org_id,user['id'],'membership.removed',user_id,dict(target))
    return {'status':'removed'}

from .employee_auth import router as employee_router
router.include_router(employee_router)
