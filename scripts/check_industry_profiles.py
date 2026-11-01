"""Six development-only live integration checks. Never a held-out accuracy score."""
import json
import os
import secrets
import tempfile
import time
from pathlib import Path
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from shiftproof.config import settings
from shiftproof.api import app

CASES=[
 ('manufacturing','CARTON-77','Packing complete hai, lekin quality inspection abhi pending hai.', [('packing','complete'),('quality','pending')]),
 ('manufacturing','CARTON-77','Quality check poora hone mein aadha ghanta aur lagega. Abhi pending hai.', [('quality','pending')]),
 ('maintenance','PUMP-42','Machine chal rahi hai, lekin vibration ka fault abhi unresolved hai.', [('operating','running'),('fault','open')]),
 ('maintenance','PUMP-42','Temporary repair kiya hai. Permanent repair abhi pending hai.', [('repair','temporary'),('repair','pending')]),
 ('warehousing','ORDER-582','Order ki packing complete hai, lekin invoice documents verification pending hai.', [('packing','complete'),('documents','pending')]),
 ('warehousing','ORDER-582','Dispatch ready hai, lekin documents abhi verify nahi hue hain.', [('dispatch','ready'),('documents','pending')]),
]

def run(output):
    configured=settings()
    if configured.provider!='gemini' or not configured.gemini_free_tier_confirmed or not configured.gemini_key:raise RuntimeError('Configure the existing free-tier Gemini integration before live checks')
    rows=[]
    with tempfile.TemporaryDirectory(prefix='shiftproof-industry-smoke-') as folder:
        old=os.environ.get('SHIFTPROOF_DATA_DIR');os.environ['SHIFTPROOF_DATA_DIR']=folder;settings.cache_clear()
        try:
            for index,(industry,work,text,expected) in enumerate(CASES):
                client=TestClient(app)
                r=client.post('/auth/signup',json={'name':'Integration Test','email':f'case{index}@example.com','password':secrets.token_urlsafe(24),'organization_name':'Isolated development check','industry':industry})
                r.raise_for_status();org=r.json()['organization_id'];client.headers['X-CSRF-Token']=r.json()['csrf_token'];base='/organizations/'+org
                client.post(base+'/work-items',json={'id':work,'name':'Fictional work item'}).raise_for_status()
                n=client.post(base+'/notes',json={'batch_id':work,'recorded_at':datetime.now(timezone.utc).isoformat(),'idempotency_key':f'integration-case-{index}'}).json()['note']['id']
                client.post(base+'/notes/'+n+'/transcript',json={'transcript':text}).raise_for_status()
                client.post(base+'/notes/'+n+'/process',json={}).raise_for_status()
                result=client.get(base+'/notes/'+n).json();actual=[(c['property'],c['value']) for c in result['claims']]
                passed=all(pair in actual for pair in expected) and all(c['excerpt'] in text for c in result['claims']) and not any(c['value'] in ('cleared','verified','resolved') for c in result['claims'])
                rows.append({'industry':industry,'work_item':work,'transcript':text,'expected':expected,'actual':actual,'passed':passed,'status':result['status'],'error':result.get('error'),'model':result.get('extraction_model'),'prompt':result.get('extraction_prompt_version'),'origin':result.get('extraction_origin'),'request_id':result.get('extraction_request_id'),'timings':result.get('timings')})
                print(f'{industry} case {index+1}: {"passed" if passed else "failed"}',flush=True)
                # Separate free-tier development calls; never silently change models.
                if index<len(CASES)-1:time.sleep(3)
        finally:
            if old is None:os.environ.pop('SHIFTPROOF_DATA_DIR',None)
            else:os.environ['SHIFTPROOF_DATA_DIR']=old
            settings.cache_clear()
    report={'scope':'Six development-only text integration checks through real account and processing services; not independent industry accuracy or human/audio evaluation.','model':configured.gemini_model,'passed':sum(r['passed'] for r in rows),'requested':len(CASES),'cases':rows,'created_at':datetime.now(timezone.utc).isoformat()}
    Path(output).parent.mkdir(parents=True,exist_ok=True);Path(output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',default='evaluation/results/industry-development-smoke.json');a=p.parse_args();r=run(a.output);print(f'{r["passed"]}/{r["requested"]} development checks passed. {a.output}')
