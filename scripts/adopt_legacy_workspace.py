"""Explicit local-only ownership assignment; never called from public signup.

PYTHONPATH=backend .venv/bin/python scripts/adopt_legacy_workspace.py --owner-email owner@example.com --organization-name 'My factory'
Existing source files are preserved. The operation is idempotent via a receipt.
"""
import argparse
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime,timezone
from shiftproof import identity
from shiftproof.accounts_api import new_org
from shiftproof.config import settings
from shiftproof.engine import BATCHES
from shiftproof.repository import LocalRepository

def adopt(source, owner_email, organization_name):
    source=Path(source).resolve();receipt=identity.root() / ('migration-'+hashlib.sha256(str(source).encode()).hexdigest()[:16]+'.json')
    if not source.is_file():raise ValueError('Legacy database does not exist')
    with identity.database() as db:
        existing=db.execute('SELECT receipt FROM migrations WHERE source=?',(str(source),)).fetchone()
        if existing:
            prior=json.loads(existing[0])
            if prior['owner_email']!=identity.email(owner_email):raise ValueError('This source is already assigned to another owner')
            return prior
        user=db.execute('SELECT id FROM users WHERE email=?',(identity.email(owner_email),)).fetchone()
        if not user:raise ValueError('The owner must create an account first')
        org_id=new_org(db,user[0],organization_name,'manufacturing','Asia/Kolkata')
        target=identity.root()/'organizations'/org_id;target.mkdir(parents=True)
        backup=identity.root()/'backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f');backup.mkdir(parents=True)
        with sqlite3.connect(source) as original,sqlite3.connect(backup/'workspace.sqlite3') as backup_db: original.backup(backup_db)
        shutil.copy2(backup/'workspace.sqlite3',target/'workspace.sqlite3')
        for folder in ('notes',):
            if (source.parent/folder).exists():
                shutil.copytree(source.parent/folder,backup/folder)
                shutil.copytree(source.parent/folder,target/folder)
        repo=LocalRepository(target/'workspace.sqlite3')
        with repo.transaction() as state:
            state['profile']='manufacturing';state['profile_version']=1;state['work_items']={b['id']:b for b in BATCHES}
        result={'organization_id':org_id,'owner_email':identity.email(owner_email),'source':str(source),'backup':str(backup),'preserved_original':True}
        db.execute('INSERT INTO migrations VALUES (?,?)',(str(source),json.dumps(result)))
    temp=receipt.with_suffix('.tmp');temp.write_text(json.dumps(result,indent=2)+'\n');temp.replace(receipt)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',default=str(settings().data_dir/'shiftproof.sqlite3'));p.add_argument('--owner-email',required=True);p.add_argument('--organization-name',required=True);a=p.parse_args()
    print(json.dumps(adopt(a.source,a.owner_email,a.organization_name),indent=2))
