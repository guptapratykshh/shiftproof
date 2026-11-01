"""Dated shifts, minimal staff directory and auditable pilot administration."""
import copy
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field, ConfigDict, field_validator
from . import identity as ident, pilot_scope as scope
from .models import now, uid
from .engine import handover

router = APIRouter(prefix='/organizations/{org_id}')

class Name(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=2,max_length=100)
class Team(Name):
    location_id: str
class Shift(Team):
    starts_at: datetime
    ends_at: datetime
    team_id: str
    @field_validator('starts_at','ends_at')
    @classmethod
    def aware(cls,v):
        if v.tzinfo is None: raise ValueError('Include the organization timezone offset')
        return v
class Assignments(BaseModel):
    model_config = ConfigDict(extra='forbid')
    user_ids: list[str] = Field(max_length=100)
    supervisor_id: str | None = None
    work_item_ids: list[str] = Field(default_factory=list,max_length=500)
class Link(BaseModel):
    incoming_shift_id: str
    reason: str = Field(min_length=3,max_length=600)
class Reason(BaseModel):
    reason: str = Field(min_length=3,max_length=600)
class Policy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    data_classification: str = Field(pattern='^(fictional|real)$')
    retention_days: int = Field(ge=1,le=3650)
    recording_consent: bool = False
    provider_terms_approved: bool = False
    spending_cap_confirmed: bool = False
    factory_approval: bool = False
    max_storage_mb: int = Field(default=1024,ge=20,le=100000)

def owner(org):
    if org['access'] != 'owner': raise HTTPException(403,'Only the organization owner can manage this setting')
def supervisor(org):
    if org['role'] != 'supervisor' and not (org['access']=='owner' and org['role']=='quality'):
        raise HTTPException(403,'Assign supervisor permission to manage shifts and work')
def responsible_supervisor(state,org,user_id,shift_id):
    supervisor(org)
    shift=state['shift_occurrences'][shift_id]
    if org['access']!='owner' and (shift.get('supervisor_id')!=user_id or not scope.shift_items(state,shift_id)<=scope.permitted_items(state,org,user_id,shift_id)):
        raise HTTPException(403,'The designated supervisor with the full shift assignment must coordinate this handover')
def audit(state,actor,action,**details):
    key=uid('operation')
    state.setdefault('operational_events',{})[key]={'id':key,'actor':actor.model_dump(),'action':action,'created_at':now(),**details}

def directory_rows(org_id):
    with ident.database(write=False) as db:
        return [dict(r) for r in db.execute('SELECT users.id,users.name,memberships.role FROM users JOIN memberships ON users.id=memberships.user_id WHERE org_id=?',(org_id,)).fetchall()]

def coordinator_ids(org_id):
    """Explicit operational permission, including owners appointed as reviewers."""
    with ident.database(write=False) as db:
        return {row['user_id'] for row in db.execute(
            "SELECT user_id FROM memberships WHERE org_id=? AND (role='supervisor' OR (access='owner' AND role='quality'))", (org_id,)).fetchall()}

@router.get('/operations')
def operations(org_id:str,request:Request):
    user,org,repo,_=ident.operational(request,org_id);state=repo.load()
    shifts=scope.allowed_shifts(state,org,user['id']);ids={s['id'] for s in shifts}
    assignments=[a for a in state.get('assignments',{}).values() if a['shift_id'] in ids]
    locations=list(state.get('locations',{}).values());teams=list(state.get('teams',{}).values())
    if org['access']!='owner':
        locations=[l for l in locations if any(s['location_id']==l['id'] for s in shifts)]
        teams=[t for t in teams if any(s['team_id']==t['id'] for s in shifts)]
    return {'locations':locations,'teams':teams,'shifts':shifts,'assignments':assignments,
            'active_shift_id':scope.choose_shift(state,org,user['id']),
            'handovers':[h for sid,h in state.get('handovers',{}).items() if sid in ids]}

@router.get('/directory')
def directory(org_id:str,request:Request):
    user,org,repo,_=ident.operational(request,org_id);rows=directory_rows(org_id)
    if org['access']=='owner': return rows
    state=repo.load();ids={s['id'] for s in scope.allowed_shifts(state,org,user['id'])}
    people={a['user_id'] for a in state.get('assignments',{}).values() if a['shift_id'] in ids}|{user['id']}
    return [r for r in rows if r['id'] in people]

