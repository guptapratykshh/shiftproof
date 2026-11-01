"""Local operator health check, with job ages and no transcripts or identities."""
import json
import os
import sys
import time
from datetime import datetime,timezone
from pathlib import Path
from shiftproof.config import settings
from shiftproof.identity import database,organization,tenant_repo

def report():
    heartbeat=Path(os.getenv('SHIFTPROOF_WORKER_HEALTH_FILE') or settings().data_dir/'worker-health.json')
    age=time.time()-heartbeat.stat().st_mtime if heartbeat.exists() else None
    with database(write=False) as db: rows=db.execute('SELECT * FROM organizations').fetchall()
    queued=0;blocked=0;oldest=0;now=datetime.now(timezone.utc)
    for row in rows:
        repo=tenant_repo(organization(dict(row)))
        with repo.connect() as db:
            jobs=db.execute("SELECT document FROM workspace_records WHERE collection='jobs'").fetchall()
        for raw in jobs:
            job=json.loads(raw[0])
            if job.get('status') in ('queued','running'):
                queued+=1;oldest=max(oldest,(now-datetime.fromisoformat(job['queued_at'])).total_seconds())
            if job.get('status')=='authorization_required':blocked+=1
    healthy=age is not None and age<30 and oldest<600
    return {'status':'ok' if healthy else 'attention_required','worker_heartbeat_age_seconds':age,'queued_or_running_jobs':queued,'oldest_job_seconds':oldest,'jobs_needing_supervisor':blocked}

if __name__=='__main__':
    result=report();print(json.dumps(result,indent=2));sys.exit(0 if result['status']=='ok' else 1)
