import importlib.util
import json
import sys
from pathlib import Path
import pytest
from shiftproof.models import Extraction
from shiftproof.providers import ExtractionUnavailable

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'evaluation'))
from language_run import load_cases, baseline_payload, replay, score, summary, RunCache


def test_frozen_language_dataset_has_isolated_families_and_blind_baseline_inputs():
    cases,digest=load_cases()
    assert len(cases)==60
    assert sum(c['split']=='development' for c in cases)==20
    families={}
    for c in cases:
        assert families.setdefault(c['family_id'],c['split'])==c['split']
        payload=json.dumps(baseline_payload(c))
        assert 'gold_claims' not in payload and 'expected' not in payload
        assert c['annotation']['independent_review']=='pending'
    assert len(digest)==64


@pytest.mark.parametrize('case',load_cases()[0],ids=lambda c:c['id'])
def test_language_gold_labels_through_real_services(case):
    # Contract consistency only; this is deliberately not an LLM benchmark.
    result=replay(case,contract=True)
    assert score(case,result)['state_correct'],result
    assert score(case,result)['conflict_correct'],result
    assert result['evidence_valid']


def test_failed_cases_are_not_dropped_from_accuracy_or_coverage():
    cases,_=load_cases('development');cases=cases[:2]
    result={'status':cases[0]['expected']['status'],'quantity':cases[0]['expected']['quantity'],'conflict':cases[0]['expected']['conflict'],'abstained':False,'evidence_valid':True}
    metrics=summary(cases,{cases[0]['id']:{'shiftproof':result}},'shiftproof')
    assert metrics['state_accuracy']==.5
    assert metrics['requested']==2 and metrics['completed']==1
    assert metrics['answer_coverage']==.5
    assert summary(cases,{},'baseline')['state_accuracy'] is None


def test_run_cache_resumes_successes_without_network_or_mixed_schema(tmp_path,monkeypatch):
    calls=[]
    def generate(system,payload,schema,reserve_call,validator):
        reserve_call();calls.append(payload)
        return Extraction(claims=[]),'actual-request'
    monkeypatch.setattr('shiftproof.providers.generate_json',generate)
    cache=RunCache(tmp_path,2)
    validator=Extraction.model_validate
    for _ in range(2):cache('prompt',{'text':'hello'},Extraction.model_json_schema(),validator=validator)
    assert len(calls)==1 and cache.hits==1
    cache('changed prompt',{'text':'hello'},Extraction.model_json_schema(),validator=validator)
    with pytest.raises(ExtractionUnavailable):cache('third prompt',{'text':'hello'},Extraction.model_json_schema(),validator=validator)
