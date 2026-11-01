import hashlib
import copy
import io
import time
import wave
import os
import sqlite3
import array
import math
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from . import providers
from .config import settings
from .engine import BATCHES, handover, active_claims
from .models import uid, now
from .repository import Conflict

def check_version(state, expected):
    if state['version'] != expected:
        raise Conflict('A new update arrived. Refresh before reviewing this version.')

def check_request_version(state, body):
    scope = getattr(body, 'scope_shift_id', None)
    if scope:
        from .pilot_scope import check_handover_version
        check_handover_version(state, scope, body.expected_version)
    else:
        check_version(state, body.expected_version)

def get_note(state, ident):
    if ident not in state['notes']:
        raise HTTPException(404, 'Note not found')
    return state['notes'][ident]

def owner_check(note, actor):
    if note['actor']['id'] != actor.id:
        raise HTTPException(403, 'Only the author can change this note')

def workspace_transaction(repo, batch_ids, record_ids=None):
    return repo.transaction(batch_ids=batch_ids, record_ids=record_ids) if hasattr(repo, 'load_scoped') else repo.transaction()

def record_transaction(repo, collection, ident):
    if not hasattr(repo, 'get_record'):
        return repo.transaction()
    record = repo.get_record(collection, ident)
    if not record:
        raise HTTPException(404, 'Note not found' if collection == 'notes' else 'Claim not found')
    return workspace_transaction(repo, [record['batch_id']], {collection:[ident]})

def note_transaction(repo, note_id):
    return record_transaction(repo, 'notes', note_id)

def provider_policy_status(repo):
    """Non-secret readiness indicators; declarations do not establish legal compliance."""
    policy = (repo.load_index() if hasattr(repo, 'load_index') else repo.load()).get('data_policy', {})
    default_mode='unconfigured' if os.getenv('SHIFTPROOF_REQUIRE_DATA_POLICY','false').lower()=='true' and not policy else 'fictional'
    declarations = (policy.get('mode', default_mode), policy.get('data_classification', default_mode))
    mode = 'real' if 'real' in declarations else next((value for value in declarations if value != 'fictional'), 'fictional')
    config = settings()
    org_approved = all(policy.get(key) is True for key in
                       ('provider_terms_approved', 'recording_consent', 'spending_cap_confirmed', 'factory_approval'))
    org_approved = org_approved and isinstance(policy.get('retention_days'), int) and policy['retention_days'] > 0
    business = config.business_provider_approved
    extraction_ready = (config.provider == 'gemini' and config.gemini_account_tier == 'business'
                        and config.gemini_business_terms_confirmed and bool(config.gemini_key) and bool(config.gemini_model)
                        and config.gemini_key != os.getenv('GEMINI_API_KEY', ''))
    speech_ready = (config.gnani_account_tier == 'business' and config.gnani_business_terms_confirmed
                    and bool(config.gnani_key()) and config.gnani_key() != os.getenv('GNANI_API_KEY', ''))
    return {'mode': mode, 'organization_declarations_complete': org_approved,
            'business_provider_configured': business,
            'extraction_allowed': mode == 'fictional' or bool(org_approved and business and extraction_ready),
            'speech_allowed': mode == 'fictional' or bool(org_approved and business and speech_ready),
            'gemini_account_tier': config.gemini_account_tier,
            'notice': 'Configuration records an explicit review; it does not establish provider terms or legal compliance.'}

def check_provider_policy(repo, operation='extraction'):
    if not getattr(repo, 'organization_id', None):
        return
    status = provider_policy_status(repo)
    if status['mode'] not in ('fictional', 'real'):
        raise providers.ProviderError('Choose fictional or real organization data mode before processing.', 'data_policy')
    allowed = status['extraction_allowed'] if operation == 'extraction' else status['speech_allowed']
    if not allowed:
        raise providers.ProviderError('Real workplace data is blocked from this provider configuration. Use manual review until business provider terms, consent and spending controls are explicitly approved.', 'real_data_provider_unapproved')

def reserve_usage(repo, key='model_calls', limit=None):
    if limit is None:
        limit = settings().max_calls
    shared_limit = limit
    if getattr(repo, 'organization_id', None):
        limit = min(limit, int(__import__('os').getenv('MAX_ORGANIZATION_CALLS_PER_DAY', '50')))
    with workspace_transaction(repo, []) as state:
        day = now()[:10]
        usage = state['usage'].setdefault(day, {'model_calls': 0, 'notes': 0, 'speech_calls': 0})
        if usage.get(key, 0) >= limit:
            raise providers.ProviderError(f'Daily {key.replace("_", " ")} limit reached. Try tomorrow or ask the workspace owner.', 'quota_exhausted')
        _reserve_shared_budget(key, shared_limit, bool(getattr(repo, 'organization_id', None)))
        usage[key] = usage.get(key, 0) + 1

