#!/usr/bin/env python3
"""Isolated factory envelope probe; no live providers and no existing data changes.

PYTHONPATH=backend .venv/bin/python scripts/pilot_load_probe.py
The generated fixtures are controlled engineering inputs, not factory evidence.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import json
import math
import os
from pathlib import Path
import platform
import secrets
import sqlite3
import tempfile
import time


def metrics(rows):
    values=sorted(row['milliseconds'] for row in rows)
    return {'count':len(rows), 'p50_ms':round(values[max(0,math.ceil(len(values)*.5)-1)],2) if values else None,
            'p95_ms':round(values[max(0,math.ceil(len(values)*.95)-1)],2) if values else None,
            'errors':sum(not row['ok'] for row in rows)}


def run(history_notes=10000, worker_members=50, concurrency=10):
    if not 1 <= concurrency <= worker_members or history_notes < concurrency * 50:
        raise ValueError('Use at least one worker per concurrent client and 50 historical notes per work item')
    members = worker_members + 1  # The organization owner is additional to workers.
    with tempfile.TemporaryDirectory(prefix='shiftproof-pilot-load-') as temporary:
        os.environ.update(SHIFTPROOF_DATA_DIR=temporary, SHIFTPROOF_SHARED_USAGE_DB=str(Path(temporary)/'usage.sqlite3'),
                          EXTRACTION_PROVIDER='scripted', SHIFTPROOF_ENV='local', SHIFTPROOF_SQLITE_WAL='false',
                          MAX_NOTES_PER_DAY='10000', SHIFTPROOF_SIGNUP_OPEN='true')
        from fastapi.testclient import TestClient
        from shiftproof.api import app
        from shiftproof import identity
        from shiftproof.config import settings
        from shiftproof.models import now
        settings.cache_clear()
        org_id='probe-factory'; location='probe-location'
        observed=datetime.now(timezone.utc); timestamp=observed.isoformat()
        password=identity.PASSWORDS.hash('probe-only-password-never-used')
        workers=[]
        with identity.database() as db:
            db.execute('INSERT INTO organizations(id,name,industry,timezone,setup,login_code) VALUES (?,?,?,?,?,?)',
                       (org_id,'Isolated Probe Factory','manufacturing','Asia/Kolkata','{}','PROBEFACTORY'))
            for index in range(members):
                ident=f'probe-user-{index}'; role='supervisor' if index==0 else 'operator'; access='owner' if index==0 else 'member'
                token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24)
                db.execute('INSERT INTO users(id,email,name,password,recovery) VALUES (?,?,?,?,?)',
                           (ident,f'probe-{index}@example.invalid' if index==0 else None,f'Probe worker {index}',password,'[]'))
                db.execute('INSERT INTO memberships VALUES (?,?,?,?)',(org_id,ident,access,role))
                if index:
                    db.execute('INSERT INTO employee_credentials VALUES (?,?,?,?,?,?,?)',
                               (org_id,f'EMP{index:03}',ident,f'Probe worker {index}',password,1,time.time()))
                db.execute('INSERT INTO sessions(token,user_id,csrf,expires,auth_kind,org_id) VALUES (?,?,?,?,?,?)',
                           (identity.digest(token),ident,csrf,time.time()+3600,'employee' if index else 'email',org_id if index else None))
                workers.append({'id':ident,'role':role,'token':token,'csrf':csrf,'team':index%concurrency})
        org={'id':org_id,'industry':'manufacturing'}
        repo=identity.tenant_repo(org)
        with repo.transaction() as state:
            state['locations']={location:{'id':location,'name':'Probe factory'}}
            state['teams']={};state['shift_occurrences']={};state['assignments']={};state['work_items']={}
            for group in range(concurrency):
                team=f'team-{group}';shift=f'shift-{group}';batch=f'ITEM-{group}'
                state['teams'][team]={'id':team,'name':f'Probe team {group}','location_id':location}
                state['work_items'][batch]={'id':batch,'name':f'Probe batch {group}','line':'Probe line','target':500,'team_id':team,'location_id':location}
                state['shift_occurrences'][shift]={'id':shift,'name':f'Probe shift {group}','team_id':team,'location_id':location,
                    'starts_at':(observed-timedelta(hours=1)).isoformat(),'ends_at':(observed+timedelta(hours=7)).isoformat(),'status':'open'}
            for worker in workers:
                shift=f'shift-{worker["team"]}';key=f'{shift}:{worker["id"]}'
                state['assignments'][key]={'id':key,'shift_id':shift,'user_id':worker['id'],'work_item_ids':[f'ITEM-{worker["team"]}']}
            for index in range(history_notes):
                group=index%concurrency;batch=f'ITEM-{group}';note=f'history-note-{index}';claim=f'history-claim-{index}'
                author=next(w for w in workers if w['team']==group and w['role']=='operator')
                actor={'id':author['id'],'name':'Fictional historical worker','role':'operator'}
                state['notes'][note]={'id':note,'batch_id':batch,'shift_id':f'shift-{group}','actor':actor,'recorded_at':timestamp,
                    'received_at':timestamp,'status':'processed','source':'scripted_fixture','audio_key':f'notes/{note}.wav','has_audio':False,
                    'transcripts':[{'revision':1,'text':'Packing was pending.','kind':'controlled_probe_fixture','created_at':timestamp}],
                    'claim_ids':[claim],'revision':1,'supersedes':[],'error':None}
                state['claims'][claim]={'id':claim,'note_id':note,'batch_id':batch,'property':'packing','value':'pending','excerpt':'Packing was pending',
                    'actor':actor,'transcript_revision':1,'modality':'actual','status':'rejected','introduced_version':1,'received_at':timestamp,'supersedes':[]}
                state['resolutions']['review-'+claim]={'id':'review-'+claim,'claim_id':claim,'action':'reject','reason':'Controlled historical fixture',
                    'actor':{'id':workers[0]['id'],'name':'Probe supervisor','role':'supervisor'},'version':1,'created_at':timestamp}
            state['version']=1
        rows=[]
        def participant(index):
            worker=workers[index+1];batch=f'ITEM-{worker["team"]}';shift=f'shift-{worker["team"]}'
            measured=[]
            with TestClient(app,raise_server_exceptions=True) as client:
                client.cookies.set(identity.COOKIE,worker['token'])
                client.headers.update({'X-CSRF-Token':worker['csrf'],'X-Shift-ID':shift})
                for sequence, operation in enumerate(['workspace_read','index_read','scoped_page','note_write','workspace_read','scoped_page','note_write','workspace_read']):
                    start=time.perf_counter();status=200;detail=None;ok=True
                    try:
                        if operation=='workspace_read':
                            response=client.get(f'/organizations/{org_id}/workspace?limit=25')
                            status=response.status_code;ok=status==200
                            if ok:
                                payload=response.json()
                                ok=all(note['batch_id']==batch for note in payload['notes'])
                                if not ok:detail='Scope violation in response'
                            else:detail=response.text[:180]
                        elif operation=='note_write':
                            response=client.post(f'/organizations/{org_id}/notes',json={'batch_id':batch,'shift_id':shift,
                                'recorded_at':now(),'idempotency_key':f'probe-{index}-{sequence}'})
                            status=response.status_code;ok=status==201
                            if not ok:detail=response.text[:180]
                        elif operation=='scoped_page':
                            page=repo.query_records('notes',batch_id=batch,limit=25,offset=25)
                            ok=len(page)==25 and all(n['batch_id']==batch for n in page)
                        else:
                            index_state=repo.load_index();ok=len(index_state['work_items'])==concurrency and not index_state['notes']
                    except Exception as exc:
                        ok=False;status=0;detail=f'{type(exc).__name__}: {str(exc)[:140]}'
                    measured.append({'operation':operation,'milliseconds':(time.perf_counter()-start)*1000,'ok':ok,'status':status,'detail':detail})
            return measured
        started=time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for measured in pool.map(participant,range(concurrency)):rows.extend(measured)
        groups=defaultdict(list)
        for row in rows:groups[row['operation']].append(row)
        failures=[row for row in rows if not row['ok']]
        result={'generated_at':now(),'purpose':'Controlled engineering envelope; not a production capacity or model-accuracy claim',
                'isolation':'Temporary identity/workspace databases deleted after this run; no .local records or provider calls',
                'fixture':{'organization_count':1,'identity_members':members,'owner_members':1,'worker_members':worker_members,'concurrent_clients':concurrency,
                    'historical_notes':history_notes,'historical_claims':history_notes,'historical_review_events':history_notes,
                    'work_items':concurrency,'historical_notes_per_active_item':history_notes//concurrency},
                'runtime':{'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,'platform':platform.system(),'journal_mode':'delete'},
                'elapsed_seconds':round(time.perf_counter()-started,3),'overall':metrics(rows),
                'by_operation':{name:metrics(values) for name,values in groups.items()},
                'http_status_counts':dict(Counter(str(row['status']) for row in rows)),
                'lock_errors':sum('locked' in (row['detail'] or '').lower() for row in failures),
                'failures':failures,'provider_calls':0,'result':'complete' if not failures else 'completed_with_failures'}
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='artifacts/pilot-load-probe.json')
    parser.add_argument('--workers',type=int,default=50)
    parser.add_argument('--history-notes',type=int,default=10000)
    parser.add_argument('--concurrency',type=int,default=10)
    args=parser.parse_args()
    result=run(history_notes=args.history_notes,worker_members=args.workers,concurrency=args.concurrency)
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'output':str(output),'result':result['result'],'overall':result['overall'],'by_operation':result['by_operation'],'lock_errors':result['lock_errors']},indent=2))
