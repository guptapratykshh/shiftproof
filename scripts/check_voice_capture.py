"""Live, fictional speech integration check. Synthesized audio is not human-microphone evidence.
Does not change provider configuration, billing, organization records or models.
"""
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from shiftproof import providers, service
from shiftproof.config import settings


def main():
    result = {'generated_at':datetime.now(timezone.utc).isoformat(), 'input_kind':'synthetic_fictional_speech',
              'human_microphone_verified':False, 'model':settings().gemini_model, 'stages':{}}
    stage='timbre'
    try:
        started=time.monotonic()
        audio=providers.synthesize('पैकिंग पूरी हो गई है। क्वालिटी चेक अभी बाकी है।')
        service.validate_audio(audio,require_signal=True)
        result['stages'][stage]={'status':'passed','ms':round((time.monotonic()-started)*1000),'quality':service.audio_quality(audio)}
        stage='prisma';started=time.monotonic()
        transcript,request_id=providers.transcribe(audio)
        result['stages'][stage]={'status':'passed','ms':round((time.monotonic()-started)*1000),'transcript':transcript,'request_id':request_id}
        stage='gemini';started=time.monotonic()
        output,request_id=providers.extract(transcript,'B-17')
        actual={(c.property,c.value) for c in output.claims}
        passed=('packing','complete') in actual and ('quality','pending') in actual and ('quality','cleared') not in actual
        result['stages'][stage]={'status':'passed' if passed else 'failed','ms':round((time.monotonic()-started)*1000), 'request_id':request_id,'output':output.model_dump(mode='json')}
        result['status']='passed' if passed else 'failed'
    except Exception as exc:
        result['status']='blocked'
        result['stages'][stage]={'status':'blocked','error_category':getattr(exc,'category',type(exc).__name__),'error':str(exc)}
    path=Path('artifacts/voice-live-speech.json');path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'stages':{k:v['status'] for k,v in result['stages'].items()},'report':str(path)}))
    return result['status']=='passed'

if __name__=='__main__': raise SystemExit(0 if main() else 1)
