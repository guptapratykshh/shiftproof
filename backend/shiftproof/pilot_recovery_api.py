"""Audited coordinator imports for recordings kept offline beyond 72 hours."""
import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import identity as ident, pilot_scope as scope, service
from .models import Actor, NoteCreate, now
from .pilot_api import audit, supervisor
from .repository import Conflict

router = APIRouter(prefix='/organizations/{org_id}')


class RecoveredCapture(BaseModel):
    model_config = ConfigDict(extra='forbid')
    note: NoteCreate
    original_actor_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=10, max_length=600)
    transcript: str | None = Field(default=None, min_length=1, max_length=4000)
    audio_expected: bool = True

    @field_validator('reason')
    @classmethod
    def meaningful_reason(cls, value):
        value = value.strip()
        if len(value) < 10:
            raise ValueError('Describe why a supervisor is importing this recording')
        return value

    @model_validator(mode='after')
    def source_required(self):
        if self.transcript is not None and not self.transcript.strip():
            raise ValueError('The copied transcript cannot be blank')
        if not self.audio_expected and not self.transcript:
            raise ValueError('A text-only recovered capture needs its saved transcript')
        return self


def assignment_evidence(state, actor_id, shift_id, item_id):
    def matches(assignment):
        return (assignment.get('user_id') == actor_id and assignment.get('shift_id') == shift_id
                and item_id in (assignment.get('work_item_ids') or scope.shift_items(state, shift_id)))

    for assignment in state.get('assignments', {}).values():
        if matches(assignment):
            return {'kind': 'current', 'id': assignment['id'], 'assignment': copy.deepcopy(assignment)}
    for change in state.get('assignment_history', {}).values():
        if change.get('shift_id') != shift_id:
            continue
        for assignment in change.get('previous', []):
            if matches(assignment):
                return {'kind': 'history', 'id': change['id'], 'assignment': copy.deepcopy(assignment)}
    raise HTTPException(422, 'The original author needs a recorded assignment to this work item in this shift')


