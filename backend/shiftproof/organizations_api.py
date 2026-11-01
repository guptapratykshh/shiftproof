"""Organization operations; authorization and assignment scope precede every access."""
import copy
import hashlib
import os
import shutil
import time
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Request, Response, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from . import identity as ident, service, providers, pilot_scope as scope
from .models import NoteCreate, ResolveRequest, AckRequest, RevisionRequest, TranscriptReview, QuestionRequest, TaskUpdate, uid, now
from .engine import handover, answer_question
from .pilot_api import audit, directory_rows, supervisor
from . import report_review

router=APIRouter(prefix='/organizations/{org_id}')
class WorkItem(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str=Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
    name:str=Field(min_length=2,max_length=120)
    line:str=Field(default='',max_length=120)
    target:int=Field(default=0,ge=0,le=1000000000)
    location_id:str|None=None
    team_id:str|None=None
    required_dispatch_quantity:int|None=Field(default=None,ge=1,le=1000000000)
class ItemUpdate(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    line:str=Field(default='',max_length=120)
    target:int=Field(default=0,ge=0,le=1000000000)
    required_dispatch_quantity:int|None=Field(default=None,ge=1,le=1000000000)
    expected_version:int
class Transcript(BaseModel): transcript:str=Field(min_length=1,max_length=4000)
class Process(BaseModel): transcribe_only:bool=False
class Speech(BaseModel):
    batch_id:str
    kind:Literal['clarification','handover']='clarification'
    expected_version:int
    language:Literal['hi','en']='hi'
class Recovery(BaseModel):
    action:Literal['cancel','carry_forward','takeover']
    reason:str=Field(min_length=3,max_length=600)
class ExceptionRequest(BaseModel):
    reason:str=Field(min_length=10,max_length=600)
    expected_version:int
class AssistedGrant(BaseModel):
    user_id:str
    shift_ids:list[str]=Field(max_length=100)

@router.get('/assisted-capture')
def assisted_options(org_id:str,request:Request):
    user,org,repo,_,state,sid=context(org_id,request)
    from .assisted import validate
    people=[]
    grants=state.get('assisted_capture_permissions',{})
    if sid in grants.get(user['id'],[]):
        allowed=scope.permitted_items(state,org,user['id'],sid)
        helper_items=set()
        for assignment in state.get('assignments',{}).values():
            if assignment['user_id']==user['id'] and assignment['shift_id']==sid:
                helper_items.update(set(assignment.get('work_item_ids') or allowed) & allowed)
        for person in directory_rows(org_id):
            if person['id']==user['id'] or person['role']!='operator':continue
            work=set()
            for assignment in state.get('assignments',{}).values():
                if assignment['user_id']==person['id'] and assignment['shift_id']==sid:
                    work.update(helper_items & set(assignment.get('work_item_ids') or allowed))
            if work:people.append({'id':person['id'],'name':person['name'],'work_item_ids':sorted(work)})
    return {'workers':people,'permissions':state.get('assisted_capture_permissions',{}) if org['access']=='owner' else {}}

@router.put('/assisted-capture')
def assisted_grant(org_id:str,body:AssistedGrant,request:Request):
    _,org,repo,actor=ident.operational(request,org_id)
    if org['access']!='owner':raise HTTPException(403,'Only the owner can grant assisted capture')
    if body.user_id not in {p['id'] for p in directory_rows(org_id)}:raise HTTPException(422,'Choose an active member')
    with repo.transaction() as state:
        if any(not any(a['user_id']==body.user_id and a['shift_id']==sid for a in state.get('assignments',{}).values()) for sid in body.shift_ids):raise HTTPException(422,'Assign the helper to each shift first')
        state.setdefault('assisted_capture_permissions',{})[body.user_id]=list(dict.fromkeys(body.shift_ids))
        audit(state,actor,'assisted_capture.permission',user_id=body.user_id,shift_ids=body.shift_ids)
    return {'status':'saved'}

def context(org_id,request,shift_id=None):
    user,org,repo,actor=ident.operational(request,org_id);state=repo.load_index()
    sid=scope.choose_shift(state,org,user['id'],shift_id or request.headers.get('X-Shift-ID'))
    state=repo.load() if sid=='shift-B' else repo.load_scoped(scope.permitted_items(state,org,user['id'],sid),shift_ids=[sid] if sid else [])
    return user,org,repo,actor,state,sid

def scoped_note(org_id,note_id,request,action='read'):
    user,org,repo,actor,state,sid=context(org_id,request)
    n=service.get_note(state,note_id)
    scope.require_item(state,org,user['id'],n['batch_id'],sid)
    if action=='process': scope.assert_note_access(state,org,user['id'],n,action)
    return user,org,repo,actor,state,sid,n

def view(state,org,user,sid):
    subset=scope.filtered_state(state,scope.permitted_items(state,org,user['id'],sid),sid)
    result=handover(subset)
    result['shift_id']=sid
    from .summary import build
    result['summary']=build(result,org['id'])
    result['incoming_shift_id']=state.get('handovers',{}).get(sid,{}).get('incoming_shift_id')
    result['legacy_archive']=sid=='shift-B'
    result['unfinished_notes']=[{'id':n['id'],'batch_id':n['batch_id'],'status':n['status'],'carry_forward':n.get('carry_forward')} for n in subset['notes'].values() if n['status'] in ('awaiting_upload','received','failed','queued','processing','manual_review')]
    result['acknowledgement_blockers']=[{**{k:n.get(k) for k in ('id','batch_id','status','processing_stage','error_category','received_at')},'actor_name':n['actor']['name'],'transcript_preview':n['transcripts'][-1]['text'][:180] if n['transcripts'] else ''} for n in subset['notes'].values() if n['status'] in ('awaiting_upload','received','failed','queued','processing','manual_review') and not n.get('carry_forward')]
    return subset,result

@router.get('/workspace')
def workspace(org_id:str,request:Request,shift_id:str|None=None,offset:int=0,limit:int=50):
    user,org,repo,actor,state,sid=context(org_id,request,shift_id)
    subset,result=view(state,org,user,sid)
    notes=sorted(subset['notes'].values(),key=lambda n:n['received_at'],reverse=True)
    for n in notes:
        n['review_progress']=report_review.progress(n,subset['claims'].values())
        n['permitted_actions']=['review'] if org['role'] in ('supervisor','quality') else []
        if n['review_progress']['can_reopen'] and n['permitted_actions']:n['permitted_actions'].append('reopen')
    offset=max(0,offset);limit=max(1,min(100,limit))
    return {**result,'organization':org,'actor':actor.model_dump(),'notes':notes[offset:offset+limit],
            'notes_total':len(notes),'next_offset':offset+limit if offset+limit<len(notes) else None,
            'resolutions':list(subset['resolutions'].values()),'allowed_shifts':[
                {**s, 'capture_allowed':org['access']=='owner' or any(a['user_id']==user['id'] and a['shift_id']==s['id'] for a in state.get('assignments',{}).values()),
                 'capture_item_ids':sorted(scope.permitted_items(state,org,user['id'],s['id']))}
                for s in scope.allowed_shifts(state,org,user['id'])],
            'active_shift_id':sid,'assignment_required':sid is None,
            'data_mode':state.get('data_policy',{}).get('data_classification','unconfigured' if os.getenv('SHIFTPROOF_REQUIRE_DATA_POLICY','false').lower()=='true' else 'fictional'),
            'capture_policy_ready':bool(state.get('data_policy')) or os.getenv('SHIFTPROOF_REQUIRE_DATA_POLICY','false').lower()!='true'}

def check_item_team(state,org,user_id,body):
    if body.team_id or body.location_id:
        team=state.get('teams',{}).get(body.team_id)
        if not team or team['location_id']!=body.location_id: raise HTTPException(422,'Choose a team in this location')
    if org['access']!='owner':
        if not body.team_id or body.team_id not in {s['team_id'] for s in scope.allowed_shifts(state,org,user_id)}:
            raise HTTPException(403,'Create work only in your assigned team')

@router.post('/work-items',status_code=201)
def create_item(org_id:str,body:WorkItem,request:Request):
    user,org,repo,actor=ident.operational(request,org_id);supervisor(org)
    with repo.transaction() as state:
        check_item_team(state,org,user['id'],body)
        if body.id in state['work_items']: raise HTTPException(409,'This identifier is already in use')
        state['work_items'][body.id]=body.model_dump();state['version']+=1
        audit(state,actor,'work_item.created',work_item_id=body.id)
    return body

@router.put('/work-items/{item_id}')
def edit_item(org_id:str,item_id:str,body:ItemUpdate,request:Request):
    user,org,repo,actor,_,sid=context(org_id,request);supervisor(org)
    with repo.transaction() as state:
        scope.require_item(state,org,user['id'],item_id,sid);scope.check_handover_version(state,sid,body.expected_version)
        values=body.model_dump(exclude={'expected_version'},exclude_unset=True)
        if any(state['work_items'][item_id].get(k)!=v for k,v in values.items()):
            state['work_items'][item_id].update(values);state['version']+=1
            audit(state,actor,'work_item.updated',work_item_id=item_id)
    return {'status':'saved'}

@router.post('/work-items/{item_id}/quantity-exception')
def quantity_exception(org_id:str,item_id:str,body:ExceptionRequest,request:Request):
    user,org,repo,actor,_,sid=context(org_id,request);supervisor(org)
    with repo.transaction() as state:
        scope.require_item(state,org,user['id'],item_id,sid);scope.check_handover_version(state,sid,body.expected_version)
        from .engine import batch_view
        current=batch_view(state,state['work_items'][item_id])
        required=state['work_items'][item_id].get('required_dispatch_quantity')
        if required is None or current['quantity'] is None or current['quantity']>=required:
            raise HTTPException(409,'A quantity exception needs an unmet requirement and a human-reviewed partial quantity')
        row={'reason':body.reason,'actor':actor.model_dump(),'created_at':now(),
             'required_dispatch_quantity':required,'accepted_quantity':current['quantity'],
             'claim_ids':[c['id'] for c in current['claims'] if c['property']=='quantity' and c['status']=='confirmed']}
        state.setdefault('quantity_exceptions',{})[item_id]=row;state['version']+=1
        audit(state,actor,'quantity.partial_exception',work_item_id=item_id,reason=body.reason)
    return row

@router.get('/export')
def export(org_id:str,request:Request):
    _,org,repo,_=ident.operational(request,org_id)
    if org['access']!='owner': raise HTTPException(403,'Only the organization owner can export organization records')
    return repo.load()

@router.post('/notes',status_code=201)
def create_note(org_id:str,body:NoteCreate,request:Request):
    user,org,repo,actor,state,sid=context(org_id,request,body.shift_id)
    late=scope.check_capture(state,org,user['id'],body.batch_id,sid,body.recorded_at)
    scope.check_data_capture_policy(state)
    from .assisted import validate
    reporter=validate(state,org_id,user['id'],body.reported_by_id,sid,body.batch_id,body.recorded_at)
    if body.reported_by_id==user['id']:body=body.model_copy(update={'reported_by_id':None})
    supplied=body.clarification_context
    stale=bool(body.clarification_ref and body.clarification_version is not None and body.clarification_version != (state.get('handovers',{}).get(sid,{}).get('version') if sid!='shift-B' else state['version']))
    original_ref=body.clarification_ref
    capture_id='note_'+hashlib.sha256(f'{actor.id}:{body.idempotency_key}'.encode()).hexdigest()[:24]
    existing=state['notes'].get(capture_id)
    if stale and supplied and not existing:
        if not isinstance(supplied.get('text'),str) or not 1<=len(supplied['text'])<=2000 or supplied.get('id')!=original_ref:
            raise HTTPException(422,'Retain the exact clarification question with this draft')
        # Client-held old questions are evidence, not trusted interpretation instructions.
        body=body.model_copy(update={'clarification_ref':None,'clarification_version':None})
    with repo.transaction(batch_ids=[body.batch_id],record_ids={'notes':[capture_id]}) as current:
        saved=service.create_note_in_state(current,body.model_copy(update={'shift_id':sid}),actor)
        if reporter:
            saved.setdefault('reported_by',reporter)
            saved.setdefault('assisted_by',actor.model_dump())
        saved.setdefault('late_submission',late);saved.setdefault('addendum',late and state.get('shift_occurrences',{}).get(sid,{}).get('status')=='closed')
        if stale and supplied:
            saved.update(clarification_ref=original_ref,clarification_context={'id':original_ref,'text':supplied['text'],'version':supplied.get('version',body.clarification_version),'unverified_client_context':True},stale_clarification=True)
        note=copy.deepcopy(saved)
    return {'note':note,'upload_url':f'/organizations/{org_id}/notes/{note["id"]}/audio','upload_headers':{'Content-Type':'audio/wav'}}

@router.get('/notes/{note_id}')
def note(org_id:str,note_id:str,request:Request):
    _,_,_,_,state,sid,n=scoped_note(org_id,note_id,request)
    version=state.get('handovers',{}).get(sid,{}).get('version',state['version'])
    return {**n,'claims':[state['claims'][c] for c in n['claim_ids']],'review_progress':report_review.progress(n,state['claims'].values()),'version':version}

async def wav_body(request):
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>4500000: raise HTTPException(413,'Recording too large')
    duration=service.validate_audio(bytes(data))
    return bytes(data),duration

def check_storage(state,size,repo):
    maximum=state.get('data_policy',{}).get('max_storage_mb',1024)*1024*1024
    used=state.get('storage_bytes')
    if used is None:
        used=sum(p.stat().st_size for p in repo.data_dir.rglob('*.wav') if p.is_file())
    if used+size>maximum: raise HTTPException(507,'Organization recording storage is full. Keep the recording on your phone and contact the owner.')
    state['storage_bytes']=used+size

def check_disk_space(repo,size):
    reserve=int(os.getenv('SHIFTPROOF_MIN_FREE_STORAGE_BYTES',str(128*1024*1024)))
    if shutil.disk_usage(repo.data_dir).free < size+reserve:
        raise HTTPException(507,'The server is running out of recording storage. Keep this draft on your phone and contact the owner.')

@router.put('/notes/{note_id}/audio')
async def upload(org_id:str,note_id:str,request:Request):
    _,org,repo,actor,_,_,n=scoped_note(org_id,note_id,request)
    imported=(n.get('supervised_import') or {}).get('actor',{}).get('id')==actor.id
    if imported: supervisor(org)
    else: service.owner_check(n,actor)
    data,duration=await wav_body(request);digest=hashlib.sha256(data).hexdigest()
    # Reauthorize after potentially interrupted upload; removal takes effect now.
    scoped_note(org_id,note_id,request)
    from .assisted import validate_note
    validate_note(repo,n)
    path=repo.data_dir/n['audio_key'];path.parent.mkdir(parents=True,exist_ok=True)
    check_disk_space(repo,len(data))
    temporary=path.with_name(uid('upload')+'.tmp')
    try:
        temporary.write_bytes(data)
        with repo.transaction(batch_ids=[n['batch_id']]) as state:
            n=service.get_note(state,note_id)
            if n.get('audio_digest')==digest: return {'duration_seconds':n['duration_seconds'],'duplicate':True}
            if n['status']!='awaiting_upload': raise HTTPException(409,'Original audio cannot be replaced')
            check_storage(state,len(data),repo)
            try: os.link(temporary,path)
            except FileExistsError:
                if hashlib.sha256(path.read_bytes()).hexdigest()!=digest: raise HTTPException(409,'Original audio cannot be replaced')
            n.update(has_audio=True,duration_seconds=duration,status='received',audio_digest=digest,audio_bytes=len(data),audio_quality=service.audio_quality(data))
    finally: temporary.unlink(missing_ok=True)
    return {'duration_seconds':duration}

@router.get('/notes/{note_id}/audio')
def audio(org_id:str,note_id:str,request:Request):
    _,_,repo,_,_,_,n=scoped_note(org_id,note_id,request)
    if not n['has_audio']: raise HTTPException(404,'No recording for this note')
    return Response(service.read_audio(n,repo.data_dir),media_type='audio/wav',headers={'Cache-Control':'private, no-store'})

@router.post('/notes/{note_id}/transcript')
def transcript(org_id:str,note_id:str,body:Transcript,request:Request):
    _,_,repo,actor,_,_,_=scoped_note(org_id,note_id,request)
    return service.submit_transcript(repo,note_id,body.transcript,actor)

@router.post('/notes/{note_id}/revisions')
def revise(org_id:str,note_id:str,body:RevisionRequest,request:Request):
    _,_,repo,actor,_,sid,_=scoped_note(org_id,note_id,request)
    return service.submit_transcript(repo,note_id,body.transcript,actor,body.expected_version,sid)

@router.post('/notes/{note_id}/process',status_code=202)
def process(org_id:str,note_id:str,body:Process,request:Request,tasks:BackgroundTasks):
    _,_,repo,actor,_,_,n=scoped_note(org_id,note_id,request,'process')
    from .assisted import validate_note
    validate_note(repo,n)
    if (n.get('supervised_import') or {}).get('audio_expected') and not n.get('has_audio'):
        raise HTTPException(409,'Upload the retained original recording before processing this recovered report')
    def submitted():
        if not body.transcribe_only:
            with repo.transaction(batch_ids=[n['batch_id']]) as state:
                saved=state['notes'][note_id]
                if saved.get('submitted_revision') != saved['revision']:
                    saved.update(submitted_at=now(),submitted_revision=saved['revision'])
    if n.get('stale_clarification') and not body.transcribe_only:
        submitted()
        with repo.transaction(batch_ids=[n['batch_id']]) as state:
            state['notes'][note_id].update(status='manual_review',processing_stage='review_required',error='A supervisor must review this answer with its saved earlier question.',error_category='stale_clarification')
        return {'job_id':note_id,'status_url':f'/organizations/{org_id}/notes/{note_id}'}
    if os.getenv('SHIFTPROOF_DURABLE_JOBS','false').lower()=='true':
        from .durable_jobs import enqueue
        job=enqueue(repo,note_id,actor,stage='transcribe' if body.transcribe_only else 'extract')
        submitted()
        return {'job_id':job['id'],'status_url':f'/organizations/{org_id}/notes/{note_id}'}
    if not(body.transcribe_only and n['transcripts']) and service.mark_queued(repo,note_id,actor,allow_reviewer=True):
        tasks.add_task(service.process_note,repo,note_id,body.transcribe_only)
    submitted()
    return {'job_id':note_id,'status_url':f'/organizations/{org_id}/notes/{note_id}'}

@router.post('/notes/{note_id}/review-transcript')
def interpret(org_id:str,note_id:str,body:TranscriptReview,request:Request):
    _,_,repo,actor,_,sid,_=scoped_note(org_id,note_id,request)
    return service.review_transcript(repo,note_id,body.model_copy(update={'scope_shift_id':sid}),actor)

@router.delete('/notes/{note_id}')
def discard(org_id:str,note_id:str,request:Request):
    _,_,repo,actor,_,_,n=scoped_note(org_id,note_id,request)
    with repo.transaction(batch_ids=[n['batch_id']]) as state:
        n=service.get_note(state,note_id);service.owner_check(n,actor)
        if n['claim_ids'] or n['status'] in ('processing','queued'): raise HTTPException(409,'Review the source instead of discarding it')
        if n['status']!='discarded': n['status']='discarded';state['version']+=1
    return {'status':'discarded'}

@router.post('/notes/{note_id}/review')
def review_report(org_id:str,note_id:str,body:report_review.ReportReview,request:Request):
    _,_,repo,actor,_,sid,_=scoped_note(org_id,note_id,request)
    return report_review.review(repo,note_id,body,actor,sid)

@router.post('/notes/{note_id}/reopen')
def reopen_report(org_id:str,note_id:str,body:report_review.Reopen,request:Request):
    _,_,repo,actor,_,sid,_=scoped_note(org_id,note_id,request)
    return report_review.reopen(repo,note_id,body,actor,sid)

@router.post('/notes/{note_id}/recover')
def recover(org_id:str,note_id:str,body:Recovery,request:Request):
    _,org,repo,actor,_,_,n=scoped_note(org_id,note_id,request)
    if actor.role not in ('supervisor','quality'): raise HTTPException(403,'A scoped supervisor or reviewer must recover this report')
    with repo.transaction(batch_ids=[n['batch_id']]) as state:
        n=service.get_note(state,note_id)
        if body.action=='cancel':
            if n['claim_ids']: raise HTTPException(409,'Review existing interpretations; their source cannot be cancelled')
            n.update(status='discarded',cancelled_reason=body.reason,cancelled_by=actor.model_dump(),cancelled_at=now())
        elif body.action=='carry_forward': n['carry_forward']={'reason':body.reason,'actor':actor.model_dump(),'created_at':now()}
        else: n['processing_takeover']={'actor':actor.model_dump(),'reason':body.reason,'created_at':now()}
        for job in state.get('jobs',{}).values():
            if job.get('note_id')==note_id and job.get('status') in ('queued','processing','leased','running'):
                job.update(status='cancelled',lease_token=None)
        if body.action=='takeover' and n['status'] in ('queued','processing'): n['status']='failed'
        state['version']+=1;audit(state,actor,'note.'+body.action,note_id=note_id,reason=body.reason)
    return {'status':'saved','author_preserved':True}

@router.get('/jobs/{job_id}')
def job(org_id:str,job_id:str,request:Request):
    user,org,repo,_,state,sid=context(org_id,request)
    row=state.get('jobs',{}).get(job_id)
    if not row: raise HTTPException(404,'Job not found')
    n=service.get_note(state,row.get('note_id',job_id));scope.require_item(state,org,user['id'],n['batch_id'],sid)
    return {k:v for k,v in row.items() if k not in ('lease_token',)}

@router.post('/claims/{claim_id}/resolve')
def resolve(org_id:str,claim_id:str,body:ResolveRequest,request:Request):
    user,org,repo,actor,state,sid=context(org_id,request)
    c=state['claims'].get(claim_id)
    if not c: raise HTTPException(404,'Report not found')
    scope.require_item(state,org,user['id'],c['batch_id'],sid)
    return service.resolve(repo,claim_id,body.model_copy(update={'scope_shift_id':sid}),actor)

@router.post('/questions')
def question(org_id:str,body:QuestionRequest,request:Request):
    user,org,_,_,state,sid=context(org_id,request);scope.require_item(state,org,user['id'],body.batch_id,sid)
    subset,_=view(state,org,user,sid)
    return answer_question(subset,body.batch_id,body.question)

@router.post('/shifts/{shift_id}/acknowledgements')
def acknowledge(org_id:str,shift_id:str,body:AckRequest,request:Request):
    user,org,repo,actor,_,sid=context(org_id,request,shift_id)
    if sid=='shift-B': return service.acknowledge(repo,body.model_copy(update={'scope_shift_id':sid}),actor)
    with repo.transaction() as state:
        scope.check_handover_version(state,sid,body.expected_version)
        incoming=state['handovers'][sid].get('incoming_shift_id')
        assigned_to=incoming or sid
        if not any(a['user_id']==user['id'] and a['shift_id']==assigned_to for a in state.get('assignments',{}).values()):
            raise HTTPException(403,'Only assigned handover recipients can acknowledge receipt')
        subset,result=view(state,org,user,sid)
        unfinished=[n for n in subset['notes'].values() if n['status'] in ('queued','processing','awaiting_upload','received','failed','manual_review') and not n.get('carry_forward')]
        if unfinished: raise HTTPException(409,'Ask a supervisor to review or carry forward unfinished reports before acknowledgement')
        if body.audio_id:
            recording=state.get('ack_audio',{}).get(body.audio_id)
            if not recording or recording['actor_id']!=actor.id or recording['shift_id']!=sid or recording['version']!=body.expected_version: raise HTTPException(409,'Record acknowledgement for this handover version')
        key=f'{actor.id}:{sid}:{body.expected_version}';snapshot_id=f'handover:{sid}:{body.expected_version}:{actor.id}'
        state['snapshots'].setdefault(snapshot_id,{**copy.deepcopy(result),'id':snapshot_id,'shift_id':sid,'created_at':now()})
        ack={'id':key,'shift_id':sid,'version':body.expected_version,'snapshot_id':snapshot_id,'actor':actor.model_dump(),'readback':body.readback,'audio_id':body.audio_id,'created_at':now()}
        state['acknowledgements'].setdefault(key,ack)
        return state['acknowledgements'][key]

@router.post('/shifts/{shift_id}/acknowledgements/audio',status_code=201)
async def ack_audio(org_id:str,shift_id:str,request:Request):
    user,org,repo,actor,state,sid=context(org_id,request,shift_id)
    data,duration=await wav_body(request);context(org_id,request,shift_id)
    if service.audio_quality(data)['silent']:
        raise HTTPException(422, 'No sound was captured. Test or change the microphone, then record again.')
    key=uid('ack');path=repo.data_dir/'acknowledgements'/f'{key}.wav';path.parent.mkdir(parents=True,exist_ok=True)
    version=state.get('handovers',{}).get(sid,{}).get('version',state['version'])
    check_disk_space(repo,len(data))
    try:
        path.write_bytes(data)
        with repo.transaction() as current:
            scope.check_handover_version(current,sid,version);check_storage(current,len(data),repo)
            current.setdefault('ack_audio',{})[key]={'id':key,'shift_id':sid,'version':version,'actor_id':actor.id,'audio_key':f'acknowledgements/{key}.wav','audio_bytes':len(data),'duration_seconds':duration,'created_at':now(),
                'work_item_ids':sorted(scope.permitted_items(current,org,user['id'],sid))}
    except BaseException:
        path.unlink(missing_ok=True);raise
    return {'audio_id':key,'version':version}

@router.get('/shifts/{shift_id}/acknowledgements/audio/{audio_id}')
def get_ack_audio(org_id:str,shift_id:str,audio_id:str,request:Request):
    user,org,repo,actor,state,sid=context(org_id,request,shift_id)
    row=state.get('ack_audio',{}).get(audio_id)
    if not row or row['shift_id']!=sid or (row['actor_id']!=actor.id and org['role']=='operator' and org['access']!='owner'): raise HTTPException(404,'Acknowledgement recording not found')
    if org['access']!='owner' and ('work_item_ids' not in row or not set(row['work_item_ids']) <= scope.permitted_items(state,org,user['id'],sid)):
        raise HTTPException(404,'This receipt includes work no longer assigned to you')
    return Response((repo.data_dir/row['audio_key']).read_bytes(),media_type='audio/wav')

@router.get('/shifts/{shift_id}/handover')
def get_handover(org_id:str,shift_id:str,request:Request):
    user,org,_,_,state,sid=context(org_id,request,shift_id)
    return view(state,org,user,sid)[1]

@router.get('/shifts/{shift_id}/snapshots/{version}')
def snapshot(org_id:str,shift_id:str,version:int,request:Request):
    user,org,_,_,state,sid=context(org_id,request,shift_id)
    key=f'handover:{version}' if sid=='shift-B' else f'handover:{sid}:{version}:{user["id"]}'
    snap=state['snapshots'].get(key)
    if not snap: raise HTTPException(404,'Snapshot not found')
    if not {b['id'] for b in snap.get('batches',[])} <= scope.permitted_items(state,org,user['id'],sid):
        raise HTTPException(404,'This historical snapshot includes work no longer assigned to you')
    return snap

@router.get('/shifts/{shift_id}/closed-snapshot')
def closed_snapshot(org_id:str,shift_id:str,request:Request):
    user,org,_,_,state,sid=context(org_id,request,shift_id)
    key=state.get('handovers',{}).get(sid,{}).get('closed_snapshot_id')
    snap=state['snapshots'].get(key)
    if not snap or not {b['id'] for b in snap.get('batches',[])} <= scope.permitted_items(state,org,user['id'],sid):
        raise HTTPException(404,'The complete closed snapshot is not available within your current assignment')
    return snap

@router.post('/tasks/{claim_id}')
def task(org_id:str,claim_id:str,body:TaskUpdate,request:Request):
    user,org,repo,actor,state,sid=context(org_id,request);c=state['claims'].get(claim_id)
    if not c: raise HTTPException(404,'Task not found')
    scope.require_item(state,org,user['id'],c['batch_id'],sid)
    if body.action=='assign':
        supervisor(org)
        if not body.owner_id: raise HTTPException(422,'Select a named active team member')
        members={r['id']:r for r in directory_rows(org_id)};person=members.get(body.owner_id)
        if not person: raise HTTPException(422,'Select an active organization member')
        if sid!='shift-B' and not any(a['user_id']==body.owner_id and a['shift_id']==sid and (not a.get('work_item_ids') or c['batch_id'] in a['work_item_ids']) for a in state.get('assignments',{}).values()): raise HTTPException(422,'Assign a person responsible for this work item in this shift')
        body=body.model_copy(update={'owner':person['name']})
    return service.update_task(repo,claim_id,body.model_copy(update={'scope_shift_id':sid}),actor)

@router.post('/speech')
def speech(org_id:str,body:Speech,request:Request):
    user,org,repo,_,state,sid=context(org_id,request);scope.check_handover_version(state,sid,body.expected_version)
    _,snapshot=view(state,org,user,sid)
    views=[v for v in snapshot['batches'] if body.batch_id=='all' or v['id']==body.batch_id]
    if not views: raise HTTPException(404,'Work item not found')
    if body.kind=='clarification':
        if not views[0]['clarification']: raise HTTPException(404,'No clarification is needed')
        text=views[0]['clarification']['text']
    else:
        from .summary import speech_text
        text=speech_text(snapshot['summary'],body.batch_id,body.language)
        if not text:text='अभी कोई रिपोर्ट नहीं है।' if body.language=='hi' else 'No reports yet.'
    service.check_provider_policy(repo,'speech');service.reserve_usage(repo,'speech_calls');started=time.monotonic()
    audio=providers.synthesize(text, language="en") if body.language=="en" and body.kind=="handover" else providers.synthesize(text)
    # Synthesis can take seconds: never deliver an old or newly unauthorized snapshot.
    _,_,_,_,latest,latest_sid=context(org_id,request)
    if latest_sid!=sid:raise HTTPException(409,'The active shift changed. Listen to the latest update.')
    scope.check_handover_version(latest,sid,body.expected_version)
    return Response(audio,media_type='audio/wav',headers={'Cache-Control':'private, no-store','X-Summary-Version':str(body.expected_version),'X-Summary-Language':body.language,'Server-Timing':f'tts;dur={(time.monotonic()-started)*1000:.2f}'})
