"""Five fictional development checks of the pinned live model's task interpretations."""
import json
from pathlib import Path
from datetime import datetime, timezone
from shiftproof import providers
from shiftproof.config import settings

CASES = [
    ('done','मैंने कार्टन के लेबल जाँच लिए हैं। काम पूरा कर दिया है।','done'),
    ('negative','लेबल की जाँच अभी पूरी नहीं हुई है।','not_done'),
    ('future','लेबल की जाँच कल करूँगा।','not_done'),
    ('conditional','मशीन ठीक होने के बाद लेबल जाँचूँगा।','not_done'),
    ('ambiguous','हाँ।','unclear'),
]

def main():
    result={'generated_at':datetime.now(timezone.utc).isoformat(),'model':settings().gemini_model,
            'prompt_version':providers.prompt_version(),'requested':len(CASES),'cases':[],'input_kind':'fictional_development_text'}
    context={'task':{'id':'task-label-check','title':'Check carton labels','owner_id':'fictional-worker'}}
    for name,text,expected in CASES:
        try:
            output,rid=providers.extract(text,'B-17',context=context)
            completion=output.task_completion
            result['cases'].append({'id':name,'passed':bool(completion and completion.outcome==expected),
                                    'request_id':rid,'output':output.model_dump(mode='json')})
        except providers.ProviderError as e:
            result['cases'].append({'id':name,'passed':False,'error_category':e.category,'error':str(e)})
            if e.category in ('quota','authorization','missing_credentials'):break
    result['passed']=sum(c['passed'] for c in result['cases'])
    result['status']='passed' if result['passed']==result['requested'] else 'incomplete' if len(result['cases'])<result['requested'] else 'failed'
    Path('artifacts/voice-live-tasks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','passed','requested')}))
    return result['status']=='passed'

if __name__=='__main__':raise SystemExit(0 if main() else 1)
