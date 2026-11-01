"""Reproduce three manufacturing workflows through real services in isolated SQLite.
Uses labeled scripted text fixtures; this is not an AI accuracy measurement.
"""
import argparse
import json
import os
import tempfile
from datetime import datetime,timezone
from pathlib import Path
from shiftproof.config import settings
from shiftproof import service,providers
from shiftproof.fixtures import ACTORS as DEMO_ACTORS
from shiftproof.models import NoteCreate,ResolveRequest
from shiftproof.repository import LocalRepository
from shiftproof.engine import handover,answer_question


def run():
    os.environ['EXTRACTION_PROVIDER']='scripted';settings.cache_clear()
    with tempfile.TemporaryDirectory(prefix='shiftproof-demos-') as temp:
        repo=LocalRepository(Path(temp)/'workspace.sqlite3')
        def add(sample_id,batch,corrects=(),review=True):
            sample=next(s for s in providers.SAMPLES if s['id']==sample_id);actor=DEMO_ACTORS[sample['role']]
            note=service.create_note(repo,NoteCreate(batch_id=batch,recorded_at=datetime.now(timezone.utc),idempotency_key=f'{batch}:{sample_id}',supersedes=list(corrects)),actor)
            service.submit_transcript(repo,note['id'],sample['text'],actor);service.process_note(repo,note['id'])
            claims=[repo.load()['claims'][cid] for cid in repo.load()['notes'][note['id']]['claim_ids']]
            for claim in claims if review else []:
                targets=[cid for cid in corrects if repo.load()['claims'][cid]['property']==claim['property']]
                service.resolve(repo,claim['id'],ResolveRequest(expected_version=repo.load()['version'],action='confirm',reason='Fictional demonstration review',supersedes=targets),DEMO_ACTORS['quality' if sample['role']=='quality' else 'supervisor'])
            return claims
        fifteen=add('quantity-15','B-18')[0]
        add('quantity-50','B-18',[fifteen['id']]);add('packing-only','B-18');add('task','B-18')
        seal=add('seal-inspection','B-19');add('packing-only','B-19')
        add('packing-hold','B-17');add('dispatch','B-17');add('dispatch-pending','B-17',review=False)
        snapshot=handover(repo.load());byid={b['id']:b for b in snapshot['batches']}
        assert byid['B-18']['quantity']==50
        assert repo.load()['claims'][fifteen['id']]['status']=='superseded'
        assert byid['B-19']['status']=='hold' and len(byid['B-19']['tasks'])==2
        assert byid['B-17']['status']=='hold' and any(r['code']=='pending_work' for r in byid['B-17']['readiness_reasons'])
        return {'status':'passed','scope':'Three fictional scripted-fixture workflows through create/process/review services; not live inference.',
            'workflows':[{ 'name':name,'batch':byid[bid], 'pending_answer':answer_question(repo.load(),bid,'What is pending?'),
                          'history_answer':answer_question(repo.load(),bid,'What changed?')}
                         for name,bid in [('production','B-18'),('quality','B-19'),('dispatch','B-17')]]}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='evaluation/results/manufacturing-demos.json');a=p.parse_args()
    result=run();Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(f"{result['status']}: {a.output}")
