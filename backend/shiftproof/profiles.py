"""Versioned industry contracts. Preview profiles cannot process operational records."""
PROFILES = {
 'manufacturing': {'name':'Manufacturing','item':'Batch','status':'available','properties':{'packing':['complete','pending'],'quality':['cleared','pending'],'dispatch':['ready','pending'],'quantity':[], 'task':[]}},
 'maintenance': {'name':'Equipment maintenance','item':'Asset','status':'available','properties':{'operating':['running','stopped'],'fault':['open','resolved'],'repair':['temporary','verified','pending'],'task':[]}},
 'warehousing': {'name':'Warehousing','item':'Order','status':'available','properties':{'packing':['complete','pending'],'documents':['verified','pending'],'dispatch':['ready','pending'],'quantity':[], 'task':[]}},
 'quality_assurance': {'name':'Quality assurance','item':'Inspection','status':'preview','properties':{}},
 'food_processing': {'name':'Food processing','item':'Batch','status':'preview','properties':{}},
 'construction': {'name':'Construction','item':'Work area','status':'preview','properties':{}},
 'healthcare': {'name':'Healthcare','item':'Handover','status':'preview','properties':{}},
 'facilities': {'name':'Facility management','item':'Asset','status':'preview','properties':{}},
}
for key, value in PROFILES.items(): value.update(id=key, version=1)

def profile(state):
    return PROFILES[state.get('profile', 'manufacturing')]

def work_items(state):
    from .engine import BATCHES
    return list(state['work_items'].values()) if 'work_items' in state else BATCHES

def validate_claims(claims, profile_id):
    allowed = PROFILES[profile_id]['properties']
    for c in claims:
        if c.property not in allowed or (allowed[c.property] and c.value not in allowed[c.property]):
            raise ValueError('Claim is not supported by the selected industry workflow')

def review_protected(claim):
    return (claim['property'], claim['value']) in {('quality','pending'),('documents','pending'),('fault','open'),('repair','pending')}

def clearance(claim):
    return (claim['property'], claim['value']) in {('quality','cleared'),('documents','verified'),('fault','resolved'),('repair','verified')}

