from audio_fixture import pcm_frames
from datetime import datetime, timezone
import copy
import io
import json
import wave
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from shiftproof.api import app
from shiftproof.fixtures import ACTORS as DEMO_ACTORS
from shiftproof.config import settings
from shiftproof.engine import handover
from shiftproof.models import NoteCreate, ResolveRequest, AckRequest, Extraction
from shiftproof.providers import extract, ExtractionUnavailable, validate_extraction
from shiftproof.service import create_note, submit_transcript, process_note, resolve, acknowledge, seed
from test_handover import add, confirm, batch


def test_planned_or_mismatched_newer_claim_never_hides_hold(repo):
    hold = add(repo, 'packing-hold')[1]
    confirm(repo, hold)
    with repo.transaction() as s:
        s['claims'][hold['id']]['reported_at'] = '2026-10-07T09:00:00+00:00'
        future = copy.deepcopy(s['claims'][hold['id']])
        future.update(id='future', value='cleared', modality='planned', reported_at='2026-10-07T12:00:00+00:00')
        s['claims']['future'] = future
    assert batch(repo)['quality'] == 'pending'
    with repo.transaction() as s:
        s['claims']['future'].update(modality='actual', batch_mismatch=True)
    assert batch(repo)['quality'] == 'pending'


def test_planned_clearance_cannot_supersede_actual_hold(repo):
    hold = add(repo, 'packing-hold')[1]; confirm(repo, hold)
    release = add(repo, 'quality-clear', 'quality')[0]
    with repo.transaction() as s: s['claims'][release['id']]['modality'] = 'planned'
    with pytest.raises(HTTPException) as exc:
        confirm(repo, release, 'quality', [hold['id']])
    assert exc.value.status_code == 422
    assert batch(repo)['quality'] == 'pending'


def test_nonquality_cannot_supersede_hold_even_with_another_pending_claim(repo):
    hold = add(repo, 'packing-hold')[1]; confirm(repo, hold)
    other = add(repo, 'clarify')[1]
    with pytest.raises(HTTPException) as exc: confirm(repo, other, 'supervisor', [hold['id']])
    assert exc.value.status_code == 403


def test_dispatch_pending_and_tasks_block_ready(repo, monkeypatch):
    for c in add(repo, 'packing-hold'): confirm(repo, c)
    hold = next(c for c in repo.load()['claims'].values() if c['property'] == 'quality')
    c = add(repo, 'quality-clear', 'quality')[0]; confirm(repo, c, 'quality', [hold['id']])
    assert batch(repo)['status'] == 'verified'
    c = add(repo, 'dispatch')[0]
    with repo.transaction() as s: s['claims'][c['id']]['value'] = 'pending'
    confirm(repo, repo.load()['claims'][c['id']])
    assert batch(repo)['status'] == 'review'
    assert any(r['code'] == 'pending_work' and c['id'] in r['claim_ids'] for r in batch(repo)['readiness_reasons'])


def test_ack_snapshot_is_immutable_and_duplicate_processing_is_nonmaterial(repo):
    seed(repo)
    ack = acknowledge(repo, AckRequest(expected_version=repo.load()['version'], readback='Quality holds remain'), DEMO_ACTORS['operator'])
    frozen = copy.deepcopy(repo.load()['snapshots'][ack['snapshot_id']])
    process_note(repo, 'fixture-1')
    assert handover(repo.load())['acknowledgements'][0]['current']
    add(repo, 'quantity-15')
    assert repo.load()['snapshots'][ack['snapshot_id']] == frozen
    assert not handover(repo.load())['acknowledgements'][0]['current']


def test_context_is_frozen_and_passed_to_extraction(repo, monkeypatch):
    seed(repo)
    note = create_note(repo, NoteCreate(batch_id='B-17', recorded_at=datetime.now(timezone.utc), clarification_ref='B-17:quality', idempotency_key='context-frozen'), DEMO_ACTORS['quality'])
    question = copy.deepcopy(note['clarification_context'])
    received = []
    def fake(text, batch_id, reserve, context):
        received.append(context)
        return Extraction(claims=[], uncertainty='Ambiguous answer'), 'test'
    monkeypatch.setattr('shiftproof.providers.extract', fake)
    submit_transcript(repo, note['id'], 'haan', DEMO_ACTORS['quality']); process_note(repo, note['id'])
    assert received[0]['clarification'] == question
    assert repo.load()['notes'][note['id']]['status'] == 'manual_review'


