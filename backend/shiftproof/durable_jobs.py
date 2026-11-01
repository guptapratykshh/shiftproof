"""Persistent local processing jobs; the HTTP process never owns their lifetime.

Only the worker executes provider calls. A lease fences late results, and network
attempts are persisted before each request so a restart cannot reset the budget.
"""
import copy
from datetime import datetime, timezone, timedelta
from threading import Event, Thread
from fastapi import HTTPException
from .models import Actor, now, uid
from .repository import Conflict
from . import service

LEASE_SECONDS = 180
TERMINAL = {'succeeded', 'failed', 'cancelled', 'authorization_required'}


def _until():
    return (datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)).isoformat()


def get_job(repo, ident):
    return repo.get_record('jobs', ident) if hasattr(repo, 'get_record') else repo.load()['jobs'].get(ident)


def job_transaction(repo, ident):
    job = get_job(repo, ident)
    if not job:
        raise Conflict('Processing job no longer exists')
    return service.note_transaction(repo, job['note_id'])


def authorize_request(repo, job):
    """Recheck membership and current scope, never trust a queued role snapshot."""
    actor = Actor.model_validate(job['requested_by'])
    if not getattr(repo, 'organization_id', None):
        return actor  # Legacy fictional demo/test repositories.
    from .identity import database
    with database(write=False) as db:
        row = db.execute('SELECT role,access FROM memberships WHERE org_id=? AND user_id=?',
                         (repo.organization_id, actor.id)).fetchone()
    if not row:
        raise HTTPException(403, 'Requester is no longer a member. An assigned supervisor must take over this saved job.')
    actor = actor.model_copy(update={'role': row['role']})
    state = repo.load_index() if hasattr(repo, 'load_index') else repo.load()
    note = repo.get_record('notes', job['note_id']) if hasattr(repo, 'get_record') else service.get_note(state, job['note_id'])
    if not note:
        raise HTTPException(404, 'Saved note no longer exists')
    from .assisted import validate_note
    validate_note(repo,note)
    if actor.role == 'operator':
        service.owner_check(note, actor)
    if state.get('shift_occurrences'):
        from .pilot_scope import assert_note_access
        assert_note_access(state, {'id': repo.organization_id, 'access': row['access'], 'role': row['role']}, actor.id, note, action='process')
    return actor


def enqueue(repo, note_id, actor, stage='extract', *, retry_failed=True):
    if stage not in ('transcribe', 'extract'):
        raise HTTPException(422, 'Choose transcription or extraction')
    actor = authorize_request(repo, {'requested_by': actor.model_dump(), 'note_id': note_id})
    with service.note_transaction(repo, note_id) as state:
        note = service.get_note(state, note_id)
        if actor.role not in ('supervisor', 'quality'):
            service.owner_check(note, actor)
        if note['status'] == 'discarded':
            raise HTTPException(409, 'This capture was cancelled')
        active = next((job for job in state['jobs'].values() if job.get('kind') == 'durable'
                       and job.get('note_id') == note_id and job['status'] in ('queued', 'running')), None)
        if active:
            return copy.deepcopy(active)
        revision = note['revision']
        ident = f'job:{note_id}:r{revision}:{stage}'
        previous = state['jobs'].get(ident)
        if previous and (previous['status'] not in TERMINAL or previous['status'] == 'succeeded' or not retry_failed):
            return copy.deepcopy(previous)
        complete = bool(note['transcripts']) if stage == 'transcribe' else any(
            state['claims'][cid]['transcript_revision'] == revision for cid in note['claim_ids']) or note['status'] == 'processed'
        history = list((previous or {}).get('attempt_history', []))
        if previous:
            history.append({key: copy.deepcopy(value) for key, value in previous.items() if key != 'attempt_history'})
        job = dict(id=ident, kind='durable', organization_id=getattr(repo, 'organization_id', None),
                   note_id=note_id, transcript_revision=revision, working_revision=revision, stage=stage,
                   status='succeeded' if complete else 'queued', requested_by=actor.model_dump(),
                   queued_at=now(), attempts={}, attempt_history=history, attempt_number=len(history) + 1,
                   lease_until=None, lease_token=None, error=None, error_category=None)
        state['jobs'][ident] = job
        if not complete:
            note.update(status='queued', processing_stage='queued', error=None, error_category=None,
                        durable_job_id=ident, lease_until='')
        return copy.deepcopy(job)


def retry(repo, job_id, actor):
    job = get_job(repo, job_id)
    if not job or job.get('kind') != 'durable':
        raise HTTPException(404, 'Processing job not found')
    actor = authorize_request(repo, {'requested_by': actor.model_dump(), 'note_id': job['note_id']})
    if job['status'] == 'running' and (job.get('lease_until') or '') > now():
        return job
    return enqueue(repo, job['note_id'], actor, job['stage'])


def check_lease(state, job_id, token):
    job = state['jobs'].get(job_id)
    if not job or job.get('lease_token') != token or job['status'] != 'running':
        raise Conflict('Processing lease changed; this result was not applied')
    note = service.get_note(state, job['note_id'])
    if note['status'] == 'discarded':
        raise Conflict('This capture was cancelled while processing')
    return job