@router.post('/locations',status_code=201)
def location(org_id:str,body:Name,request:Request):
    _,org,repo,actor=ident.operational(request,org_id);owner(org)
    row={'id':uid('location'),**body.model_dump()}
    with repo.transaction() as state:
        state.setdefault('locations',{})[row['id']]=row;audit(state,actor,'location.created',location_id=row['id'])
    return row

@router.post('/teams',status_code=201)
def team(org_id:str,body:Team,request:Request):
    _,org,repo,actor=ident.operational(request,org_id);owner(org)
    row={'id':uid('team'),**body.model_dump()}
    with repo.transaction() as state:
        if body.location_id not in state.get('locations',{}): raise HTTPException(422,'Choose an organization location')
        state.setdefault('teams',{})[row['id']]=row;audit(state,actor,'team.created',team_id=row['id'])
    return row

@router.post('/shift-occurrences',status_code=201)
def create_shift(org_id:str,body:Shift,request:Request):
    user,org,repo,actor=ident.operational(request,org_id)
    if org['access']!='owner': supervisor(org)
    if not timedelta(0)<body.ends_at-body.starts_at<=timedelta(hours=24): raise HTTPException(422,'A dated shift must last between zero and 24 hours; include the next date for overnight shifts')
    row={'id':uid('shift'),**body.model_dump(mode='json'),'status':'open','created_at':now(),'timezone':org['timezone']}
    with repo.transaction() as state:
        team=state.get('teams',{}).get(body.team_id)
        if not team or team['location_id']!=body.location_id: raise HTTPException(422,'Choose a team in this location')
        if org['access']!='owner' and body.team_id not in {s['team_id'] for s in scope.allowed_shifts(state,org,user['id'])}:
            raise HTTPException(403,'This team is outside your assigned scope')
        state.setdefault('shift_occurrences',{})[row['id']]=row
        if org['access']!='owner':
            permitted=scope.permitted_items(state,org,user['id']) & scope.shift_items(state,row['id'])
            key=f'{row["id"]}:{user["id"]}'
            state.setdefault('assignments',{})[key]={'id':key,'shift_id':row['id'],'user_id':user['id'],'work_item_ids':sorted(permitted),'assigned_by':actor.id,'assigned_at':now()}
            row['supervisor_id']=user['id']
        audit(state,actor,'shift.created',shift_id=row['id'])
    return row

@router.put('/shift-occurrences/{shift_id}/assignments')
def assign(org_id:str,shift_id:str,body:Assignments,request:Request):
    user,org,repo,actor=ident.operational(request,org_id)
    if org['access']!='owner': supervisor(org)
    members={r['id']:r for r in directory_rows(org_id)}
    ids=set(body.user_ids)|({body.supervisor_id} if body.supervisor_id else set())
    if not ids <= members.keys(): raise HTTPException(422,'Every assignee must be an active organization member')
    if body.supervisor_id and body.supervisor_id not in coordinator_ids(org_id): raise HTTPException(422,'Select a supervisor or an owner explicitly appointed as reviewer')
    with repo.transaction() as state:
        scope.choose_shift(state,org,user['id'],shift_id)
        shift=state['shift_occurrences'][shift_id]
        responsible_supervisor(state,org,user['id'],shift_id)
        if shift['status']=='closed': raise HTTPException(409,'Closed shift assignments are historical evidence')
        if not set(body.work_item_ids)<=scope.shift_items(state,shift_id): raise HTTPException(422,'Assign only this team’s work items')
        assignments=state.setdefault('assignments',{})
        history=state.setdefault('assignment_history',{})
        change_id=uid('assignments')
        history[change_id]={'id':change_id,'shift_id':shift_id,'previous':[copy.deepcopy(a) for a in assignments.values() if a['shift_id']==shift_id],
                            'actor_id':actor.id,'created_at':now(),'reason':'Explicit assignment update'}
        for key in [k for k,a in assignments.items() if a['shift_id']==shift_id]: del assignments[key]
        for person in sorted(ids):
            key=f'{shift_id}:{person}'
            assignments[key]={'id':key,'shift_id':shift_id,'user_id':person,'work_item_ids':body.work_item_ids,'assigned_by':actor.id,'assigned_at':now()}
        shift['supervisor_id']=body.supervisor_id
        audit(state,actor,'shift.assignments.updated',shift_id=shift_id,user_ids=sorted(ids),supervisor_id=body.supervisor_id)
    return {'status':'saved'}