def test_short_reply_requires_real_question_reference():
    raw = {'claims': [{'property': 'quality', 'value': 'cleared', 'excerpt': 'haan clear'}]}
    context = {'clarification': {'id': 'B-17:quality', 'text': 'Is quality clear?'}}
    with pytest.raises(ValueError, match='stored question'): validate_extraction(raw, 'haan clear', context)
    raw['claims'][0]['context_refs'] = ['invented']
    with pytest.raises(ValueError, match='not supplied'): validate_extraction(raw, 'haan clear', context)
    raw['claims'][0]['context_refs'] = ['B-17:quality']
    assert validate_extraction(raw, 'haan clear', context).claims[0].value == 'cleared'


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setenv('EXTRACTION_PROVIDER', 'gemini')
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key-not-real')
    monkeypatch.setenv('GEMINI_FREE_TIER_CONFIRMED', 'true'); settings.cache_clear()


def response(status=200, output=None):
    return httpx.Response(status, request=httpx.Request('POST', 'https://generativelanguage.googleapis.com/v1beta/interactions'), json={'status': 'completed', 'id': 'gemini-test', 'output_text': json.dumps(output)} if output is not None else {})


def test_gemini_structured_request_and_exact_hindi_excerpt(gemini, monkeypatch):
    text = 'क्वालिटी चेक पूरा होने वाला है बस आधा घंटा और लगेगा'
    sent = []
    def post(*args, **kwargs):
        sent.append(kwargs)
        return response(output={'claims': [{'property': 'quality', 'value': 'pending', 'excerpt': text}]})
    monkeypatch.setattr('httpx.post', post)
    result, ident = extract(text, 'B-17')
    assert result.claims[0].value == 'pending'
    assert ident == 'gemini-test'
    assert sent[0]['json']['store'] is False
    assert sent[0]['json']['response_format']['mime_type'] == 'application/json'
    assert sent[0]['json']['model'] == 'gemini-3.8-flash'


def test_gemini_repairs_fabricated_excerpt_only_once(gemini, monkeypatch):
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs)
        return response(output={'claims': [{'property': 'quality', 'value': 'cleared', 'excerpt': 'invented'}]})
    monkeypatch.setattr('httpx.post', post)
    with pytest.raises(ExtractionUnavailable, match='validation within'): extract('quality pending', 'B-17')
    assert len(calls) == 2
    assert 'retry_validation_error' in calls[1]['json']['input']


@pytest.mark.parametrize('code,category', [(429, 'quota_exhausted'), (403, 'authorization'), (404, 'configuration'), (503, 'provider_unavailable')])
def test_gemini_errors_do_not_silently_fallback(gemini, monkeypatch, code, category):
    sent = []
    def post(*args, **kwargs): sent.append(1); return response(code)
    monkeypatch.setattr('httpx.post', post)
    with pytest.raises(ExtractionUnavailable) as exc: extract('packing pending', 'B-17')
    assert exc.value.category == category
    assert len(sent) == (2 if code == 503 else 1)


def test_gemini_requires_free_tier_confirmation_before_network(gemini, monkeypatch):
    settings().gemini_free_tier_confirmed = False
    monkeypatch.setattr('httpx.post', lambda *a, **k: pytest.fail('No request permitted'))
    with pytest.raises(ExtractionUnavailable) as exc: extract('packing pending', 'B-17')
    assert exc.value.category == 'free_tier_unconfirmed'


def test_transcribe_then_inspect_then_extract_same_note(organization_api, monkeypatch):
    client, org, repo = organization_api
    base = f'/organizations/{org}'
    nid = client.post(base+'/notes', json={'batch_id': 'B-17', 'recorded_at': datetime.now(timezone.utc).isoformat(), 'idempotency_key': 'staged-recording'}).json()['note']['id']
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm_frames(16000))
    client.put(base+f'/notes/{nid}/audio', content=out.getvalue())
    monkeypatch.setattr('shiftproof.providers.transcribe', lambda audio: ('Packing complete nahi hai.', 'prisma-test'))
    r = client.post(base+f'/notes/{nid}/process', json={'transcribe_only': True})
    assert r.status_code == 202
    note = client.get(base+f'/notes/{nid}').json()
    assert note['processing_stage'] == 'transcript_review' and not note['claims']
    monkeypatch.setattr('shiftproof.providers.transcribe', lambda audio: pytest.fail('Must reuse transcript'))
    client.post(base+f'/notes/{nid}/process', json={})
    note = client.get(base+f'/notes/{nid}').json()
    assert note['claims'][0]['value'] == 'pending'
    assert len(note['transcripts']) == 1
    assert set(note['timings']) == {'transcription_ms', 'extraction_ms', 'reconciliation_ms'}