def reserve_attempt(repo, job_id, token, stage):
    current = get_job(repo, job_id)
    if not current:
        raise Conflict('Processing job no longer exists')
    authorize_request(repo, current)
    with job_transaction(repo, job_id) as state:
        job = check_lease(state, job_id, token)
        attempts = job.setdefault('attempts', {})
        if attempts.get(stage, 0) >= 2:
            from .providers import ProviderError
            raise ProviderError('The saved processing attempt used its two network requests. Review the source or explicitly retry.', 'attempts_exhausted')
        attempts[stage] = attempts.get(stage, 0) + 1
        job['last_request_at'] = now()


def _heartbeat(repo, ident, token, stopped):
    while not stopped.wait(20):
        try:
            with job_transaction(repo, ident) as state:
                job = check_lease(state, ident, token)
                job['lease_until'] = _until()
                state['notes'][job['note_id']]['lease_until'] = job['lease_until']
        except Exception:
            # Fencing still prevents a late worker from overwriting a new lease.
            return


def run_once(repo, *, membership_check=None):
    """Claim one queued/expired job. Return False when there is no work.

    membership_check is a test hook; the production default always checks the
    identity database and assigned scope, including before provider requests.
    """
    token = uid('lease')
    if hasattr(repo, 'next_due_job'):
        candidate = repo.next_due_job(now())
        if not candidate:
            return False
        transaction = service.note_transaction(repo, candidate['note_id'])
    else:
        transaction = repo.transaction()
    with transaction as state:
        candidates = [j for j in state['jobs'].values() if j.get('kind') == 'durable'
                      and (j['status'] == 'queued' or (j['status'] == 'running' and (j.get('lease_until') or '') <= now()))]
        if not candidates:
            return False
        job = min(candidates, key=lambda j: (j['queued_at'], j['id']))
        job.update(status='running', lease_token=token, lease_until=_until(), started_at=now())
        ident = job['id']
        note = service.get_note(state, job['note_id'])
        if note['status'] == 'discarded':
            job.update(status='cancelled', completed_at=now(), lease_until=None)
            return True
        already_done = (claimed_stage := job['stage']) == 'transcribe' and bool(note['transcripts'])
        already_done = already_done or (claimed_stage == 'extract' and (note['status'] == 'processed' or any(
            state['claims'][cid]['transcript_revision'] == note['revision'] for cid in note['claim_ids'])))
        if already_done:
            job.update(status='succeeded', completed_at=now(), lease_until=None)
            if note['status'] in ('queued', 'processing'):
                note.update(status='received' if claimed_stage == 'transcribe' else 'processed',
                            processing_stage='transcript_review' if claimed_stage == 'transcribe' else 'review_required')
            return True
        # The previous process may have died while its note lease was active.
        # A claimed job lease is the authority for this resumable attempt.
        note.update(status='queued', lease_until='')
        claimed = copy.deepcopy(job)
    stopped = Event()
    heartbeat = Thread(target=_heartbeat, args=(repo, ident, token, stopped), daemon=True)
    try:
        (membership_check or authorize_request)(repo, claimed)
        heartbeat.start()
        service.process_note(repo, claimed['note_id'], claimed['stage'] == 'transcribe',
                             durable_job_id=ident, lease_token=token)
        with job_transaction(repo, ident) as state:
            job = check_lease(state, ident, token)
            note = service.get_note(state, job['note_id'])
            success = note['status'] == 'processed' or (job['stage'] == 'transcribe' and bool(note['transcripts']))
            job.update(status='succeeded' if success else 'failed', completed_at=now(), lease_until=None,
                       error=note.get('error'), error_category=note.get('error_category'))
    except HTTPException as exc:
        with job_transaction(repo, ident) as state:
            job = state['jobs'].get(ident)
            if job and job.get('lease_token') == token:
                job.update(status='authorization_required', error=str(exc.detail), error_category='authorization', completed_at=now(), lease_until=None)
                note = service.get_note(state, job['note_id'])
                note.update(status='manual_review' if note['transcripts'] else 'failed', processing_stage='review_required' if note['transcripts'] else 'failed', error=str(exc.detail), error_category='authorization')
    except Exception as exc:
        with job_transaction(repo, ident) as state:
            job = state['jobs'].get(ident)
            if job and job.get('lease_token') == token and job['status'] == 'running':
                job.update(status='failed', error='Saved job was interrupted; retry or review the source.', error_category='processing_error', completed_at=now(), lease_until=None)
                note = service.get_note(state, job['note_id'])
                if note['status'] != 'discarded':
                    note.update(status='manual_review' if note['transcripts'] else 'failed', processing_stage='review_required' if note['transcripts'] else 'failed', error=job['error'], error_category=job['error_category'])
    finally:
        stopped.set()
        if heartbeat.is_alive():
            heartbeat.join(timeout=1)
    return True
