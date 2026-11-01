"""Inventory retention-due recordings. Does not delete evidence or recordings."""
import argparse
import json
from datetime import datetime,timedelta,timezone
from shiftproof.identity import database,organization,tenant_repo

def inventory(org_id):
    with database(write=False) as db: row=db.execute('SELECT * FROM organizations WHERE id=?',(org_id,)).fetchone()
    if not row: raise ValueError('Organization not found')
    state=tenant_repo(organization(dict(row))).load();days=state.get('data_policy',{}).get('retention_days')
    if not isinstance(days,int) or days<1: raise ValueError('Owner must set an explicit retention policy first')
    cutoff=datetime.now(timezone.utc)-timedelta(days=days)
    due=[{'note_id':n['id'],'recorded_at':n['recorded_at'],'has_audio':n['has_audio'],'status':n['status']}
         for n in state['notes'].values() if n.get('has_audio') and datetime.fromisoformat(n['recorded_at'])<cutoff]
    return {'organization_id':org_id,'retention_days':days,'due_recordings':due,'action':'owner_review_required','deleted':0}
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('organization_id');args=parser.parse_args();print(json.dumps(inventory(args.organization_id),indent=2))
