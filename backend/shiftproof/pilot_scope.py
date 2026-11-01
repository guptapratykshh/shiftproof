"""Pure shift/material-version calculations and server-side assignment checks."""
import copy
import hashlib
import json
import os
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from .repository import Conflict

def check_data_capture_policy(state):
    policy=state.get('data_policy',{})
    if os.getenv('SHIFTPROOF_REQUIRE_DATA_POLICY','false').lower()=='true' and not policy:
        raise HTTPException(409,'The owner must choose a practice or approved real-data policy in Settings before capturing reports')
    if 'real' in (policy.get('mode'),policy.get('data_classification')) and not (policy.get('retention_days') and policy.get('recording_consent') and policy.get('factory_approval')):
        raise HTTPException(409,'The owner must record factory consent and a retention policy before collecting real recordings')

def shift_items(state, shift_id):
    shift = state.get('shift_occurrences', {}).get(shift_id)
    if not shift:
        return set(state.get('work_items', {})) if shift_id == 'shift-B' else set()
    explicit = shift.get('work_item_ids')
    if explicit:
        return set(explicit) & set(state.get('work_items', {}))
    return {key for key, item in state.get('work_items', {}).items()
            if item.get('team_id') == shift['team_id'] and item.get('location_id') == shift['location_id']}

def allowed_shifts(state, org, user_id):
    shifts = list(state.get('shift_occurrences', {}).values())
    if org['access'] == 'owner':
        return shifts
    assigned = {a['shift_id'] for a in state.get('assignments', {}).values() if a['user_id'] == user_id}
    # Incoming members can inspect the explicitly linked outgoing handover.
    assigned |= {sid for sid, h in state.get('handovers', {}).items() if h.get('incoming_shift_id') in assigned}
    return [s for s in shifts if s['id'] in assigned]

def choose_shift(state, org, user_id, requested=None):
    shifts = allowed_shifts(state, org, user_id)
    if requested and requested != 'shift-B':
        if not any(s['id'] == requested for s in shifts):
            raise HTTPException(404, 'Shift not found or not assigned to you')
        return requested
    if requested == 'shift-B':
        if org['access'] != 'owner': raise HTTPException(403, 'The legacy archive is available to the organization owner')
        return requested
    current = datetime.now(timezone.utc)
    active = [s for s in shifts if datetime.fromisoformat(s['starts_at']) <= current <= datetime.fromisoformat(s['ends_at'])]
    if active: return sorted(active, key=lambda s: s['starts_at'], reverse=True)[0]['id']
    if shifts: return sorted(shifts, key=lambda s: s['starts_at'], reverse=True)[0]['id']
    return 'shift-B' if org['access'] == 'owner' else None

def permitted_items(state, org, user_id, shift_id=None):
    if org['access'] == 'owner':
        return shift_items(state, shift_id) if shift_id and shift_id != 'shift-B' else set(state.get('work_items', {}))
    allowed = {s['id'] for s in allowed_shifts(state, org, user_id)}
    if shift_id:
        allowed &= {shift_id}
    ids = set()
    for sid in allowed:
        assignments = [a for a in state.get('assignments', {}).values() if a['shift_id'] == sid and a['user_id'] == user_id]
        if assignments:
            for a in assignments:
                ids |= set(a.get('work_item_ids') or shift_items(state, sid))
        else:
            # Linked outgoing evidence is restricted by incoming assignment too.
            incoming = state.get('handovers', {}).get(sid, {}).get('incoming_shift_id')
            for a in state.get('assignments', {}).values():
                if a['shift_id'] == incoming and a['user_id'] == user_id:
                    ids |= set(a.get('work_item_ids') or shift_items(state, incoming)) & shift_items(state, sid)
    return ids

def require_item(state, org, user_id, item_id, shift_id=None):
    if item_id not in state.get('work_items', {}) or item_id not in permitted_items(state, org, user_id, shift_id):
        raise HTTPException(404, 'Work item not found or not assigned to you')

def assert_note_access(state, org, user_id, note, action='read'):
    require_item(state, org, user_id, note['batch_id'])
    if action == 'process' and org['role'] == 'operator':
        if note['actor']['id'] != user_id:
            raise HTTPException(403, 'Only your own reports can be sent for processing')
        sid = note.get('shift_id')
        if not any(a['user_id'] == user_id and a['shift_id'] == sid for a in state.get('assignments', {}).values()):
            raise HTTPException(403, 'Your assignment ended. A supervisor must take over this report.')