def _reserve_shared_budget(key, shared_limit, private):
    """Separate demo/private pools beneath one atomic account-level ceiling."""
    bucket = 'private' if private else 'demo'
    pool_limit = min(shared_limit, int(os.getenv('MAX_PRIVATE_CALLS_PER_DAY' if private else 'MAX_DEMO_CALLS_PER_DAY', '160' if private else '40')))
    location = Path(os.getenv('SHIFTPROOF_SHARED_USAGE_DB') or str(Path(__file__).resolve().parents[2] / '.local' / 'shared-usage.sqlite3'))
    location.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(location, timeout=5) as db:
        db.execute('CREATE TABLE IF NOT EXISTS usage(key TEXT PRIMARY KEY,count INTEGER NOT NULL)')
        db.execute('BEGIN IMMEDIATE')
        day = now()[:10]
        limits = [(f'{day}:{key}', shared_limit), (f'{day}:{bucket}:{key}', pool_limit)]
        for counter, maximum in limits:
            row = db.execute('SELECT count FROM usage WHERE key=?', (counter,)).fetchone()
            if row and row[0] >= maximum:
                raise providers.ProviderError(f'The {bucket if ":" + bucket + ":" in counter else "shared"} provider budget is exhausted. Saved reports remain available.', 'quota_exhausted')
        for counter, _ in limits:
            db.execute('INSERT INTO usage VALUES (?,1) ON CONFLICT(key) DO UPDATE SET count=count+1', (counter,))

def create_note(repo, body, actor):
    if body.reported_by_id:raise HTTPException(422, "Assisted capture requires an organization workspace")
    ident = 'note_' + hashlib.sha256(f'{actor.id}:{body.idempotency_key}'.encode()).hexdigest()[:24]
    with workspace_transaction(repo, [body.batch_id], {'notes':[ident]}) as state:
        return create_note_in_state(state, body, actor)

def create_note_in_state(state, body, actor):
    """Create source metadata inside an already authorized workspace transaction."""
    ident = 'note_' + hashlib.sha256(f'{actor.id}:{body.idempotency_key}'.encode()).hexdigest()[:24]
    from .profiles import work_items
    if body.batch_id not in {b['id'] for b in work_items(state)}:
        raise HTTPException(404, 'Work item not found')
    if ident in state['notes']:
        existing = state['notes'][ident]
        if (existing['batch_id'] != body.batch_id or existing['recorded_at'] != body.recorded_at.isoformat()
            or existing.get('clarification_ref') != body.clarification_ref
            or existing.get('supersedes', []) != body.supersedes
            or existing.get('shift_id') != getattr(body, 'shift_id', None)
            or existing.get('task_id') != body.task_id
            or (existing.get('reported_by') or {}).get('id') != body.reported_by_id
            or (body.clarification_version is not None and (existing.get('clarification_context') or {}).get('version') != body.clarification_version)):
            raise Conflict('Idempotency key already used for a different note')
        return existing
    usage = state['usage'].setdefault(now()[:10], {'model_calls': 0, 'notes': 0, 'speech_calls': 0})
    if usage['notes'] >= settings().max_notes:
        raise HTTPException(429, 'Daily note limit reached')
    usage['notes'] += 1
    clarification_context = None
    if body.clarification_ref:
        context_version = state['version']
        if getattr(body, 'shift_id', None) and body.shift_id != 'shift-B':
            context_version = state.get('handovers', {}).get(body.shift_id, {}).get('version')
            if context_version is None:
                raise Conflict('This shift does not have a current handover')
        if body.clarification_version is not None and body.clarification_version != context_version:
            raise Conflict('The handover changed since this clarification was displayed. Refresh the question before submitting; your recording is retained.')
        valid = {b['clarification']['id']: b['clarification'] for b in handover(state)['batches'] if b['clarification']}
        if body.clarification_ref not in valid or not body.clarification_ref.startswith(body.batch_id + ':'):
            raise HTTPException(422, 'Clarification is no longer active for this batch')
        clarification_context = {**copy.deepcopy(valid[body.clarification_ref]), 'version': context_version}
    for cid in body.supersedes:
        target = state['claims'].get(cid)
        if not target or target['batch_id'] != body.batch_id:
            raise HTTPException(422, 'Correction target must belong to this batch')
    note = {'id': ident, 'batch_id': body.batch_id, 'actor': actor.model_dump(), 'recorded_at': body.recorded_at.isoformat(), 'received_at': now(), 'status': 'awaiting_upload', 'source': 'recording', 'audio_key': f'notes/{ident}.wav', 'has_audio': False, 'transcripts': [], 'claim_ids': [], 'clarification_ref': body.clarification_ref, 'supersedes': body.supersedes, 'error': None, 'revision': 0}
    note.update(clarification_context=clarification_context, processing_stage='uploading', error_category=None, timings={})
    if body.task_id:
        task = state['claims'].get(body.task_id)
        if (not task or task['batch_id'] != body.batch_id or task['property'] != 'task'
            or task['status'] != 'confirmed' or task.get('assigned_owner_id') != (body.reported_by_id or actor.id)):
            raise HTTPException(403, 'Select a reviewed task assigned to you in this work item')
        if task.get('source_review_pending') or task.get('task_status') == 'completed':
            raise Conflict('This task is completed or its source needs review. Refresh your assigned work.')
        note.update(task_id=body.task_id, task_context={'id':body.task_id, 'title':str(task['value']), 'owner_id':body.reported_by_id or actor.id})
    if getattr(body, 'shift_id', None):
        note['shift_id'] = body.shift_id
    state['notes'][ident] = note
    state['version'] += 1
    return note

