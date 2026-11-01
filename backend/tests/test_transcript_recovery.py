from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from botocore.exceptions import ClientError
from shiftproof.fixtures import ACTORS as DEMO_ACTORS
from shiftproof.config import settings
from shiftproof.models import NoteCreate, TranscriptReview, ResolveRequest
from shiftproof.providers import extract, ExtractionUnavailable
from shiftproof.service import create_note, submit_transcript, process_note, review_transcript, resolve
from shiftproof.repository import Conflict
from shiftproof.engine import handover

QUALITY = 'अ वो क्वालिटी चेक पूरा ही होने वाला है बस आधा घंटा और लगेगा'
HELLO = 'हेलो हेलो एम आई एबल टू लिसन टू यू हेलो हेलो हेलो'

def unfinished(repo, text):
    actor = DEMO_ACTORS['operator']
    note = create_note(repo, NoteCreate(batch_id='B-17', recorded_at=datetime.now(timezone.utc), idempotency_key='recovery-note-001'), actor)
    submit_transcript(repo, note['id'], text, actor)
    process_note(repo, note['id'])
    return note['id']

def body(repo, claims=None):
    return TranscriptReview(expected_version=repo.load()['version'], claims=claims or [], no_operational_update=not claims, reason='Reviewed the original transcript and selected batch')

def test_saved_hindi_note_can_be_recovered_without_fake_automatic_claims(repo):
    nid = unfinished(repo, QUALITY)
    assert repo.load()['notes'][nid]['status'] == 'manual_review'
    assert not repo.load()['claims']
    request = body(repo, [{'property': 'quality', 'value': 'pending', 'excerpt': QUALITY}])
    review_transcript(repo, nid, request, DEMO_ACTORS['supervisor'])
    state = repo.load()
    note = state['notes'][nid]
    claim = state['claims'][note['claim_ids'][0]]
    assert note['transcripts'][0]['text'] == QUALITY
    assert claim['status'] == 'draft'
    assert claim['extraction_provider'] == 'human'
    assert handover(state)['batches'][0]['quality'] == 'pending'
    with pytest.raises(Conflict):
        review_transcript(repo, nid, request, DEMO_ACTORS['quality'])
    assert len(repo.load()['claims']) == 1

def test_microphone_test_can_be_closed_with_retained_evidence(repo):
    nid = unfinished(repo, HELLO)
    review_transcript(repo, nid, body(repo), DEMO_ACTORS['supervisor'])
    note = repo.load()['notes'][nid]
    assert note['status'] == 'processed'
    assert not note['claim_ids']
    assert note['transcripts'][0]['text'] == HELLO
    assert note['review_outcome']['action'] == 'no_operational_claims'

def test_manual_review_requires_reviewer_and_exact_evidence(repo):
    nid = unfinished(repo, QUALITY)
    with pytest.raises(HTTPException) as error:
        review_transcript(repo, nid, body(repo), DEMO_ACTORS['operator'])
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        review_transcript(repo, nid, body(repo, [{'property': 'quality', 'value': 'cleared', 'excerpt': 'invented words'}]), DEMO_ACTORS['supervisor'])
    assert error.value.status_code == 422
    assert not repo.load()['claims']

def test_manual_quality_claim_cannot_bypass_clearance_role(repo):
    nid = unfinished(repo, 'Quality cleared according to this report.')
    review_transcript(repo, nid, body(repo, [{'property': 'quality', 'value': 'cleared', 'excerpt': 'Quality cleared'}]), DEMO_ACTORS['supervisor'])
    cid = repo.load()['notes'][nid]['claim_ids'][0]
    with pytest.raises(HTTPException) as error:
        resolve(repo, cid, ResolveRequest(expected_version=repo.load()['version'], action='confirm', reason='Checked report'), DEMO_ACTORS['supervisor'])
    assert error.value.status_code == 403

def test_aws_authorization_error_is_actionable_and_keeps_transcript(repo, monkeypatch):
    monkeypatch.setenv('EXTRACTION_PROVIDER', 'bedrock'); settings.cache_clear()
    class Denied:
        def converse(self, **kwargs):
            raise ClientError({'Error': {'Code': 'ValidationException', 'Message': 'Operation not allowed'}}, 'Converse')
    monkeypatch.setattr('boto3.client', lambda *a, **k: Denied())
    nid = unfinished(repo, QUALITY)
    note = repo.load()['notes'][nid]
    assert note['status'] == 'manual_review'
    assert 'AWS denied Bedrock model access' in note['error']
    assert note['transcripts'][0]['text'] == QUALITY
    assert not note['claim_ids']

def test_retry_reuses_saved_transcript_without_calling_gnani(repo, monkeypatch):
    nid = unfinished(repo, QUALITY)
    def should_not_transcribe(*args):
        raise AssertionError('Retry must reuse the saved transcript')
    monkeypatch.setattr('shiftproof.providers.transcribe', should_not_transcribe)
    process_note(repo, nid)
    assert len(repo.load()['notes'][nid]['transcripts']) == 1
    assert repo.load()['notes'][nid]['status'] == 'manual_review'