@router.post('/shift-occurrences/{shift_id}/incoming')
def incoming(org_id:str,shift_id:str,body:Link,request:Request):
    user,org,repo,actor=ident.operational(request,org_id);supervisor(org)
    with repo.transaction() as state:
        scope.choose_shift(state,org,user['id'],shift_id)
        responsible_supervisor(state,org,user['id'],shift_id)
        target=state.get('shift_occurrences',{}).get(body.incoming_shift_id)
        outgoing=state['shift_occurrences'][shift_id]
        if not target or target['id']==shift_id or target['team_id']!=outgoing['team_id']: raise HTTPException(422,'Choose a different incoming shift for this team')
        if not target.get('supervisor_id'): raise HTTPException(409,'Assign an incoming supervisor or an explicit substitute first')
        state.setdefault('handovers',{}).setdefault(shift_id,{'id':shift_id,'version':0})['incoming_shift_id']=target['id']
        audit(state,actor,'handover.incoming.assigned',shift_id=shift_id,incoming_shift_id=target['id'],reason=body.reason)
    return {'status':'saved'}

@router.post('/shift-occurrences/{shift_id}/close')
def close(org_id:str,shift_id:str,body:Reason,request:Request):
    user,org,repo,actor=ident.operational(request,org_id);supervisor(org)
    active_supervisors=coordinator_ids(org_id)
    with repo.transaction() as state:
        scope.choose_shift(state,org,user['id'],shift_id)
        responsible_supervisor(state,org,user['id'],shift_id)
        shift=state['shift_occurrences'][shift_id];h=state['handovers'][shift_id]
        if shift['status']=='closed': return {'status':'closed','snapshot_id':h['closed_snapshot_id']}
        if not h.get('incoming_shift_id'): raise HTTPException(409,'Assign the incoming shift and supervisor before closing')
        incoming=state['shift_occurrences'].get(h['incoming_shift_id'],{})
        if incoming.get('supervisor_id') not in active_supervisors:
            raise HTTPException(409,'The incoming supervisor is no longer authorized. Assign an explicit substitute.')
        subset=scope.filtered_state(state,scope.shift_items(state,shift_id),shift_id)
        unfinished=[n for n in subset['notes'].values() if n['status'] in ('awaiting_upload','received','failed','queued','processing','manual_review') and not n.get('carry_forward')]
        if unfinished: raise HTTPException(409,'Review, cancel or explicitly carry forward unfinished reports')
        key=f'closed:{shift_id}:{h["version"]}'
        snapshot={**copy.deepcopy(handover(subset)),'id':key,'created_at':now(),'shift_id':shift_id,'reason':body.reason}
        state['snapshots'][key]=snapshot;h['closed_snapshot_id']=key
        shift.update(status='closed',closed_at=now());audit(state,actor,'shift.closed',shift_id=shift_id,snapshot_id=key,reason=body.reason)
    return {'status':'closed','snapshot_id':key}

@router.put('/pilot-policy')
def policy(org_id:str,body:Policy,request:Request):
    _,org,repo,actor=ident.operational(request,org_id);owner(org)
    if body.data_classification=='real' and not(body.factory_approval and body.recording_consent): raise HTTPException(422,'Factory approval and recording consent are required before real recordings')
    with repo.transaction() as state:
        state['data_policy']={**body.model_dump(),'mode':body.data_classification};audit(state,actor,'data_policy.updated',policy=body.model_dump())
    return body

@router.get('/pilot-policy')
def get_policy(org_id:str,request:Request):
    _,org,repo,_=ident.operational(request,org_id);owner(org)
    from .service import provider_policy_status
    stored=repo.load().get('data_policy',{'data_classification':'fictional'})
    editable={key:value for key,value in stored.items() if key in Policy.model_fields}
    # Keep the conservative classification for legacy records as well.
    editable['data_classification']='real' if 'real' in (stored.get('mode'),stored.get('data_classification')) else stored.get('data_classification',stored.get('mode','fictional'))
    return {'policy':editable,'providers':provider_policy_status(repo)}

@router.get('/operational-events')
def events(org_id:str,request:Request,offset:int=0,limit:int=50):
    _,org,repo,_=ident.operational(request,org_id);owner(org)
    rows=list(repo.load().get('operational_events',{}).values())
    return {'items':list(reversed(rows))[max(0,offset):max(0,offset)+min(100,max(1,limit))],'total':len(rows)}
