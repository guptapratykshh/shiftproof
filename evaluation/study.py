"""Prepare blind annotation, consented recording assignments and usability sheets."""
import argparse
import csv
import json
import hashlib
import secrets
import statistics
import math
from pathlib import Path
from language_run import load_cases

ROOT=Path(__file__).parent


def prepare():
    cases,digest=load_cases()
    output=ROOT/'study'; output.mkdir(exist_ok=True)
    if any((output / name).exists() for name in ('blind-annotations.jsonl', 'usability.csv')):
        raise SystemExit('Study sheets already exist; preserving labels and participant results')
    # Do not include expected values, model predictions or implementation labels.
    with (output/'blind-annotations.jsonl').open('w') as f:
        for c in cases:
            item={'case_id':c['id'],'split':c['split'],'batch_id':c['batch_id'],'question':c['question'],
                  'notes':[{k:n[k] for k in ('id','text','role','recorded_at','received_at','review','supersedes_note','clarification')} for n in c['notes']],
                  'reviewer_id':None,'state':None,'quantity':None,'conflict':None,'answerable':None,'claims':[],
                  'disagreement_reason':None,'adjudicated_label':None}
            f.write(json.dumps(item,ensure_ascii=False)+'\n')
    selected=[c for c in cases if c['split']=='development'][:8]+[c for c in cases if c['split']=='held_out'][:12]
    manifest={'status':'not_collected','dataset_sha256':digest,'target_scenarios':20,'target_speakers':2,
              'provenance':'Consenting speakers read fictional scripts. Different speakers across splits; small controlled study, not factory validation.',
              'assignments':[{'scenario_id':c['id'],'split':c['split'],'speaker_id':'speaker-a' if c['split']=='development' else 'speaker-b',
                              'notes':[{'note_id':n['id'],'text':n['text']} for n in c['notes']]} for c in selected], 'recordings':[]}
    path=ROOT/'audio_manifest.json'
    if path.exists() and json.loads(path.read_text()).get('recordings'): raise SystemExit('Existing recordings retained; refusing to overwrite audio manifest')
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    with (output/'usability.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['participant_id','background','task','case_id','condition','order','elapsed_seconds','missed_items','mistaken_clearances','corrections','notes'])
        for person,conditions in [('speaker-a',['raw_transcripts','shiftproof']),('speaker-b',['shiftproof','raw_transcripts'])]:
            for order,condition in enumerate(conditions,1):
                w.writerow([person,'pending','find_pending_work','LANG-021' if order==1 else 'LANG-027',condition,order,'','','','',''])
            for order,condition in enumerate(['voice','manual_claim_form'] if person=='speaker-a' else ['manual_claim_form','voice'],1):
                w.writerow([person,'pending','capture_update','LANG-001' if order==1 else 'LANG-016',condition,order,'','','','',''])
    print('Prepared blind labels, 20 recording assignments and counterbalanced usability sheets. No participation or consent is claimed.')


def payload_hash(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def semantic_sheet(run_dir, mapping_path=None, packet_name="semantic-review.jsonl"):
    folder=Path(run_dir)
    rows=json.loads((folder/'cases.json').read_text())
    sources=json.loads((folder/'source-inputs.json').read_text())
    if Path(packet_name).name != packet_name: raise ValueError('Packet must be a filename')
    path=folder/packet_name
    mapping_path=Path(mapping_path) if mapping_path else ROOT.parent/'.local/study-mappings'/f'{folder.name}.json'
    if path.exists() or mapping_path.exists(): raise ValueError('Review packet or mapping already exists; preserving annotations')
    entries=[]; mapping={}
    for cid,row in rows.items():
        for variant in ('shiftproof','baseline'):
            if not row.get(variant): continue
            result=row[variant]; source=sources[cid]; rid=secrets.token_hex(10)
            payload={'question':source['question'],'selected_batch':source['selected_batch'],
                     'notes':source['notes'],'review_events':source['review_events'],
                     'clarification_contexts':source.get('clarification_contexts',{}),
                     'answer':result['answer'],'abstained':result['abstained'],
                     'evidence_note_ids':result.get('evidence_note_ids',[])}
            entries.append({'review_id':rid,'payload':payload,'reviewer_id':None,
                            'answer_correct':None,'evidence_entails_answer':None,'reason':None})
            mapping[rid]={'case_id':cid,'system':variant,'payload_sha256':payload_hash(payload)}
    secrets.SystemRandom().shuffle(entries)
    mapping_path.parent.mkdir(parents=True,exist_ok=True)
    mapping_path.write_text(json.dumps({'manifest':json.loads((folder/'manifest.json').read_text()),'mapping':mapping},indent=2)+'\n')
    mapping_path.chmod(0o600)
    path.write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in entries))
    print(f'Blind packet: {path}. Keep the private mapping from reviewers until review ends: {mapping_path}')
    return path,mapping_path


