"""Explicit assisted capture; a selected worker never becomes an authenticated actor."""
from fastapi import HTTPException
from . import identity, pilot_scope

def validate(state, org_id, helper_id, worker_id, shift_id, item_id, recorded_at=None):
    if not worker_id or worker_id==helper_id:return None
    grants=state.get('assisted_capture_permissions',{})
    if shift_id not in grants.get(helper_id,[]):raise HTTPException(403,'The owner must allow assisted recording for this shift')
    with identity.database(write=False) as db:
        helper=db.execute('SELECT role,access FROM memberships WHERE org_id=? AND user_id=?',(org_id,helper_id)).fetchone()
        worker=db.execute('SELECT u.id,u.name,m.role,m.access FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.org_id=? AND m.user_id=?',(org_id,worker_id)).fetchone()
    if not helper or not worker or worker['role']!='operator':raise HTTPException(403,'Select an active assigned worker')
    for ident in (helper_id,worker_id):
        if not any(a['user_id']==ident and a['shift_id']==shift_id and (not a.get('work_item_ids') or item_id in a['work_item_ids']) for a in state.get('assignments',{}).values()):
            raise HTTPException(403,'The worker and helper must both be assigned to this work and shift')
    if recorded_at:
        pilot_scope.check_capture(state,dict(worker),worker_id,item_id,shift_id,recorded_at)
    return {'id':worker['id'],'name':worker['name'],'role':worker['role']}

def validate_note(repo,note):
    if not note.get('reported_by'):return
    state=repo.load_index() if hasattr(repo,'load_index') else repo.load()
    validate(state,repo.organization_id,note['actor']['id'],note['reported_by']['id'],note.get('shift_id'),note['batch_id'])
