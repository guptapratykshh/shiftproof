import copy
import json
import csv
import sys
from pathlib import Path
import pytest
from shiftproof.config import settings
from shiftproof.providers import ExtractionUnavailable
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'evaluation'))
import language_run as runner
import study


def result(case):
    row={**case['expected'],'abstained':False,'answer':'Quality pending','evidence_note_ids':['n1'],
         'evidence_valid':True,'stage_timings':[{'origin':'replay','extraction_ms':999}],
         'pre_review_states':['hold']}
    row['ablation']={k:row[k] for k in ('status','quantity','conflict','abstained')}
    return row


def test_independent_attempts_resume_and_preserve_failures(tmp_path,monkeypatch):
    cases,digest=runner.load_cases('development');cases=cases[:1];calls=[]
    monkeypatch.setenv('EXTRACTION_PROVIDER','gemini');settings.cache_clear()
    monkeypatch.setattr(runner,'load_cases',lambda split:(cases,digest))
    def broken(*args):raise ExtractionUnavailable('malformed output','invalid_output')
    monkeypatch.setattr(runner,'replay',broken)
    monkeypatch.setattr(runner,'baseline',lambda case:(calls.append(case['id']) or result(case),'live-request'))
    first=runner.run(output=tmp_path)
    assert calls==[cases[0]['id']] and first['status']=='partial'
    assert first['pending'][0]['systems']==['shiftproof']
    history=(tmp_path/'attempts.jsonl').read_text()
    monkeypatch.setattr(runner,'replay',lambda case,contract:result(case))
    second=runner.run(output=tmp_path)
    assert second['status']=='completed' and len(calls)==1
    assert second['historical_failure_count']==1 and not second['errors']
    assert (tmp_path/'attempts.jsonl').read_text().startswith(history)
    assert second['stage_latency']['extraction_ms']['count']==0
    source=json.loads((tmp_path/'source-inputs.json').read_text())
    assert 'gold_claims' not in json.dumps(source) and 'expected' not in json.dumps(source)
    with pytest.raises(SystemExit,match='identity changed'):
        monkeypatch.setenv('GEMINI_MODEL_ID','another-model');settings.cache_clear();runner.run(output=tmp_path)


def test_shared_quota_leaves_baseline_pending(tmp_path,monkeypatch):
    cases,digest=runner.load_cases('development');cases=cases[:2]
    monkeypatch.setenv('EXTRACTION_PROVIDER','gemini');settings.cache_clear()
    monkeypatch.setattr(runner,'load_cases',lambda split:(cases,digest))
    def quota(*args):raise ExtractionUnavailable('quota','quota_exhausted')
    monkeypatch.setattr(runner,'replay',quota)
    monkeypatch.setattr(runner,'baseline',lambda *args:pytest.fail('shared quota must pause calls'))
    report=runner.run(output=tmp_path)
    assert report['status']=='blocked' and len(report['pending'])==2
    assert report['metrics']['baseline']['completed']==0


def test_baseline_uses_frozen_inputs_even_if_supplied_predictions(monkeypatch):
    case=next(c for c in runner.load_cases()[0] if c['id']=='LANG-007')
    seen=[]
    def generate(system,payload,*args,**kwargs):
        seen.append(payload)
        return runner.BaselineAnswer(status='hold',quantity=None,conflict=False,abstained=False,
            answer='pending',evidence_note_ids=['n1'],proposed_ready_before_review=False),None
    monkeypatch.setattr(runner.providers,'generate_json',generate)
    runner.baseline(case,{'leaked_prediction':'DO NOT USE'})
    assert seen[0]['clarification_contexts']==runner.frozen_contexts(case)
    assert 'leaked_prediction' not in json.dumps(seen)