def industry_view(state, item):
    from .engine import active_claims
    p = profile(state)
    claims = active_claims(state, item['id'])
    actual = [c for c in claims if c['modality']=='actual' and not c.get('batch_mismatch')]
    reviewed = [c for c in actual if c['status']=='confirmed' and not c.get('source_review_pending')]
    conflicts=[]; reasons=[]
    def reason(code,text,refs,action,owner='Authorized reviewer'):
        reasons.append(dict(code=code,text=text,claim_ids=[c['id'] for c in refs],note_ids=list(dict.fromkeys(c['note_id'] for c in refs)),next_action=action,owner=owner))
    for prop in p['properties']:
        peers=[c for c in actual if c['property']==prop]
        if prop!='task' and len({str(c['value']) for c in peers})>1:
            conflicts.append(dict(id=f'{item["id"]}:{prop}',type=prop,message=f'Conflicting {prop} reports need review',claim_ids=[c['id'] for c in peers]))
            reason('conflict',f'Conflicting {prop} reports',peers,'Compare sources and record an explicit resolution')
    holds=[c for c in actual if review_protected(c)]
    for c in holds: reason('hold',f'{c["property"]}: {c["value"]}',[c],'Record an authorized verification; preserve the original report')
    prerequisites = [('operating','running'),('repair','verified')] if p['id']=='maintenance' else [('packing','complete'),('documents','verified')]
    complete=True
    for prop, value in prerequisites:
        if not any(c['property']==prop and c['value']==value for c in reviewed):
            complete=False
            role = 'Authorized reviewer' if clearance({'property':prop,'value':value}) else 'Shift supervisor'
            reason('unverified',f'{prop.title()} {value} is not human-reviewed',[c for c in claims if c['property']==prop],f'Obtain and review a sourced {prop} report',role)
    pending=[c for c in actual if (c['property'],c['value']) in {('packing','pending'),('dispatch','pending'),('operating','stopped'),('repair','temporary')}]
    for c in pending: reason('pending',f'{c["property"]}: {c["value"]}',[c],'Verify outstanding work',c.get('owner'))
    for c in claims:
        if c.get('batch_mismatch'): reason('identifier','Reported identifier does not match selected work item',[c],'Confirm the correct work item')
        if c['modality']!='actual': reason('condition','Planned or conditional work remains unverified',[c],'Verify the reported condition')
        if c['status'] in ('draft','disputed'): reason('unreviewed','Reported - needs review',[c],'Review this report','Shift supervisor')
        if c.get('source_review_pending'): reason('source_revision','The source transcript changed; earlier interpretations need explicit review',[c],'Review the revised transcript and original evidence','Shift supervisor')
    tasks=[dict(id=c['id'],title=str(c['value']),owner=c.get('assigned_owner') or c.get('owner'),
                owner_id=c.get('assigned_owner_id'),assigned_owner_id=c.get('assigned_owner_id'),completion_note_id=c.get('completion_note_id'),
                source_review_pending=c.get('source_review_pending',False) or c.get('completion_review_pending',False),status=c.get('task_status','open'),claim_ids=[c['id']]) for c in actual if c['property']=='task']
    for task in tasks:
        if task['status']!='completed': reason('task',task['title'],[c for c in claims if c['id']==task['id']],task['title'],task['owner'])
    unfinished=[n for n in state['notes'].values() if n['batch_id']==item['id'] and n['status'] not in ('processed','discarded')]
    for n in unfinished: reasons.append(dict(code='processing',text='Saved note needs processing or interpretation',claim_ids=[],note_ids=[n['id']],next_action='Finish reviewing the saved transcript',owner='Shift supervisor'))
    ready=[c for c in actual if c['property']=='dispatch' and c['value']=='ready']
    if ready and (holds or not complete or pending):
        conflicts.append(dict(id=f'{item["id"]}:readiness',type='unmet_condition',message='Reported ready has unresolved prerequisites',claim_ids=[c['id'] for c in ready+holds+pending]))
    status='hold' if holds else 'conflict' if conflicts else 'verified' if complete and not reasons else 'review' if claims or unfinished else 'unknown'
    question=None
    if holds:
        prop=holds[0]['property']
        subject={'fault':'खराबी ठीक होने','repair':'मरम्मत पूरी होने','documents':'दस्तावेज़ों की जाँच','quality':'गुणवत्ता जाँच'}.get(prop,'काम पूरा होने')
        question=dict(id=f'{item["id"]}:{prop}',text=f'{item["id"]}: {subject} की पुष्टि हुई है, या काम अभी बाकी है?',claim_ids=[c['id'] for c in holds],type=prop)
    elif reasons:
        first=reasons[0]
        prompts={'conflict':'अलग-अलग रिपोर्ट मिली हैं। जाँच करके सही स्थिति बताएं।',
                 'identifier':'आप किस काम या सामान की बात कर रहे हैं? सही पहचान बताएं।',
                 'condition':'क्या बताई गई शर्त पूरी हो चुकी है? जाँच करके बताएं।',
                 'source_revision':'सुधारे गए बयान के अनुसार अभी सही स्थिति क्या है?',
                 'task':'यह काम पूरा हुआ है, या अभी बाकी है?',
                 'unreviewed':'क्या इस रिपोर्ट की जाँच हुई है? अभी की सही स्थिति बताएं।'}
        question=dict(id=f'{item["id"]}:verification',text=f'{item["id"]}: '+prompts.get(first['code'],'बताया गया काम पूरा हुआ है, या अभी बाकी है? जाँच करके बताएं।'),claim_ids=first['claim_ids'],type='verification')
    from .engine import clarification_progress
    question=clarification_progress(state,item['id'],question)
    quantities=[c['value'] for c in reviewed if c['property']=='quantity']
    return {**item,'status':status,'claims':claims,'claim_history':[c for c in state['claims'].values() if c['batch_id']==item['id']], 'readiness_reasons':reasons,'conflicts':conflicts,'clarification':question,'tasks':tasks,'quantity':quantities[0] if quantities and len(set(quantities))==1 and not any(c['type']=='quantity' for c in conflicts) else None,'packing':'complete' if any(c['property']=='packing' and c['value']=='complete' for c in reviewed) else 'unverified','quality':'pending' if holds else 'unverified','unreviewed_count':sum(c['status'] in ('draft','disputed') or c.get('source_review_pending',False) for c in claims),'pending_note_count':len(unfinished),'evidence_ids':list(dict.fromkeys(c['note_id'] for c in claims))}