def check_capture(state, org, user_id, item_id, shift_id, recorded_at):
    require_item(state, org, user_id, item_id, shift_id)
    if not shift_id or shift_id == 'shift-B':
        if org['access'] != 'owner': raise HTTPException(422, 'Choose your assigned shift')
        return False
    shift = state['shift_occurrences'][shift_id]
    current = datetime.now(timezone.utc)
    end = datetime.fromisoformat(shift['ends_at'])
    if recorded_at < datetime.fromisoformat(shift['starts_at']) - timedelta(hours=1) or recorded_at > end + timedelta(hours=1):
        raise HTTPException(422, 'This recording belongs to a different date than the selected shift. Keep the draft and ask your organization owner to assign a shift covering the recording time.')
    if current > end + timedelta(hours=72):
        raise HTTPException(409, 'This report is over 72 hours late. Keep the recording and ask your supervisor to import it.')
    if org['access'] != 'owner' and not any(a['user_id'] == user_id and a['shift_id'] == shift_id for a in state.get('assignments', {}).values()):
        raise HTTPException(403, 'You can read this handover but were not assigned to record in its shift')
    return current > end or shift.get('status') == 'closed'

def filtered_state(state, item_ids, shift_id=None):
    result = {k: v for k, v in state.items() if k not in ('notes','claims','resolutions','jobs','snapshots','acknowledgements','work_items','handovers','assignments')}
    result['work_items'] = {k:v for k,v in state.get('work_items', {}).items() if k in item_ids}
    result['claims'] = {k:v for k,v in state['claims'].items() if v['batch_id'] in item_ids}
    result['notes'] = {k:v for k,v in state['notes'].items() if v['batch_id'] in item_ids}
    result['resolutions'] = {k:v for k,v in state['resolutions'].items() if v.get('claim_id') in result['claims'] or v.get('note_id') in result['notes']}
    result['jobs'] = {k:v for k,v in state.get('jobs', {}).items() if v.get('note_id', k) in result['notes']}
    result['snapshots'] = {}
    result['acknowledgements'] = {k:v for k,v in state['acknowledgements'].items() if v.get('shift_id','shift-B') == (shift_id or 'shift-B')
        and {b['id'] for b in state.get('snapshots',{}).get(v.get('snapshot_id'),{}).get('batches',[])} <= item_ids}
    if shift_id and shift_id != 'shift-B':
        result['version'] = state.get('handovers', {}).get(shift_id, {}).get('version', 1)
        result['shift_name'] = state['shift_occurrences'][shift_id]['name']
    return copy.deepcopy(result)

def sync_handovers(state, before=None):
    """Material fingerprints avoid re-reading unrelated history under write locks.

    A scoped transaction supplies complete history for its touched work items.
    Unloaded item fingerprints stay unchanged. Receipt/playback/job leases are
    not part of a handover's material contents.
    """
    touched = set(state.get('_transaction_batch_ids', state.get('work_items', {})))
    material = state.setdefault('material_items', {})
    if before is not None and before.get('material_items'):
        changed_items = {key for key in touched if state.get('work_items', {}).get(key) != before.get('work_items', {}).get(key)
                         or state.get('quantity_exceptions', {}).get(key) != before.get('quantity_exceptions', {}).get(key)}
        for collection in ('notes','claims'):
            old, new = before.get(collection, {}), state.get(collection, {})
            for key in old.keys() | new.keys():
                if old.get(key) != new.get(key):
                    for record in (old.get(key),new.get(key)):
                        if record: changed_items.add(record['batch_id'])
        touched = (changed_items | (set(state.get('work_items', {})) - material.keys())) & touched
    def digest(value):
        return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()
    for item in touched:
        notes=[]
        for n in state['notes'].values():
            if n['batch_id'] != item or n.get('status') == 'discarded': continue
            row={k:n.get(k) for k in ('id','batch_id','shift_id','revision','transcripts','claim_ids','source_review_pending','cancelled_reason','carry_forward')}
            row['completion']='done' if n.get('status')=='processed' else 'unfinished'
            notes.append(row)
        claims=[c for c in state['claims'].values() if c['batch_id']==item]
        material[item]=digest({'item':state.get('work_items',{}).get(item),'notes':sorted(notes,key=lambda n:n['id']),'claims':sorted(claims,key=lambda c:c['id']),
                               'quantity_exception':state.get('quantity_exceptions',{}).get(item)})
    def signature_for(source,sid):
        items=shift_items(source,sid)
        members=sorted((a for a in source.get('assignments',{}).values() if a['shift_id']==sid),key=lambda a:a['id'])
        return digest({'items':{i:source.get('material_items',{}).get(i) for i in sorted(items)},'members':members,
                       'incoming_shift_id':source.get('handovers',{}).get(sid,{}).get('incoming_shift_id')})
    for sid, shift in state.get('shift_occurrences', {}).items():
        h=state.setdefault('handovers',{}).setdefault(sid,{'id':sid,'version':0})
        signature=signature_for(state,sid)
        if h.get('signature')!=signature:
            # SQL row ordering is not a material change. Normalize an older
            # order-dependent signature without invalidating an existing receipt.
            same_before=before is not None and sid in before.get('handovers',{}) and signature_for(before,sid)==signature
            h.update(version=h['version']+(0 if same_before else 1),signature=signature)

def check_handover_version(state, shift_id, expected_version):
    version = state.get('handovers', {}).get(shift_id, {}).get('version') if shift_id != 'shift-B' else state['version']
    if version is None or expected_version != version:
        raise Conflict('This handover changed. Refresh it before confirming.')
