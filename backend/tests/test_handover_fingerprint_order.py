import copy
import hashlib
import json

from shiftproof.pilot_scope import sync_handovers


def fixture():
    return {'work_items':{'item':{'id':'item','team_id':'team','location_id':'location'}}, 'notes':{
        'z':{'id':'z','batch_id':'item','status':'processed'},
        'a':{'id':'a','batch_id':'item','status':'processed'}},
        'claims':{'z':{'id':'z','batch_id':'item','value':'pending'},'a':{'id':'a','batch_id':'item','value':'complete'}},
        'shift_occurrences':{'shift':{'id':'shift','team_id':'team','location_id':'location'}},
        'assignments':{'z':{'id':'z','shift_id':'shift','user_id':'z','work_item_ids':['item']},
                       'a':{'id':'a','shift_id':'shift','user_id':'a','work_item_ids':['item']}}}


def test_database_row_order_does_not_change_material_version():
    state=fixture();sync_handovers(state)
    original=copy.deepcopy(state)
    for collection in ('notes','claims','assignments'):
        state[collection]=dict(reversed(list(state[collection].items())))
    sync_handovers(state)  # Also verify a full fingerprint rebuild.
    assert state['handovers']==original['handovers']
    assert state['material_items']==original['material_items']


def test_old_assignment_order_signature_normalizes_without_invalidating_receipt():
    state=fixture();sync_handovers(state)
    old={'items':state['material_items'],'members':list(state['assignments'].values()),'incoming_shift_id':None}
    state['handovers']['shift']['signature']=hashlib.sha256(json.dumps(old,sort_keys=True,default=str).encode()).hexdigest()
    before=copy.deepcopy(state)
    state['ack_audio']={'receipt':{'actor_id':'a'}}
    sync_handovers(state,before)
    assert state['handovers']['shift']['version']==before['handovers']['shift']['version']
    assert state['handovers']['shift']['signature']!=before['handovers']['shift']['signature']
    before=copy.deepcopy(state)
    state['assignments']['a']['user_id']='replacement'
    sync_handovers(state,before)
    assert state['handovers']['shift']['version']==before['handovers']['shift']['version']+1
