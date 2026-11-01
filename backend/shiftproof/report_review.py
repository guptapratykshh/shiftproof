"""Atomic report decisions using the existing evidence and clearance rules."""
from contextlib import contextmanager
import hashlib
import json
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from . import service
from .models import Candidate, ResolveRequest, TranscriptReview, now, uid

class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    claim_id: str | None = None
    candidate: Candidate | None = None
    action: Literal['confirm', 'reject', 'draft']
    supersedes: list[str] = Field(default_factory=list, max_length=12)
    reason: str = Field(min_length=3, max_length=600)

class ReportReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int
    request_id: str = Field(min_length=8, max_length=100)
    decisions: list[Decision] = Field(min_length=1, max_length=12)

class Reopen(BaseModel):
    expected_version: int
    reason: str = Field(min_length=3, max_length=600)

class StateRepository:
    # Reuse the single-claim services inside ONE outer SQLite transaction.
    def __init__(self, state): self.state = state
    @contextmanager
    def transaction(self): yield self.state

def progress(note, claims):
    current = [c for c in claims if c['id'] in note['claim_ids'] and c['status'] not in ('rejected','superseded')]
    reopenable = note.get('review_outcome', {}).get('action') == 'no_operational_claims' and not note['claim_ids'] and note['status'] == 'processed'
    pending = [c for c in current if c['status'] != 'confirmed' or c.get('source_review_pending')]
    stage = 'closed_without_update' if reopenable else 'needs_help' if note['status'] in ('failed','manual_review') else 'checked' if current and not pending else 'awaiting_review'
    return {'state':stage,'checked_count':len(current)-len(pending),'pending_count':len(pending),'can_reopen':reopenable}

def reopen(repo, note_id, body, actor, sid):
    if actor.role not in ('supervisor','quality'): raise HTTPException(403,'A supervisor must reopen this report')
    with service.note_transaction(repo,note_id) as state:
        from .pilot_scope import check_handover_version
        check_handover_version(state,sid,body.expected_version)
        note=service.get_note(state,note_id)
        if not progress(note,[])['can_reopen']: raise HTTPException(409,'Only reports closed without work updates can be reopened')
        row={'id':uid('reopen'),'note_id':note_id,'action':'reopen_report','reason':body.reason,'actor':actor.model_dump(),'created_at':now(),'previous_outcome':note.get('review_outcome')}
        state['resolutions'][row['id']]=row
        note.update(status='manual_review',processing_stage='review_required',error=None,error_category=None)
        state['version']+=1
        return row

def review(repo,note_id,body,actor,sid):
    if actor.role not in ('supervisor','quality'): raise HTTPException(403,'A supervisor must review reports')
    with service.note_transaction(repo,note_id) as state:
        note=service.get_note(state,note_id)
        fingerprint=hashlib.sha256(json.dumps(body.model_dump(exclude={'expected_version'}),sort_keys=True,default=str).encode()).hexdigest()
        key=f'report-review:{note_id}:{body.request_id}'
        previous=state['resolutions'].get(key)
        if previous:
            if previous['fingerprint']!=fingerprint or previous['actor']['id']!=actor.id: raise HTTPException(409,'Review request already used')
            return previous
        from .pilot_scope import check_handover_version
        from .profiles import clearance, review_protected
        check_handover_version(state,sid,body.expected_version)
        if note['status'] in ('processing','queued','discarded','awaiting_upload') or not note['transcripts']:
            raise HTTPException(409,'Wait for the saved transcript before reviewing')
        if progress(note,[])['can_reopen']: raise HTTPException(409,'Reopen this report before reviewing it')
        ids=[]; candidates=[]
        for d in body.decisions:
            if (d.claim_id is None)==(d.candidate is None): raise HTTPException(422,'Choose an existing statement or a new interpretation')
            if d.claim_id:
                if d.claim_id not in note['claim_ids'] or d.claim_id in ids: raise HTTPException(422,'Choose each statement from this report only once')
                ids.append(d.claim_id)
                c=state['claims'][d.claim_id]
            else:
                if d.action=='reject': raise HTTPException(422,'New interpretations must be saved or confirmed')
                candidates.append(d.candidate); c=d.candidate.model_dump()
            if (clearance(c) or review_protected(c) or d.supersedes) and d.reason in ('Checked against the recording','रिकॉर्डिंग सुनकर जाँच की'):
                raise HTTPException(422,'Explain this protected or conflicting decision specifically')
        memory=StateRepository(state)
        new_ids=[]
        if candidates:
            # Evidence validation is shared; no inference is made from free-text reasons.
            from .providers import validate_extraction
            from .profiles import PROFILES
            context={'clarification':note.get('clarification_context'),'workflow':PROFILES[state.get('profile','manufacturing')]}
            raw=[c.model_dump(mode='json') for c in candidates]
            if context['clarification']:
                for c in raw:c['context_refs']=[context['clarification']['id']]
            try: parsed=validate_extraction({'claims':raw},note['transcripts'][-1]['text'],context)
            except ValueError as exc: raise HTTPException(422,str(exc)) from exc
            for c in parsed.claims:
                cid=uid('human-claim'); claim=c.model_dump(mode='json')
                claim.update(id=cid,batch_id=note['batch_id'],note_id=note_id,transcript_revision=note['revision'],actor=note['actor'],received_at=note['received_at'],status='draft',introduced_version=state['version']+1,supersedes=[],batch_mismatch=False,extraction_provider='human',interpreted_by=actor.model_dump())
                state['claims'][cid]=claim;note['claim_ids'].append(cid);new_ids.append(cid)
        index=0
        for d in body.decisions:
            cid=d.claim_id
            if not cid:cid=new_ids[index];index+=1
            if d.action!='draft':
                service.resolve(memory,cid,ResolveRequest(expected_version=state['version'],action=d.action,reason=d.reason,supersedes=d.supersedes),actor)
        previous_error = {'message': note.get('error'), 'category': note.get('error_category')}
        note.update(status='processed',error=None,error_category=None)
        if new_ids:note['extraction_provider']='human'
        related=[state['claims'][cid] for cid in note['claim_ids']]
        note['processing_stage']='complete' if all(c['status'] in ('confirmed','rejected','superseded') and not c.get('source_review_pending') for c in related) else 'review_required'
        state['version']+=1
        result={'id':key,'note_id':note_id,'action':'report_review','previous_error':previous_error,'actor':actor.model_dump(),'created_at':now(),'fingerprint':fingerprint,'claim_ids':ids+new_ids,'reason':'; '.join(dict.fromkeys(d.reason for d in body.decisions)),'decisions':[d.model_dump(mode='json') for d in body.decisions]}
        state['resolutions'][key]=result
        return result