def score_semantics(run_dir, mapping_path=None, packet_name="semantic-review.jsonl"):
    folder=Path(run_dir)
    mapping_path=Path(mapping_path) if mapping_path else ROOT.parent/'.local/study-mappings'/f'{folder.name}.json'
    mapping_doc=json.loads(mapping_path.read_text())
    if mapping_doc['manifest']!=json.loads((folder/'manifest.json').read_text()): raise ValueError('Mapping belongs to another run')
    mapping=mapping_doc['mapping']
    if Path(packet_name).name != packet_name: raise ValueError('Packet must be a filename')
    entries=[json.loads(line) for line in (folder/packet_name).read_text().splitlines() if line.strip()]
    report=json.loads((folder/'report.json').read_text());seen=set();judgments=[]
    for e in entries:
        rid=e['review_id']
        if rid in seen or rid not in mapping: raise ValueError('Invalid/duplicate review ID')
        seen.add(rid)
        if payload_hash(e['payload'])!=mapping[rid]['payload_sha256']: raise ValueError('Review source/answer was altered')
        fields=(e.get('answer_correct'),e.get('evidence_entails_answer'))
        if any(v is not None for v in fields):
            if not all(type(v) is bool for v in fields) or not e.get('reviewer_id') or not e.get('reason'):
                raise ValueError('Completed reviews need both booleans, reviewer and reason')
            judgments.append({**e,**mapping[rid]})
    if seen!=set(mapping): raise ValueError('Review packet entries were removed; retain pending entries')
    for variant in ('shiftproof','baseline'):
        judged=[e for e in judgments if e['system']==variant];total=sum(m['system']==variant for m in mapping.values())
        report['metrics'][variant].update(answer_correctness=sum(e['answer_correct'] for e in judged)/len(judged) if judged else None,
             semantic_evidence_correctness=sum(e['evidence_entails_answer'] for e in judged)/len(judged) if judged else None,
             answer_correctness_status='human_reviewed_subset' if judged else 'pending',semantic_review_count=len(judged),
             semantic_review_requested=total,semantic_review_pending=total-len(judged))
    (folder/'report-with-semantic-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('Saved separate semantic report. Blinding hides system labels, but answer style may still reveal a system.')
    return report


RATIOS={
    'missed_task_rate':('missed_items','required_items'),
    'false_ready_rate':('incorrect_ready_decisions','evaluated_decisions'),
    'correction_rate':('claims_needing_correction','claims_reviewed'),
    'evidence_traceability':('correct_sources_found','source_tasks'),
    'acknowledgement_completeness':('latest_acknowledgements','ack_checkpoints'),
}
TIMES=('capture_seconds','understanding_seconds','source_finding_seconds')
COUNTS=tuple(dict.fromkeys([v for pair in RATIOS.values() for v in pair]+['transcript_edits']))
FIELDS=['participant_id','background','task','case_id','condition','order','status',*COUNTS,*TIMES,'notes']


def usability_template(path):
    path=Path(path)
    if path.exists(): raise ValueError('Worksheet exists; refusing to overwrite participant measurements')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader()
        for person,conditions in [('speaker-a',['raw_transcripts','shiftproof']),('speaker-b',['shiftproof','raw_transcripts'])]:
            pairs=[('find_pending_work',['LANG-021','LANG-027'],conditions),
                   ('capture_update',['LANG-001','LANG-016'],['voice','manual_claim_form'] if person=='speaker-a' else ['manual_claim_form','voice'])]
            for task,cases,sequence in pairs:
                for i,condition in enumerate(sequence):
                    w.writerow(dict(participant_id=person,task=task,case_id=cases[i],condition=condition,order=i+1,status='pending'))
    return path


def score_usability(path, output):
    with Path(path).open(newline='') as f: rows=list(csv.DictReader(f))
    seen=set();measured=[]
    for row in rows:
        key=tuple(row.get(k) for k in ('participant_id','task','case_id','condition','order'))
        if not all(key) or key in seen: raise ValueError('Missing or duplicate assignment identity')
        seen.add(key)
        if row.get('status') not in ('pending','completed','failed'): raise ValueError('Each assignment needs pending/completed/failed status')
        if row['status']=='pending': continue
        if not row.get('background'): raise ValueError('Measured sessions require participant background')
        values=dict(row)
        for field in COUNTS+TIMES:
            raw=row.get(field,'')
            if not raw.strip(): values[field]=None;continue
            value=float(raw)
            if not math.isfinite(value) or value<0 or (field in COUNTS and not value.is_integer()):
                raise ValueError(f'Invalid {field}')
            values[field]=int(value) if field in COUNTS else value
        for numerator,denominator in RATIOS.values():
            a,b=values[numerator],values[denominator]
            if (a is None)!=(b is None) or (a is not None and a>b): raise ValueError(f'Invalid pair {numerator}/{denominator}')
        measured.append(values)
    def summarize(group):
        result={'measured_assignments':len(group),'failed_assignments':sum(r['status']=='failed' for r in group)}
        for name,(a,b) in RATIOS.items():
            valid=[r for r in group if r[a] is not None];n=sum(r[a] for r in valid);d=sum(r[b] for r in valid)
            result[name]={'numerator':n,'denominator':d,'value':n/d if d else None,'assignments_with_measurements':len(valid),'unmeasured_assignments':len(group)-len(valid)}
        for field in TIMES:
            vals=[r[field] for r in group if r[field] is not None]
            result[field]={'count':len(vals),'median':statistics.median(vals) if vals else None,'values':vals}
        edits=[r['transcript_edits'] for r in group if r['transcript_edits'] is not None]
        result['transcript_edits']={'total':sum(edits) if edits else None,'assignments':len(edits)}
        return result
    report={'status':'pending' if not measured else 'partial' if len(measured)!=len(rows) else 'completed',
            'assigned':len(rows),'pending':sum(r['status']=='pending' for r in rows),'overall':summarize(measured),
            'by_condition':{v:summarize([r for r in measured if r['condition']==v]) for v in sorted({r['condition'] for r in rows})},
            'by_participant':{v:summarize([r for r in measured if r['participant_id']==v]) for v in sorted({r['participant_id'] for r in rows})},
            'limitations':['Descriptive two-person controlled exercise, not representative factory validation.',
                          'Blank measurements remain unmeasured; failed assignments remain in the report.',
                          'Capture, understanding and source-finding times are reported separately.']}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','semantic-sheet','score-semantics','usability-template','score-usability'])
    p.add_argument('--run-dir');p.add_argument('--mapping');p.add_argument('--packet',default='semantic-review.jsonl');p.add_argument('--input');p.add_argument('--output');a=p.parse_args()
    if a.action=='prepare':prepare()
    elif a.action=='usability-template':print(usability_template(a.output or ROOT/'study/usability-v2.csv'))
    elif a.action=='score-usability':
        if not a.input or not a.output:p.error('--input and --output are required')
        print(json.dumps(score_usability(a.input,a.output),indent=2))
    elif not a.run_dir:p.error('--run-dir is required')
    elif a.action=='semantic-sheet':semantic_sheet(a.run_dir,a.mapping,a.packet)
    else:score_semantics(a.run_dir,a.mapping,a.packet)