def audio_quality(audio):
    with wave.open(io.BytesIO(audio)) as source:
        samples = array.array('h', source.readframes(source.getnframes()))
    if sys.byteorder != 'little': samples.byteswap()
    peak = max((abs(value) for value in samples), default=0) / 32768
    rms = math.sqrt(sum((value / 32768) ** 2 for value in samples) / max(1,len(samples)))
    return {'peak':peak, 'rms':rms, 'silent':peak == 0, 'quiet':0 < rms < 0.003}

def validate_audio(audio, *, require_signal=False):
    if not audio or len(audio) > 4_500_000:
        raise HTTPException(422, 'Upload a mono WAV recording of at most 45 seconds')
    try:
        with wave.open(io.BytesIO(audio)) as wav:
            duration = wav.getnframes() / wav.getframerate()
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or not 8000 <= wav.getframerate() <= 44100 or not 0.2 <= duration <= 45.1:
                raise HTTPException(422, 'Audio must be 16-bit mono WAV, 8–44.1 kHz, between 0.2 and 45 seconds')
            if len(wav.readframes(wav.getnframes())) != wav.getnframes() * 2:
                raise HTTPException(422, 'Incomplete WAV recording')
        if require_signal and audio_quality(audio)['silent']:
            raise providers.ProviderError('No sound was captured. Test or change the microphone and record again. The original recording is retained.', 'silent_audio')
        return duration
    except (wave.Error, EOFError, ZeroDivisionError) as exc:
        raise HTTPException(422, 'This file is not a valid PCM WAV recording') from exc

def read_audio(note, data_dir=None):
    if settings().cloud:
        import boto3
        obj = boto3.client('s3').get_object(Bucket=settings().bucket, Key=note['audio_key'])
        if obj['ContentLength'] > 4_500_000:
            raise providers.ProviderError('Recording exceeds the upload size limit')
        return obj['Body'].read()
    path = (data_dir or settings().data_dir) / note['audio_key']
    if not path.exists():
        raise providers.ProviderError('Recording is not uploaded yet')
    return path.read_bytes()

def submit_transcript(repo, note_id, text, actor, expected_version=None, scope_shift_id=None):
    with note_transaction(repo, note_id) as state:
        note = get_note(state, note_id)
        owner_check(note, actor)
        if expected_version is not None:
            if scope_shift_id:
                from .pilot_scope import check_handover_version
                check_handover_version(state, scope_shift_id, expected_version)
            else:
                check_version(state, expected_version)
        if note['status'] in ('processing', 'queued'):
            raise Conflict('Wait until processing finishes before editing this transcript')
        if note['transcripts'] and expected_version is None:
            raise Conflict('Use transcript revision with the current version to preserve history')
        if note['transcripts'] and note['transcripts'][-1]['text'] == text:
            return note
        note['revision'] += 1
        note['transcripts'].append({'revision': note['revision'], 'text': text, 'created_at': now(), 'actor_id': actor.id, 'kind': 'manual_correction' if note['has_audio'] or note['transcripts'] else 'typed_transcript'})
        if not note['has_audio']:
            note['source'] = 'typed_transcript'
        note['status'] = 'received'
        note['error'] = None
        note.update(processing_stage='transcript_review', error_category=None)
        # An earlier interpretation may still be valid, but must be explicitly
        # reconsidered against the revised source before it establishes readiness.
        for cid in note['claim_ids']:
            claim = state['claims'][cid]
            if claim['status'] not in ('rejected', 'superseded'):
                claim['source_review_pending'] = True
                claim['source_revision_pending'] = note['revision']
        for task in state['claims'].values():
            if task.get('completion_note_id') == note_id:
                task.update(completion_review_pending=True, task_status='open')
                key = uid('task-evidence-revised')
                state['resolutions'][key] = dict(id=key, claim_id=task['id'], note_id=note_id,
                    action='completion_evidence_revised', actor=actor.model_dump(), created_at=now(),
                    reason='Completion source changed; completion must be reported and checked again.', version=state['version']+1)
        state['version'] += 1
    return note

