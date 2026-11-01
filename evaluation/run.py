"""Run supplied-claim engine checks, or delegate to the live Gemini language runner.

python evaluation/run.py --mode engine
EXTRACTION_PROVIDER=gemini python evaluation/run.py --mode live --split held_out
"""
import argparse
import copy
import hashlib
import json
import statistics
import time
from pathlib import Path
from datetime import datetime, timezone
from shiftproof.engine import batch_view, BATCHES, answer_question
from shiftproof.repository import empty_state
from shiftproof.fixtures import ACTORS as DEMO_ACTORS

ROOT=Path(__file__).parent

def make_state(case):
    state=empty_state()
    for index,note in enumerate(case['notes']):
        nid=f'{case["id"]}:note{index}'
        claims=note['claims']
        mentioned=None
        state['notes'][nid]={'id':nid,'batch_id':case['batch_id'],'status':'processed','transcripts':[{'revision':1,'text':note['text']}]}
        for j,raw in enumerate(claims):
            c=copy.deepcopy(raw)
            cid=f'{nid}:{j}'
            c.update(id=cid,batch_id=case['batch_id'],note_id=nid,transcript_revision=1,status='confirmed' if note['reviewed'] else 'draft',actor=DEMO_ACTORS[note['role']].model_dump(),received_at=f'2026-10-07T14:{index:02}:00+00:00',introduced_version=index+1)
            c.setdefault('batch_mismatch',bool(mentioned and mentioned!=case['batch_id']))
            # Reviews are specified scenario inputs, shared with the baseline. They are not model decisions.
            if raw.get('superseded'):
                c['status']='superseded'
            state['claims'][cid]=c
    state['version']=4
    return state

def ablation(state):
    data=copy.deepcopy(state)
    for c in data['claims'].values():
        if c['status']=='superseded':c['status']='confirmed'
        if c['modality']=='conditional':c['modality']='actual';c['condition']=None
    return batch_view(data,BATCHES[0])


def summarize(rows):
    tp=sum(r['predicted_conflict'] and r['expected_conflict'] for r in rows)
    fp=sum(r['predicted_conflict'] and not r['expected_conflict'] for r in rows)
    fn=sum(not r['predicted_conflict'] and r['expected_conflict'] for r in rows)
    return {'state_accuracy':sum(r['passed'] for r in rows)/len(rows) if rows else None,'conflict_precision':tp/(tp+fp) if tp+fp else None,'conflict_recall':tp/(tp+fn) if tp+fn else None,'answer_coverage':None,'evidence_validity':None,'false_ready_count':sum(r['actual']=='verified' and r['expected']!='verified' for r in rows)}

def run(mode='engine',split='all'):
    if mode == 'live':
        from language_run import run as run_language
        return run_language(mode='live', split=split)
    raw=(ROOT/'scenarios.json').read_bytes();data=json.loads(raw)
    cases=[c for c in data['scenarios'] if split=='all' or c['split']==split]
    rows=[];ablated=[];baselines=[];latencies=[];errors=[]
    for case in cases:
        start=time.monotonic()
        try:
            state=make_state(case)
            view=batch_view(state,BATCHES[0])
            base={'id':case['id'],'category':case['category'],'split':case['split'],'expected':case['expected']['status'],'expected_conflict':case['expected']['conflict']}
            def row(v):
                return {**base,'actual':v['status'],'predicted_conflict':bool(v['conflicts']),'passed':v['status']==case['expected']['status'] and v['quantity']==case['expected']['quantity']}
            rows.append(row(view));ablated.append(row(ablation(state)))
            latencies.append((time.monotonic()-start)*1000)
        except Exception as exc:
            errors.append({'case_id':case['id'],'error':str(exc)})
    metrics=summarize(rows)
    if mode=='engine' and rows:
        metrics['evidence_validity']=sum(all(c['excerpt'] in state['notes'][c['note_id']]['transcripts'][0]['text'] for c in state['claims'].values()) for state in [make_state(case) for case in cases])/len(cases)
    report={'status':'completed' if not errors else 'blocked','generated_at':datetime.now(timezone.utc).isoformat(),'scope':'Structured engine contract checks' if mode=='engine' else 'Live Bedrock synthetic-text comparison','mode':mode,'scenario_count':len(rows),'requested_scenario_count':len(cases),'dataset_sha256':hashlib.sha256(raw).hexdigest(),'split_counts':{s:sum(c['split']==s for c in cases) for s in ('development','held_out')},'metrics':metrics,'baseline':{'status':'not_run' if mode=='engine' else ('completed' if baselines else 'blocked'),'metrics':summarize(baselines)},'ablation':{'status':'completed' if ablated else 'not_run','metrics':summarize(ablated)},'latency':{'scope':'engine only' if mode=='engine' else 'extraction plus baseline; not audio end-to-end','median_ms':statistics.median(latencies) if latencies else None,'p95_ms':sorted(latencies)[min(len(latencies)-1,int(len(latencies)*.95))] if latencies else None},'limitations':[data['provenance'],'Engine mode consumes gold structured claims. It does not measure speech recognition or language extraction.','Held-out template variants are related to development templates; independent scenario authoring is still required.','Human audio, user validation, semantic citation correctness, and answer coverage have not been measured.','Full-context Gemini comparison is recorded separately by language_run.py; no baseline score is invented.'],'cases':rows,'errors':errors}
    path=ROOT/'results'/f'{mode}-{split}.json';path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    if mode=='engine' or (mode=='live' and not errors):
        (ROOT.parent/'backend/shiftproof/evaluation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'cases':len(rows),'metrics':metrics,'errors':errors,'report':str(path)},ensure_ascii=False,indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['engine','live'],default='engine');p.add_argument('--split',choices=['all','development','held_out'],default='all');a=p.parse_args();run(a.mode,a.split)
