import json
from .repository import repository
from .service import process_note

def handler(event, context):
    failures = []
    for record in event.get('Records', []):
        try:
            body = json.loads(record['body'])
            process_note(repository(), body['note_id'], body.get('transcribe_only', False))
        except Exception:
            failures.append({'itemIdentifier': record['messageId']})
    return {'batchItemFailures': failures}


def local_pass(organization_id=None):
    """Poll registered organization stores, never infer tenancy from a path."""
    from .identity import database, organization, tenant_repo
    from .durable_jobs import run_once
    from .config import settings
    if settings().cloud:
        raise RuntimeError('The pilot worker requires a local persistent database host')
    with database(write=False) as db:
        if organization_id:
            rows = db.execute('SELECT * FROM organizations WHERE id=?', (organization_id,)).fetchall()
        else:
            rows = db.execute('SELECT * FROM organizations ORDER BY id').fetchall()
    count = 0
    for row in rows:
        org = organization(dict(row))
        if org['profile']['status'] != 'available':
            continue
        count += int(run_once(tenant_repo(org)))
    return count


def write_health(status='running'):
    import os
    from pathlib import Path
    from .config import settings
    from .models import now
    location = Path(os.getenv('SHIFTPROOF_WORKER_HEALTH_FILE') or str(settings().data_dir / 'worker-health.json'))
    location.parent.mkdir(parents=True, exist_ok=True)
    temporary = location.with_name(location.name + f'.{os.getpid()}.tmp')
    temporary.write_text(json.dumps({'status': status, 'heartbeat_at': now(), 'pid': os.getpid()}) + '\n')
    temporary.replace(location)


if __name__ == '__main__':
    import argparse
    import time
    from threading import Event, Thread
    parser = argparse.ArgumentParser(description='Durable local ShiftProof worker; does not enable AWS or billing.')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--organization-id')
    parser.add_argument('--poll-seconds', type=float, default=1.0)
    args = parser.parse_args()
    if args.poll_seconds < 0.1:
        parser.error('--poll-seconds must be at least 0.1')
    stopped = Event()
    def health_loop():
        while not stopped.wait(5):
            write_health()
    heartbeat = Thread(target=health_loop, daemon=True)
    write_health(); heartbeat.start()
    try:
        while True:
            processed = local_pass(args.organization_id)
            if args.once:
                print(json.dumps({'processed_jobs': processed}))
                break
            if not processed:
                time.sleep(args.poll_seconds)
    finally:
        stopped.set(); heartbeat.join(timeout=1); write_health('stopped')