def mark_queued(repo, note_id, actor, allow_reviewer=False):
    with note_transaction(repo, note_id) as state:
        note = get_note(state, note_id)
        if not allow_reviewer or actor.role not in ('supervisor', 'quality'):
            owner_check(note, actor)
        if note['status'] in ('processed', 'discarded') or any(state['claims'][cid]['transcript_revision'] == note['revision'] for cid in note['claim_ids']):
            return False
        if note['status'] in ('processing', 'queued') and note.get('lease_until', '') > now():
            return False
        note['status'] = 'queued'
        note['processing_stage'] = 'queued'
        note['lease_until'] = (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat()
        note['error'] = None
        state['jobs'][note_id] = {'note_id': note_id, 'status': 'queued', 'queued_at': now(), 'requested_by': actor.model_dump()}
    return True

def process_note(repo, note_id, transcribe_only=False, *, durable_job_id=None, lease_token=None):
    started = time.monotonic()
    run_id = uid('run')
    with note_transaction(repo, note_id) as state:
        if durable_job_id:
            from .durable_jobs import check_lease
            job = check_lease(state, durable_job_id, lease_token)
        note = get_note(state, note_id)
        if durable_job_id and note['revision'] != job.get('working_revision', job['transcript_revision']):
            raise Conflict('The transcript changed after this job was queued')
        if note['status'] in ('processed', 'discarded') or any(state['claims'][cid]['transcript_revision'] == note['revision'] for cid in note['claim_ids']):
            return
        if note['status'] == 'processing' and note.get('lease_until', '') > now():
            raise Conflict('This note is already processing')
        note['status'] = 'processing'
        note['run_id'] = run_id
        note.update(processing_stage='transcription' if not note['transcripts'] else 'extraction', error_category=None, error=None)
        note['lease_until'] = (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat()
        revision = note['revision']
    try:
        from .assisted import validate_note
        validate_note(repo,note)
        def reserve(stage):
            if durable_job_id:
                from .durable_jobs import reserve_attempt
                reserve_attempt(repo, durable_job_id, lease_token, stage)
            validate_note(repo,note)
            reserve_usage(repo, 'speech_calls' if stage == 'transcription' else 'model_calls')

        def fence(state):
            if durable_job_id:
                from .durable_jobs import check_lease
                check_lease(state, durable_job_id, lease_token)

        timings = dict(note.get('timings', {}))
        if not note['transcripts']:
            check_provider_policy(repo, 'transcription')
            stt_started = time.monotonic()
            audio = read_audio(note, getattr(repo, "data_dir", None))
            duration = validate_audio(audio, require_signal=True)
            reserve('transcription')
            text, request_id = providers.transcribe(audio)
            with note_transaction(repo, note_id) as state:
                fence(state)
                current = get_note(state, note_id)
                if current.get('run_id') != run_id:
                    raise Conflict('Processing lease changed')
                current['has_audio'] = True
                current['duration_seconds'] = duration
                current['stt_request_id'] = request_id
                current['revision'] = 1
                current['transcripts'].append({'revision': 1, 'text': text, 'created_at': now(), 'kind': 'prisma_verbatim', 'actor_id': None})
                if durable_job_id:
                    state['jobs'][durable_job_id]['working_revision'] = 1
                timings['transcription_ms'] = round((time.monotonic()-stt_started)*1000)
                current['timings'] = timings
                note = dict(current)
                revision = 1
        if transcribe_only:
            with note_transaction(repo, note_id) as state:
                fence(state)
                current = get_note(state, note_id)
                if current.get('run_id') != run_id: raise Conflict('Processing lease changed')
                current.update(status='received', processing_stage='transcript_review', error=None)
                state['jobs'][note_id] = {**state['jobs'].get(note_id, {}), 'note_id': note_id, 'status': 'received', 'completed_at': now()}
            return
        transcript = note['transcripts'][-1]['text']
        prior = repo.load_scoped([note['batch_id']]) if hasattr(repo, 'load_scoped') else repo.load()
        context = {'recorded_at': note['recorded_at'], 'received_at': note['received_at'],
                   'clarification': note.get('clarification_context'),
                   'task': note.get('task_context'),
                   **({'workflow': __import__('shiftproof.profiles', fromlist=['PROFILES']).PROFILES[prior['profile']]} if 'profile' in prior else {}),
                   'correction_targets': [prior['claims'][cid] for cid in note['supersedes'] if cid in prior['claims']]}
        with note_transaction(repo, note_id) as state:
            fence(state)
            if state['notes'][note_id].get('run_id') != run_id:
                raise Conflict('Processing lease changed')
            state['notes'][note_id]['processing_stage'] = 'extraction'
        extract_started = time.monotonic()
        if note.get('stale_clarification') or (note.get('clarification_context') or {}).get('unverified_client_context'):
            raise providers.ExtractionUnavailable('This reply refers to an older question. Its recording and question are retained for a supervisor to interpret; automatic extraction is paused.', 'stale_clarification')
        check_provider_policy(repo, 'extraction')
        extraction, request_id = providers.extract(transcript, note['batch_id'], lambda: reserve('extraction'), context)
        if durable_job_id:
            from .durable_jobs import authorize_request, get_job
            authorize_request(repo, get_job(repo, durable_job_id))
        if extraction.task_completion and getattr(repo, 'organization_id', None):
            from .identity import database
            with database(write=False) as db:
                author = db.execute('SELECT role,access FROM memberships WHERE org_id=? AND user_id=?',
                                    (repo.organization_id, note['actor']['id'])).fetchone()
            if not author:
                raise providers.ExtractionUnavailable('The task reporter is no longer a member. A supervisor must review this source.', 'authorization')
            from .pilot_scope import assert_note_access
            latest = repo.load_index()
            assert_note_access(latest, {'role':author['role'], 'access':author['access']}, note['actor']['id'], note, 'process')
        timings['extraction_ms'] = round((time.monotonic()-extract_started)*1000)
        reconcile_started = time.monotonic()
        with note_transaction(repo, note_id) as state:
            fence(state)
            current = get_note(state, note_id)
            if current.get('run_id') != run_id or current['revision'] != revision:
                raise Conflict('Note changed during processing')
            # IDs are stable for a note revision; queue redelivery cannot duplicate claims.
            ids = []
            mismatch = bool(extraction.mentioned_batch and extraction.mentioned_batch != current['batch_id'])
            for index, candidate in enumerate(extraction.claims):
                cid = f'{note_id}:r{revision}:{index}'
                claim = candidate.model_dump(mode='json')
                targets = [target for target in current['supersedes'] if state['claims'][target]['property'] == candidate.property]
                claim.update({'id': cid, 'batch_id': current['batch_id'], 'note_id': note_id, 'transcript_revision': revision, 'actor': current['actor'], 'received_at': current['received_at'], 'status': 'draft', 'introduced_version': state['version']+1, 'supersedes': targets, 'batch_mismatch': mismatch, 'mentioned_batch': extraction.mentioned_batch, 'extraction_provider': settings().provider})
                state['claims'].setdefault(cid, claim)
                ids.append(cid)
            current['claim_ids'] = list(dict.fromkeys(current['claim_ids'] + ids))
            completion = extraction.task_completion
            task_error = None
            if current.get('task_id'):
                task = state['claims'].get(current['task_id'])
                current['task_completion'] = completion.model_dump() if completion else None
                if not task or task['status'] != 'confirmed' or task.get('source_review_pending') or task.get('assigned_owner_id') != (current.get('reported_by') or current['actor'])['id']:
                    task_error = 'Task assignment or evidence changed. A supervisor must review this saved report.'
                elif not completion or completion.outcome == 'unclear':
                    task_error = 'Task completion is unclear. Ask the worker or review the source.'
                elif not mismatch and not extraction.uncertainty and completion.outcome == 'done':
                    # This is a report from the assigned worker, never a supervisor verification.
                    if task.get('task_status') != 'completed':
                        task.update(task_status='reported_complete', completion_note_id=note_id,
                                    completion_note_revision=revision, completion_excerpt=completion.excerpt,
                                    completion_review_pending=False)
                        key = f'task-report:{note_id}:r{revision}'
                        state['resolutions'].setdefault(key, dict(id=key, claim_id=task['id'], note_id=note_id,
                            action='report_complete', actor=current['actor'], created_at=now(), version=state['version']+1,
                            reason='Worker reported completion in selected-task voice update', completion_note_id=note_id,
                            completion_note_revision=revision))
                elif not mismatch and not extraction.uncertainty and completion.outcome == 'not_done' and completion.modality == 'actual':
                    if task.get('task_status') in ('reported_complete', 'completed'):
                        task.update(task_status='open', completion_review_pending=True)
                        key = f'task-withdrawal:{note_id}:r{revision}'
                        state['resolutions'].setdefault(key, dict(id=key, claim_id=task['id'], note_id=note_id,
                            action='completion_withdrawn', actor=current['actor'], created_at=now(), version=state['version']+1,
                            reason='Worker reports the selected task is not complete; review the conflicting sources.'))
            supported = bool(ids or completion)
            current['error'] = extraction.uncertainty or task_error or ('Spoken batch differs from selected batch. Reject these claims and create a note for the correct batch.' if mismatch else ('No supported operational claims were found.' if not supported else None))
            current['status'] = 'manual_review' if current['error'] else 'processed'
            current['extraction_provider'] = settings().provider
            current['extraction_request_id'] = request_id
            current['extraction_model'] = providers.model_name()
            current['extraction_prompt_version'] = providers.prompt_version('tenant_manufacturing' if prior['profile']=='manufacturing' else prior['profile']) if 'profile' in prior else providers.prompt_version()
            current['extraction_origin'] = 'scripted_fixture' if settings().provider == 'scripted' else 'replay' if str(request_id).startswith('replay:') else 'live'
            current['processing_stage'] = 'review_required'
            current['error_category'] = 'uncertain' if current['error'] else None
            timings['reconciliation_ms'] = round((time.monotonic()-reconcile_started)*1000)
            current['timings'] = timings
            current['latency_ms'] = round((time.monotonic()-started)*1000)
            current['processed_at'] = now()
            state['jobs'][note_id] = {**state['jobs'].get(note_id, {}), 'note_id': note_id, 'status': current['status'], 'completed_at': now()}
            state['version'] += 1
    except Exception as exc:
        with note_transaction(repo, note_id) as state:
            current = get_note(state, note_id)
            still_owns_job = not durable_job_id or (state['jobs'].get(durable_job_id, {}).get('lease_token') == lease_token and state['jobs'].get(durable_job_id, {}).get('status') == 'running')
            if current.get('run_id') == run_id and still_owns_job and current['status'] != 'discarded':
                current['failed_stage'] = current.get('processing_stage', 'extraction')
                current['status'] = 'manual_review' if current['transcripts'] else 'failed'
                current['processing_stage'] = 'review_required' if current['transcripts'] else 'failed'
                current['error_category'] = 'authorization' if isinstance(exc, HTTPException) and exc.status_code in (401, 403, 404) else getattr(exc, 'category', 'processing_error')
                current['error'] = str(exc) if isinstance(exc, (providers.ProviderError, Conflict)) else 'Processing failed. The note is saved; retry or correct the transcript.'
                state['jobs'][note_id] = {**state['jobs'].get(note_id, {}), 'note_id': note_id, 'status': current['status'], 'completed_at': now()}
        if isinstance(exc, (Conflict, HTTPException)):
            raise

def review_transcript(repo, note_id, body, actor):
    """Save human interpretations as drafts; ordinary claim permissions still apply."""
    if actor.role not in ('supervisor', 'quality'):
        raise HTTPException(403, 'A supervisor or quality reviewer must interpret this transcript')
    with note_transaction(repo, note_id) as state:
        check_request_version(state, body)
        note = get_note(state, note_id)
        if note['status'] not in ('failed', 'manual_review') or any(state['claims'][cid]['transcript_revision'] == note['revision'] for cid in note['claim_ids']) or not note['transcripts']:
            raise Conflict('Manual extraction requires an unfinished transcript without claims for its current revision')
        if not body.claims and not body.no_operational_update:
            raise HTTPException(422, 'Choose the reported work, or explicitly confirm that this recording contains no work update')
        if body.claims and body.no_operational_update:
            raise HTTPException(422, 'A work report cannot also be marked as containing no work update')
        try:
            context = {'clarification': note.get('clarification_context')}
            if 'profile' in state:
                from .profiles import PROFILES
                context['workflow'] = PROFILES[state['profile']]
            candidates = [c.model_dump(mode='json') for c in body.claims]
            if context['clarification']:
                for c in candidates: c['context_refs'] = [context['clarification']['id']]
            extraction = providers.validate_extraction({'claims': candidates}, note['transcripts'][-1]['text'], context)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        state['version'] += 1
        for index, candidate in enumerate(extraction.claims):
            cid = f'{note_id}:r{note["revision"]}:manual:{index}'
            claim = candidate.model_dump(mode='json')
            claim.update(id=cid, batch_id=note['batch_id'], note_id=note_id,
                         transcript_revision=note['revision'], actor=note['actor'],
                         received_at=note['received_at'], status='draft',
                         introduced_version=state['version'], supersedes=[cid for cid in note['supersedes'] if state['claims'][cid]['property'] == candidate.property],
                         batch_mismatch=False, extraction_provider='human', interpreted_by=actor.model_dump())
            state['claims'][cid] = claim
            note['claim_ids'].append(cid)
        review = {'id': uid('transcript-review'), 'note_id': note_id, 'actor': actor.model_dump(),
                  'reason': body.reason, 'created_at': now(), 'version': state['version'],
                  'action': 'manual_extraction' if extraction.claims else 'no_operational_claims',
                  'previous_error': note.get('error')}
        state['resolutions'][review['id']] = review
        note.update(status='processed', error=None, processing_stage='review_required' if extraction.claims else 'complete', error_category=None, extraction_provider='human',
                    review_outcome=review, processed_at=now())
        state['jobs'][note_id] = {'note_id': note_id, 'status': 'processed', 'completed_at': now()}
        return note

def resolve(repo, claim_id, body, actor):
    if actor.role not in ('quality', 'supervisor'):
        raise HTTPException(403, 'A supervisor or quality reviewer must review claims')
    with record_transaction(repo, 'claims', claim_id) as state:
        check_request_version(state, body)
        claim = state['claims'].get(claim_id)
        if not claim:
            raise HTTPException(404, 'Claim not found')
        from .profiles import clearance, review_protected
        if body.action == 'reject' and review_protected(claim) and actor.role != 'quality':
            raise HTTPException(403, 'Only an authorized reviewer can remove an established hold')
        if body.action == 'confirm' and clearance(claim) and actor.role != 'quality':
            raise HTTPException(403, 'Only an authorized reviewer can confirm clearance')
        unchanged = ((body.action == 'confirm' and claim['status'] == 'confirmed')
                     or (body.action == 'reject' and claim['status'] == 'rejected'))
        same_targets = all(cid in claim.get('supersedes', []) and state['claims'].get(cid, {}).get('superseded_by') == claim_id
                           and state['claims'][cid]['status'] == 'superseded' for cid in body.supersedes)
        if unchanged and not claim.get('source_review_pending') and same_targets:
            prior = next((r for r in reversed(list(state['resolutions'].values()))
                          if r.get('claim_id') == claim_id and r['action'] == body.action), None)
            return prior or {'claim_id': claim_id, 'action': body.action, 'version': state['version'], 'unchanged': True}
        if claim['status'] in ('superseded', 'rejected'):
            raise Conflict('This claim is no longer active')
        if body.action == 'confirm':
            if claim.get('batch_mismatch'):
                raise HTTPException(422, 'Resolve the batch mismatch by submitting a note for the correct batch')
            from .profiles import clearance, review_protected
            if clearance(claim) and actor.role != 'quality':
                raise HTTPException(403, 'Only a quality reviewer can confirm quality clearance' if state.get('profile','manufacturing')=='manufacturing' else 'Only an authorized reviewer can confirm clearance')
            peers = [c for c in active_claims(state, claim['batch_id']) if claim['property'] != 'task' and c['property'] == claim['property'] and c['id'] != claim_id and c['modality'] == 'actual' and claim['modality'] == 'actual' and c['value'] != claim['value']]
            missing = [c['id'] for c in peers if c['id'] not in body.supersedes]
            if missing:
                raise HTTPException(409, {'message': 'Resolve the conflicting reports explicitly before confirming', 'conflicting_claim_ids': missing})
            for cid in body.supersedes:
                target = state['claims'].get(cid)
                if not target or cid == claim_id or target['batch_id'] != claim['batch_id'] or target['property'] != claim['property']:
                    raise HTTPException(422, 'Superseded claims must describe the same batch and property')
                if claim['modality'] != 'actual' and target['modality'] == 'actual':
                    raise HTTPException(422, 'Planned or conditional claims cannot supersede actual observations')
                if review_protected(target) and actor.role != 'quality':
                    raise HTTPException(403, 'Only a quality reviewer can supersede a quality hold' if state.get('profile','manufacturing')=='manufacturing' else 'Only an authorized reviewer can supersede an unresolved hold')
                if claim.get('reported_at') and target.get('reported_at') and datetime.fromisoformat(claim['reported_at']) < datetime.fromisoformat(target['reported_at']):
                    raise HTTPException(422, 'An older observation cannot supersede a newer report')
                if target['status'] in ('superseded', 'rejected'):
                    raise Conflict('A selected report is no longer active')
                target['status'] = 'superseded'
                target['superseded_by'] = claim_id
            claim['status'] = 'confirmed'
            claim['supersedes'] = list(dict.fromkeys(claim.get('supersedes', []) + body.supersedes))
        else:
            # Rejecting an established quality hold is equivalent to clearing it.
            from .profiles import review_protected
            if review_protected(claim) and actor.role != 'quality':
                raise HTTPException(403, 'Only a quality reviewer can remove an established quality hold' if state.get('profile','manufacturing')=='manufacturing' else 'Only an authorized reviewer can remove an established hold')
            claim['status'] = 'rejected'
        claim['source_review_pending'] = False
        claim['source_reviewed_revision'] = state['notes'][claim['note_id']]['revision']
        state['version'] += 1
        resolution = {'id': uid('resolution'), 'claim_id': claim_id, 'action': body.action, 'supersedes': body.supersedes, 'reason': body.reason, 'actor': actor.model_dump(), 'created_at': now(), 'version': state['version']}
        state['resolutions'][resolution['id']] = resolution
        note = state['notes'][claim['note_id']]
        if note['status'] == 'manual_review' and all(state['claims'][cid]['status'] in ('confirmed', 'rejected', 'superseded') for cid in note['claim_ids']):
            note['review_outcome'] = {'previous_error': note.get('error'), 'resolved_at': now(), 'actor': actor.model_dump()}
            note['status'] = 'processed'
            note['error'] = None
        # A completed human review must not keep advertising "review required".
        # Supersession may also finish the last outstanding claim of an older note.
        affected_notes = {claim['note_id']} | {state['claims'][cid]['note_id'] for cid in body.supersedes}
        for note_id in affected_notes:
            reviewed_note = state['notes'][note_id]
            related = [state['claims'][cid] for cid in reviewed_note['claim_ids']]
            if reviewed_note['status'] == 'processed' and related:
                complete = all(c['status'] in ('confirmed', 'rejected', 'superseded') and not c.get('source_review_pending') for c in related)
                reviewed_note['processing_stage'] = 'complete' if complete else 'review_required'
        return resolution

def update_task(repo, claim_id, body, actor):
    """Assigned workers report completion; reviewers separately verify it."""
    action = body.action
    if action != 'report_complete' and actor.role not in ('supervisor', 'quality'):
        raise HTTPException(403, 'A supervisor must assign or verify tasks')
    with record_transaction(repo, 'claims', claim_id) as state:
        check_request_version(state, body)
        task = state['claims'].get(claim_id)
        if not task or task['property'] != 'task' or task['status'] != 'confirmed':
            raise HTTPException(422, 'Select a human-reviewed task')
        if task.get('source_review_pending'):
            raise HTTPException(409, 'Review this task against the revised source first')
        previous = copy.deepcopy(task)
        if action == 'assign':
            owner = (body.owner or '').strip()
            owner_id = getattr(body, 'owner_id', None)
            if not owner and not owner_id:
                raise HTTPException(422, 'Select a responsible person or role')
            task.update(assigned_owner=owner or owner_id, assigned_owner_id=owner_id)
        elif action == 'report_complete':
            if task.get('assigned_owner_id') != actor.id:
                raise HTTPException(403, 'Only the assigned worker can report this task complete')
            if task.get('task_status') == 'completed':
                return {'status': 'saved', 'unchanged': True}
            task['task_status'] = 'reported_complete'
        elif action in ('complete', 'verify'):
            if not (task.get('owner') or task.get('assigned_owner') or task.get('assigned_owner_id')):
                raise HTTPException(422, 'Assign an owner first')
            if action == 'verify' and task.get('task_status', 'open') not in ('reported_complete', 'completed'):
                raise HTTPException(409, 'The assigned worker has not reported completion')
            task['task_status'] = 'completed'
        elif action == 'reopen':
            task['task_status'] = 'open'
        else:
            raise HTTPException(422, 'Unsupported task action')
        evidence_id = getattr(body, 'completion_note_id', None) or getattr(body, 'note_id', None)
        if action in ('complete', 'verify') and task.get('completion_review_pending') and not evidence_id:
            raise HTTPException(409, 'Completion evidence changed. Supply the reviewed current source or request a new completion report.')
        if evidence_id:
            evidence = get_note(state, evidence_id)
            if evidence['batch_id'] != task['batch_id'] or evidence['status'] == 'discarded':
                raise HTTPException(422, 'Completion evidence must belong to this work item')
            if action == 'report_complete' and evidence['actor']['id'] != actor.id:
                raise HTTPException(403, 'Use your own report as completion evidence')
            task['completion_note_id'] = evidence_id
            task['completion_note_revision'] = evidence['revision']
            task['completion_review_pending'] = False
        if task == previous:
            return {'status': 'saved', 'unchanged': True}
        state['version'] += 1
        key = uid('task-action')
        state['resolutions'][key] = dict(id=key, claim_id=claim_id, action=action,
            reason=body.reason, actor=actor.model_dump(), created_at=now(), version=state['version'],
            owner_id=task.get('assigned_owner_id'), completion_note_id=evidence_id)
        return {'status': 'saved', 'task_status': task.get('task_status', 'open')}


def acknowledge(repo, body, actor):
    with repo.transaction() as state:
        check_request_version(state, body)
        if any(n['status'] in ('queued', 'processing', 'awaiting_upload', 'received', 'failed', 'manual_review') for n in state['notes'].values()):
            raise HTTPException(409, 'Process, review, or discard unfinished notes before acknowledging the handover')
        ident = f'{actor.id}:{state["version"]}'
        snapshot_id = f'handover:{state["version"]}'
        if snapshot_id not in state['snapshots']:
            snapshot = copy.deepcopy(handover(state))
            snapshot.pop('acknowledgements', None)
            snapshot.update(id=snapshot_id, created_at=now())
            state['snapshots'][snapshot_id] = snapshot
        ack = {'id': ident, 'version': state['version'], 'snapshot_id': snapshot_id, 'actor': actor.model_dump(), 'readback': body.readback, 'created_at': now()}
        state['acknowledgements'].setdefault(ident, ack)
        return state['acknowledgements'][ident]

def seed(repo):
    from .fixtures import ACTORS as DEMO_ACTORS
    rows = [
        ('B-17', 'operator', 'Packing complete hai, quality check pending hai.', [('packing','complete','Packing complete hai'), ('quality','pending','quality check pending hai')], 'confirmed'),
        ('B-17', 'supervisor', 'Dispatch ke liye ready hai.', [('dispatch','ready','Dispatch ke liye ready hai')], 'draft'),
        ('B-18', 'quality', 'Packing complete. Quality inspection cleared. 240 cartons verified.', [('packing','complete','Packing complete'), ('quality','cleared','Quality inspection cleared'), ('quantity',240,'240 cartons verified')], 'confirmed'),
        ('B-19', 'operator', 'Packing pending. 360 cartons completed. Recheck carton labels.', [('packing','pending','Packing pending'), ('quantity',360,'360 cartons completed'), ('task','Recheck carton labels','Recheck carton labels')], 'confirmed'),
        ('B-21', 'operator', 'Packing complete hai.', [('packing','complete','Packing complete hai')], 'draft'),
        ('B-22', 'quality', 'Quality inspection pending.', [('quality','pending','Quality inspection pending')], 'confirmed'),
    ]
    with repo.transaction() as state:
        if state['notes']:
            return False
        for index, (batch, role, text, values, status) in enumerate(rows):
            ident = f'fixture-{index+1}'
            actor = DEMO_ACTORS[role].model_dump()
            stamp = (datetime.now(timezone.utc)-timedelta(minutes=46-index*6)).isoformat()
            note = {'id': ident, 'batch_id': batch, 'actor': actor, 'recorded_at': stamp, 'received_at': stamp, 'status': 'processed', 'source': 'scripted_fixture', 'audio_key': None, 'has_audio': False, 'transcripts': [{'revision': 1, 'text': text, 'created_at': stamp, 'kind': 'scripted_fixture', 'actor_id': actor['id']}], 'claim_ids': [], 'revision': 1, 'error': None, 'supersedes': [], 'clarification_ref': None}
            for j, (prop, value, excerpt) in enumerate(values):
                cid = f'{ident}:r1:{j}'
                state['claims'][cid] = {'id': cid, 'batch_id': batch, 'note_id': ident, 'transcript_revision': 1, 'actor': actor, 'received_at': stamp, 'reported_at': None, 'property': prop, 'value': value, 'excerpt': excerpt, 'modality': 'actual', 'condition': None, 'negated': False, 'owner': None, 'status': status, 'supersedes': [], 'batch_mismatch': False, 'introduced_version': index+1}
                note['claim_ids'].append(cid)
                if status == 'confirmed':
                    rid = f'seed-review-{cid}'
                    state['resolutions'][rid] = {'id': rid, 'claim_id': cid, 'action': 'confirm', 'supersedes': [], 'reason': 'Fictional seeded review for the labeled demonstration', 'actor': DEMO_ACTORS['quality' if prop == 'quality' else 'supervisor'].model_dump(), 'created_at': stamp, 'version': index+1}
            state['notes'][ident] = note
        state['version'] = 6
        state['snapshots']['previous-shift'] = {'id': 'previous-shift', 'version': 1, 'label': 'Previous handover · fictional baseline', 'created_at': now()}
        return True
