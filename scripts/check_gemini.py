"""Live development checks; explicit --activate pins a passing model in .env."""
import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from shiftproof.config import settings
from shiftproof.providers import extract, ExtractionUnavailable, prompt_version
from shiftproof.diagnostics import save_check

QUESTION = {'clarification': {'id': 'B-17:quality', 'text': 'बैच 17 का quality check clear हुआ है, या अभी pending है?', 'claim_ids': [], 'version': 1}}
CASES = [
    {'id':'future', 'text':'क्वालिटी चेक पूरा होने वाला है बस आधा घंटा और लगेगा', 'claims':[('quality','pending','actual')]},
    {'id':'negation', 'text':'Packing complete nahi hai.', 'claims':[('packing','pending','actual')]},
    {'id':'not-pending', 'text':'Quality check pending nahi hai, inspection clear ho gaya.', 'claims':[('quality','cleared','actual')]},
    {'id':'fifteen', 'text':'Abhi pandrah cartons pack hue hain.', 'claims':[('quantity',15,'actual')]},
    {'id':'correction', 'text':'Correction: pandrah nahi, pachaas cartons pack hue hain.', 'claims':[('quantity',50,'actual')]},
    {'id':'conditional', 'text':'Quality clear hone ke baad dispatch ready hoga.', 'claims':[('dispatch','ready','conditional')]},
    {'id':'context-reply', 'text':'Haan, quality clear ho gaya.', 'context':QUESTION, 'claims':[('quality','cleared','actual')]},
    {'id':'ambiguous-reply', 'text':'Haan.', 'context':QUESTION, 'claims':[], 'uncertain':True},
    {'id':'wrong-batch', 'text':'Batch atharah ka packing complete nahi hai.', 'claims':[('packing','pending','actual')], 'mentioned_batch':'B-18'},
    {'id':'microphone', 'text':'हेलो हेलो आवाज आ रही है?', 'claims':[]},
    {'id':'seal', 'text':'Cartons ka seal theek nahi hai. Quality inspection pending hai. Seal inspect karna hai.', 'claims':[('quality','pending','actual')], 'task':True},
    {'id':'separate-facts', 'text':'Packing complete hai, lekin quality check abhi pending hai.', 'claims':[('packing','complete','actual'),('quality','pending','actual')]},
]


def assess(case, result):
    actual={(c.property,c.value,c.modality) for c in result.claims if c.property != 'task'}
    valid = actual == set(tuple(c) for c in case['claims'])
    tasks=[c for c in result.claims if c.property=='task']
    valid = valid and bool(tasks) == bool(case.get('task'))
    if case.get('task'): valid = valid and all('seal' in c.excerpt.lower() for c in tasks)
    if case.get('uncertain'): valid = valid and bool(result.uncertainty)
    if case.get('mentioned_batch'): valid = valid and result.mentioned_batch == case['mentioned_batch']
    if case.get('context'): valid = valid and all(QUESTION['clarification']['id'] in c.context_refs for c in result.claims)
    return bool(valid)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model');parser.add_argument('--activate',action='store_true');a=parser.parse_args()
    os.environ['EXTRACTION_PROVIDER']='gemini'
    if a.model: os.environ['GEMINI_MODEL_ID']=a.model
    settings.cache_clear()
    result={'status':'pending','provider':'gemini','model':settings().gemini_model,'prompt_version':prompt_version(),
            'generated_at':datetime.now(timezone.utc).isoformat(),'requested':len(CASES),'cases':[]}
    try:
        for case in CASES:
            extraction,rid=extract(case['text'],'B-17',context=case.get('context'))
            result['cases'].append({'id':case['id'],'passed':assess(case,extraction),'output':extraction.model_dump(mode='json'),'request_id':rid})
        result['status']='passed' if all(c['passed'] for c in result['cases']) else 'failed'
    except ExtractionUnavailable as exc:
        result.update(status='blocked',error=str(exc),error_category=exc.category)
    save_check(result)
    path=Path('.local/gemini-smoke.json');path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    if a.activate and result['status']=='passed':
        from dotenv import set_key
        env=Path(__file__).resolve().parents[1]/'.env'
        set_key(env,'GEMINI_MODEL_ID',settings().gemini_model);set_key(env,'EXTRACTION_PROVIDER','gemini')
        result['activated']=True
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='passed' else 1

if __name__=='__main__':sys.exit(main())
