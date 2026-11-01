"""Generate transparent synthetic contract scenarios, not independently annotated field data."""
import json
from pathlib import Path

ROOT = Path(__file__).parent

def note(text, claims=None, role='operator', reviewed=True):
    return {'text': text, 'role': role, 'reviewed': reviewed, 'claims': claims or []}

def claim(prop, value, text, **extra):
    return {'property': prop, 'value': value, 'excerpt': text, 'modality': 'actual', 'condition': None, 'reported_at': None, 'owner': None, 'negated': False, **extra}

def build():
    cases=[]
    for variant in range(6):
        low,high=15+variant,50+variant
        ready=note('Packing complete hai.',[claim('packing','complete','Packing complete hai.')])
        clear=note('Quality inspection cleared hai.',[claim('quality','cleared','Quality inspection cleared hai.')],role='quality')
        hold=note('Quality check abhi pending hai.',[claim('quality','pending','Quality check abhi pending hai.')],role='quality')
        qlow=note(f'{low} cartons complete hue hain.',[claim('quantity',low,f'{low} cartons complete hue hain.')])
        qhigh=note(f'Correction: {low} nahi, {high} cartons hue hain.',[claim('quantity',high,f'Correction: {low} nahi, {high} cartons hue hain.')])
        casespecs=[
            ('clean_completion',[ready,clear,qlow], 'verified',False,low),
            ('quality_hold',[ready,hold,note('Dispatch ready hai.',[claim('dispatch','ready','Dispatch ready hai.')],role='supervisor')],'hold',True,None),
            ('explicit_correction',[qlow,qhigh], 'review',False,high),
            ('conditional_completion',[ready,clear,note('Labels verify hone ke baad dispatch ready hoga.',[claim('dispatch','ready','Labels verify hone ke baad dispatch ready hoga.',modality='conditional',condition='Labels must be verified')])],'review',False,None),
            ('negation',[note('Packing complete nahi hai.',[claim('packing','pending','Packing complete nahi hai.',negated=True)]),clear], 'review',False,None),
            ('late_upload',[qhigh,qlow], 'review',False,high),
            ('missing_owner',[note('Carton labels dobara check karne hain.',[claim('task','Recheck carton labels','Carton labels dobara check karne hain.')])], 'review',False,None),
            ('batch_mismatch',[note('Batch atharah packing complete hai.',[claim('packing','complete','Batch atharah packing complete hai.',batch_mismatch=True)],reviewed=False)],'conflict',True,None),
            ('conflicting_counts',[qlow,note(f'{high} cartons verified hain.',[claim('quantity',high,f'{high} cartons verified hain.')],role='supervisor')],'conflict',True,None),
            ('unsupported_question',[note('Aaj mausam accha hai.')],'unknown',False,None),
        ]
        for category,notes,status,conflict,quantity in casespecs:
            notes=json.loads(json.dumps(notes))
            if category=='explicit_correction':
                notes[0]['claims'][0]['superseded']=True
                notes[1]['claims'][0]['supersedes_index']='0:0'
            if category=='late_upload':
                notes[0]['claims'][0]['reported_at']='2026-10-07T12:00:00+00:00'
                notes[1]['claims'][0]['reported_at']='2026-10-07T09:00:00+00:00'
                notes[0]['text']+=' Reported time: 2026-10-07T12:00:00+00:00.'
                notes[1]['text']+=' Reported time: 2026-10-07T09:00:00+00:00.'
            while len(notes)<4:
                notes.append(note(['Shift note received.','Handover record mein note rakho.','Agli team ko update milega.'][len(notes)%3]))
            ident=f'SP-{len(cases)+1:03d}'
            cases.append({'id':ident,'split':'development' if variant<2 else 'held_out','category':category,'batch_id':'B-17','notes':notes,'question':'What is the weather tomorrow?' if category=='unsupported_question' else 'What is pending?','expected':{'status':status,'conflict':conflict,'quantity':quantity,'abstain':category in ('unsupported_question','negation','late_upload','explicit_correction')}})
    document={'version':1,'provenance':'Template-generated fictional contract scenarios. Gold claims authored with the implementation; not independently annotated. Variants within a category are related, so the held_out split is a smoke-test partition, not evidence of out-of-distribution generalization.','scenarios':cases}
    (ROOT/'scenarios.json').write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n')
    return document

if __name__=='__main__':
    document=build();print(f'Wrote {len(document["scenarios"])} synthetic scenarios to evaluation/scenarios.json')