@router.post('/recovered-captures', status_code=201)
def import_capture(org_id: str, body: RecoveredCapture, request: Request):
    user, org, repo, importer = ident.operational(request, org_id)
    supervisor(org)
    note_body = body.note
    sid = note_body.shift_id
    if not sid or sid == 'shift-B':
        raise HTTPException(422, 'Choose the actual dated shift for the recovered recording')
    index = repo.load_index()
    scope.choose_shift(index, org, user['id'], sid)
    scope.require_item(index, org, user['id'], note_body.batch_id, sid)
    # Incoming readers cannot import reports into the outgoing shift as its staff.
    if org['access'] != 'owner' and not any(a['user_id'] == user['id'] and a['shift_id'] == sid
                                          for a in index.get('assignments', {}).values()):
        raise HTTPException(403, 'An assigned supervisor must recover this shift’s recordings')
    with ident.database(write=False) as db:
        author = db.execute('SELECT id,name FROM users WHERE id=?', (body.original_actor_id,)).fetchone()
        membership = db.execute('SELECT role FROM memberships WHERE user_id=? AND org_id=?',
                                (body.original_actor_id, org_id)).fetchone()
    if not author:
        raise HTTPException(422, 'The original author must be an existing recorded account')
    # An unknown historical role never grants review authority to a recovered report.
    original_actor = Actor(id=author['id'], name=author['name'], role=membership['role'] if membership else 'operator')
    capture_id = 'note_' + hashlib.sha256(f'{original_actor.id}:{note_body.idempotency_key}'.encode()).hexdigest()[:24]
    fingerprint = hashlib.sha256(json.dumps(body.model_dump(mode='json'), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    history = repo.load_scoped([note_body.batch_id], shift_ids=[sid]).get('assignment_history', {})
    records = {'notes': [capture_id], 'assignment_history': list(history)}
    with repo.transaction(batch_ids=[note_body.batch_id], record_ids=records) as state:
        # Recheck assignments inside the same transaction as the source creation.
        scope.choose_shift(state, org, user['id'], sid)
        scope.require_item(state, org, user['id'], note_body.batch_id, sid)
        if org['access'] != 'owner' and not any(a['user_id'] == user['id'] and a['shift_id'] == sid
                                              for a in state.get('assignments', {}).values()):
            raise HTTPException(403, 'Your assignment to this shift has ended')
        shift = state['shift_occurrences'][sid]
        end = datetime.fromisoformat(shift['ends_at'])
        if datetime.now(timezone.utc) <= end + timedelta(hours=72):
            raise HTTPException(409, 'This shift is still within the normal 72-hour upload window')
        if not datetime.fromisoformat(shift['starts_at']) - timedelta(hours=1) <= note_body.recorded_at <= end + timedelta(hours=1):
            raise HTTPException(422, 'Recording time does not match the selected historical shift')
        evidence = assignment_evidence(state, original_actor.id, sid, note_body.batch_id)
        existing = state['notes'].get(capture_id)
        if existing:
            imported = existing.get('supervised_import') or {}
            if imported.get('request_fingerprint') != fingerprint or imported.get('actor', {}).get('id') != importer.id:
                raise Conflict('This capture already exists. Use its saved report instead of replacing it.')
            return response(org_id, copy.deepcopy(existing), duplicate=True)
        policy = state.get('data_policy', {})
        scope.check_data_capture_policy(state)
        if (policy.get('data_classification') == 'real' or policy.get('mode') == 'real') and not (
                policy.get('retention_days') and policy.get('recording_consent') and policy.get('factory_approval')):
            raise HTTPException(409, 'The owner must record factory consent and a retention policy before collecting real recordings')
        version = state.get('handovers', {}).get(sid, {}).get('version')
        stale = bool(note_body.clarification_ref and note_body.clarification_version is not None
                     and note_body.clarification_version != version)
        stored_context = None
        if stale:
            saved = note_body.clarification_context or {}
            if (saved.get('id') != note_body.clarification_ref or not note_body.clarification_ref.startswith(note_body.batch_id + ':')
                    or not isinstance(saved.get('text'), str) or not 1 <= len(saved['text']) <= 2000
                    or saved.get('version', note_body.clarification_version) != note_body.clarification_version):
                raise HTTPException(422, 'Retain the exact earlier clarification question and version with this recording')
            stored_context = {'id': note_body.clarification_ref, 'text': saved['text'],
                              'version': note_body.clarification_version, 'unverified_client_context': True}
            note_body = note_body.model_copy(update={'clarification_ref': None, 'clarification_version': None})
        # The common helper still validates correction targets and current questions.
        from .assisted import validate
        reporter=validate(state,org_id,original_actor.id,note_body.reported_by_id,sid,note_body.batch_id)
        note = service.create_note_in_state(state, note_body, original_actor)
        if reporter: note.update(reported_by=reporter,assisted_by=original_actor.model_dump())
        timestamp = now()
        note.update(late_submission=True, addendum=shift.get('status') == 'closed',
                    supervised_import={'actor': importer.model_dump(), 'reason': body.reason,
                        'imported_at': timestamp, 'original_actor_id': original_actor.id,
                        'assignment_evidence': evidence, 'request_fingerprint': fingerprint,
                        'source_role_basis': 'current_membership' if membership else 'historical_role_unknown',
                        'audio_expected': body.audio_expected,
                        'transcript_attestation': 'Supervisor-supplied copy; not independently attested by the original worker' if body.transcript else None},
                    processing_takeover={'actor': importer.model_dump(), 'reason': body.reason, 'created_at': timestamp})
        if body.transcript:
            note.update(revision=1, source='supervised_import',
                        status='awaiting_upload' if body.audio_expected else 'received',
                        processing_stage='uploading' if body.audio_expected else 'transcript_review')
            note['transcripts'].append({'revision': 1, 'text': body.transcript, 'created_at': timestamp,
                                       'actor_id': importer.id, 'original_actor_id': original_actor.id, 'kind': 'offline_import'})
        if stored_context:
            note.update(clarification_ref=stored_context['id'], clarification_context=stored_context, stale_clarification=True)
        audit(state, importer, 'note.offline_imported', note_id=note['id'], work_item_id=note['batch_id'],
              shift_id=sid, original_actor_id=original_actor.id, reason=body.reason,
              recorded_at=note['recorded_at'], assignment_evidence=evidence, addendum=note['addendum'])
        result = copy.deepcopy(note)
    return response(org_id, result)


def response(org_id, note, duplicate=False):
    return {'note': note, 'upload_url': f'/organizations/{org_id}/notes/{note["id"]}/audio',
            'upload_headers': {'Content-Type': 'audio/wav'}, 'duplicate': duplicate}