def test_review_packets_are_blinded_and_tamper_checked(tmp_path):
    case=runner.load_cases()[0][0]
    (tmp_path/'cases.json').write_text(json.dumps({case['id']:{'baseline':result(case),'shiftproof':result(case)}}))
    (tmp_path/'source-inputs.json').write_text(json.dumps({case['id']:runner.baseline_payload(case)}))
    (tmp_path/'manifest.json').write_text('{}')
    (tmp_path/'report.json').write_text(json.dumps({'metrics':{'shiftproof':{},'baseline':{}}}))
    mapping=tmp_path/'private/mapping.json'
    packet,_=study.semantic_sheet(tmp_path,mapping)
    entries=[json.loads(s) for s in packet.read_text().splitlines()]
    assert len(entries)==2 and all('variant' not in e and 'system' not in e for e in entries)
    assert entries[0]['payload']['notes'] and 'gold_claims' not in packet.read_text()
    assert study.score_semantics(tmp_path,mapping)['metrics']['baseline']['semantic_review_pending']==1
    entries[0].update(reviewer_id='speaker-b',answer_correct=True,evidence_entails_answer=False,reason='Test annotation')
    packet.write_text(''.join(json.dumps(e)+'\n' for e in entries))
    report=study.score_semantics(tmp_path,mapping)
    assert sum(v['semantic_review_count'] for v in report['metrics'].values())==1
    entries[0]['payload']['answer']='altered'
    packet.write_text(''.join(json.dumps(e)+'\n' for e in entries))
    with pytest.raises(ValueError,match='altered'):study.score_semantics(tmp_path,mapping)


def test_usability_metrics_keep_pending_and_failed_assignments(tmp_path):
    path=study.usability_template(tmp_path/'input.csv')
    report=study.score_usability(path,tmp_path/'report.json')
    assert report['status']=='pending' and report['pending']==8
    assert report['overall']['missed_task_rate']['value'] is None
    with path.open() as f:rows=list(csv.DictReader(f))
    rows[0].update(status='failed',background='student',missed_items='1',required_items='4',
        incorrect_ready_decisions='1',evaluated_decisions='1',capture_seconds='12',understanding_seconds='20')
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=study.FIELDS);w.writeheader();w.writerows(rows)
    report=study.score_usability(path,tmp_path/'report.json')
    assert report['pending']==7 and report['overall']['missed_task_rate']['value']==.25
    assert report['overall']['false_ready_rate']['value']==1
    assert report['overall']['correction_rate']['value'] is None
    rows[0]['required_items']='0'
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=study.FIELDS);w.writeheader();w.writerows(rows)
    with pytest.raises(ValueError,match='Invalid pair'):study.score_usability(path,tmp_path/'report.json')


def test_monotonic_timing_separates_human_time_and_counts_failures():
    from timing import summarize
    sequence=[('capture_started',0),('recording_stopped',1000),('upload_submitted',2000),
        ('transcript_visible',4000),('extraction_submitted',14000),('result_visible',17000)]
    events=[dict(event=event,at_ms=stamp,document_id='doc',capture_id='a') for event,stamp in sequence]
    events.append(dict(event='processing_failed',at_ms=18000,document_id='doc',capture_id='b'))
    result=summarize(events)
    assert result['timings']['human_transcript_inspection_ms']['median_ms']==10000
    assert result['timings']['processing_excluding_human_ms']['median_ms']==5000
    assert result['failed_capture_attempts']==1 and result['capture_attempts']==2
    # Never subtract clocks from different page documents.
    events[-1]=dict(event='result_visible',at_ms=99,document_id='other',capture_id='a')
    assert summarize(events)['timings']['extraction_visible_ms']['count']==1


def test_resume_rejects_extraction_schema_change(tmp_path,monkeypatch):
    cases,digest=runner.load_cases('development');cases=cases[:1]
    monkeypatch.setenv('EXTRACTION_PROVIDER','gemini');settings.cache_clear()
    monkeypatch.setattr(runner,'load_cases',lambda split:(cases,digest))
    monkeypatch.setattr(runner,'replay',lambda case,contract:result(case))
    monkeypatch.setattr(runner,'baseline',lambda case:(result(case),None))
    runner.run(output=tmp_path)
    monkeypatch.setattr(runner.Extraction,'model_json_schema',lambda:{'type':'object','changed':True})
    with pytest.raises(SystemExit,match='identity changed'):runner.run(output=tmp_path)


def test_before_review_false_ready_uses_review_policy_not_final_gold():
    case=copy.deepcopy(runner.load_cases()[0][0]);case['expected']['status']='verified'
    candidate=result(case);candidate.update(status='verified',proposed_ready_before_review=True,pre_review_states=['verified'])
    rows={case['id']:{'shiftproof':candidate,'baseline':candidate}}
    # Even an ultimately released batch cannot be ready while its release is unreviewed.
    for system in ('shiftproof','baseline'):
        assert runner.summary([case],rows,system)['false_ready_before_final_review_count']==1
