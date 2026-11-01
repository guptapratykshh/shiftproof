"""One evidence-linked summary for display and spoken handover."""
TERMS={
 'packing':('पैकिंग','Packing'), 'quality':('गुणवत्ता','Quality'), 'documents':('भेजने के दस्तावेज़','Dispatch documents'),
 'dispatch':('भेजने की तैयारी','Dispatch readiness'),'quantity':('गिनती','Quantity'),'operating':('मशीन की स्थिति','Operating status'),
 'fault':('खराबी','Fault'),'repair':('मरम्मत','Repair'),'task':('काम','Task')}
VALUES={'complete':('पूरी','complete'),'pending':('बाकी','pending'),'cleared':('मंज़ूर','cleared'),'verified':('जाँचे गए','verified'),
 'ready':('तैयार','ready'),'running':('चल रही','running'),'stopped':('रुकी हुई','stopped'),'open':('बाकी','open'),'resolved':('ठीक','resolved'),'temporary':('अस्थायी','temporary')}

def build(snapshot, org_id):
    items=[]
    for batch in snapshot['batches']:
        bid=batch['id']
        for c in batch['claims']:
            if c['status'] in ('rejected','superseded'):continue
            checked=c['status']=='confirmed' and not c.get('source_review_pending')
            hi,en=TERMS.get(c['property'],('काम','Work'))
            vh,ve=VALUES.get(str(c['value']),(str(c['value']),str(c['value'])))
            qualifier=('आगे की योजना: ','Planned: ') if c['modality']=='planned' else ('शर्त पूरी होने पर: ','Conditional: ') if c['modality']=='conditional' else ('','')
            text={'hi':f'{qualifier[0]}{hi}: {vh}। '+('रिपोर्ट की जाँच हो गई है।' if checked else 'बताया गया है; जाँच बाकी है।'),
                  'en':f'{qualifier[1]}{en}: {ve}. '+('Report checked.' if checked else 'Reported; review needed.')}
            items.append({'work_item_id':bid,'kind':'checked' if checked else 'reported','text':text,'claim_ids':[c['id']],'note_ids':[c['note_id']]})
        seen=set()
        for r in batch['readiness_reasons']:
            code=r['code']
            if code=='unreviewed':continue # Already explained with each reported fact.
            key=(code,r['text'])
            if key in seen:continue
            seen.add(key)
            prop=next((p for p in TERMS if r['text'].lower().startswith(p)),None)
            if code in ('unverified','packing_unknown','quality_unknown'):
                prop=prop or ('packing' if code=='packing_unknown' else 'quality' if code=='quality_unknown' else None)
                h,e=TERMS.get(prop,('इस काम','This work'))
                hi=f'{h} की जाँच अभी बाकी है।';en=f'{e} still needs verification.'
            else:
                hi={'processing':'सहेजी हुई रिपोर्ट समझने में सुपरवाइज़र की मदद चाहिए।','pending_notes':'सहेजी हुई रिपोर्ट समझने में सुपरवाइज़र की मदद चाहिए।','conflict':'अलग-अलग बातें बताई गई हैं। सही स्थिति की जाँच करें।','hold':'रोक अभी बाकी है। अधिकृत जाँचकर्ता पुष्टि करें।','quality_hold':'गुणवत्ता की रोक अभी बाकी है।','source_revision':'बयान बदला गया है। दोबारा जाँच चाहिए।','identifier':'काम की पहचान साफ़ नहीं है।','condition':'शर्त या आगे के काम की पुष्टि बाकी है।','task':'एक काम अभी बाकी है।','pending':'काम अभी बाकी है।'}.get(code,'एक ज़रूरी जाँच अभी बाकी है।')
                en=r['text']
            owner=r.get('owner') or 'Shift supervisor'
            oh={'Shift supervisor':'सुपरवाइज़र','Authorized reviewer':'अधिकृत जाँचकर्ता','Quality reviewer':'गुणवत्ता जाँचकर्ता'}.get(owner,owner)
            items.append({'work_item_id':bid,'kind':'outstanding','text':{'hi':hi+f' ज़िम्मेदारी: {oh}।','en':en+f' Responsible: {owner}.'},'claim_ids':r.get('claim_ids',[]),'note_ids':r.get('note_ids',[]),'next_action':r.get('next_action'),'owner':owner})
    return {'organization_id':org_id,'shift_id':snapshot['shift_id'],'version':snapshot['version'],'items':items}

def speech_text(summary, batch_id, language):
    groups={}
    for row in summary['items']:
        if batch_id=='all' or row['work_item_id']==batch_id:
            groups.setdefault(row['work_item_id'],[]).append(row['text'][language])
    return ' '.join(item+'. '+' '.join(texts) for item,texts in groups.items())
