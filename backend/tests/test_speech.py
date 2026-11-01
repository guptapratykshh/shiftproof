from fastapi.testclient import TestClient
from shiftproof.api import app
from shiftproof.service import seed
import io
import wave
import pytest
from shiftproof.providers import normalize_speech_wav, ProviderError

def test_streamed_timbre_wave_length_is_repaired_without_changing_pcm():
    pcm = b'\x01\x00' * 24000
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
        wav.writeframes(pcm)
    streaming = bytearray(buffer.getvalue())
    streaming[4:8] = b'\xff' * 4
    streaming[40:44] = b'\xff' * 4
    repaired = normalize_speech_wav(bytes(streaming))
    with wave.open(io.BytesIO(repaired)) as wav:
        assert wav.getnframes() / wav.getframerate() == 1
        assert wav.readframes(wav.getnframes()) == pcm
    assert int.from_bytes(repaired[4:8], 'little') == len(repaired) - 8

def test_invalid_speech_audio_has_readable_fallback():
    with pytest.raises(ProviderError, match='invalid audio'):
        normalize_speech_wav(b'not-wave-data')

def test_spoken_handover_uses_current_state_and_keeps_holds(organization_api,monkeypatch):
    client,org,repo=organization_api
    seed(repo);sent=[]
    monkeypatch.setattr('shiftproof.providers.synthesize',lambda text: sent.append(text) or b'RIFF-test-wave')
    view=client.get(f'/organizations/{org}/workspace').json()
    response=client.post(f'/organizations/{org}/speech',json={'batch_id':'all','kind':'handover','expected_version':view['version']})
    assert response.status_code==200,response.text
    assert response.headers['content-type']=='audio/wav'
    assert all(row['text']['hi'] in sent[0] for row in view['summary']['items'])
    assert any(row['kind']=='outstanding' for row in view['summary']['items'])
    assert view['batches'][0]['quality']=='pending'

def test_public_speech_calls_cannot_spend_credits(organization_api):
    _,org,_=organization_api
    client=TestClient(app)
    assert client.post(f'/organizations/{org}/speech',json={'batch_id':'all','kind':'handover','expected_version':1}).status_code==401
    assert client.post('/speech',json={'batch_id':'all','kind':'handover'}).status_code==404
