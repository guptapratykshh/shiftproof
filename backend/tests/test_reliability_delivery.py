import copy
import importlib.util
import json
from pathlib import Path
from datetime import datetime, timezone
import httpx
import pytest
from fastapi.testclient import TestClient
from shiftproof import providers, service
from shiftproof.api import app
from shiftproof.fixtures import ACTORS as DEMO_ACTORS
from shiftproof.config import settings
from shiftproof.diagnostics import save_check, last_check
from shiftproof.engine import answer_question, handover
from shiftproof.models import NoteCreate, ResolveRequest
from shiftproof.repository import Conflict
from test_handover import add, confirm, batch

ROOT=Path(__file__).resolve().parents[2]


def setup_gemini(monkeypatch):
    monkeypatch.setenv('EXTRACTION_PROVIDER','gemini');monkeypatch.setenv('GEMINI_API_KEY','test-key');monkeypatch.setenv('GEMINI_FREE_TIER_CONFIRMED','true')
    settings.cache_clear();monkeypatch.setattr(providers.time,'sleep',lambda _:None)


def response(status=200, raw=None):
    return httpx.Response(status,request=httpx.Request('POST','https://generativelanguage.googleapis.com/v1beta/interactions'),json={'status':'completed','id':'live-test','output_text':json.dumps(raw if raw is not None else {'claims':[]})})


@pytest.mark.parametrize('sequence,category',[
    ([503,'valid'],None),(['timeout','valid'],None),
    ([503,'invalid'],'invalid_output'),(['invalid',503],'provider_unavailable'),
    ([429],'quota_exhausted'),([403],'authorization'),([503,503],'provider_unavailable'),
])
def test_single_shared_retry_budget(monkeypatch,sequence,category):
    setup_gemini(monkeypatch);calls=[];reserved=[]
    def post(*a,**kw):
        step=sequence[len(calls)];calls.append(kw)
        if step=='timeout':raise httpx.ReadTimeout('test timeout')
        if step=='invalid':return response(raw={'claims':[{'property':'quality','value':'cleared','excerpt':'invented'}]})
        return response(step) if isinstance(step,int) else response()
    monkeypatch.setattr(providers.httpx,'post',post)
    if category:
        with pytest.raises(providers.ExtractionUnavailable) as exc:providers.extract('hello','B-17',lambda:reserved.append(1))
        assert exc.value.category==category
    else: assert not providers.extract('hello','B-17',lambda:reserved.append(1))[0].claims
    assert len(calls)==len(reserved)==len(sequence)


def test_provider_check_bound_to_key_model_prompt_and_no_network(monkeypatch,tmp_path):
    setup_gemini(monkeypatch);monkeypatch.setenv('PROVIDER_CHECK_PATH',str(tmp_path/'checks.json'))
    save_check({'model':settings().gemini_model,'status':'passed','generated_at':'2026-10-15T12:00:00+00:00'})
    monkeypatch.setattr(providers.httpx,'post',lambda *a,**k:pytest.fail('Config must not call provider'))
    assert TestClient(app).get('/config').json()['extraction_check']['status']=='passed'
    settings().gemini_key='different-key'; assert last_check()['status']=='not_tested'
    settings().gemini_key='test-key';settings().gemini_model='another-model';assert last_check()['status']=='not_tested'


def test_stale_clarification_has_no_new_note_or_usage(repo):
    service.seed(repo);before=copy.deepcopy(repo.load())
    body=NoteCreate(batch_id='B-17',recorded_at=datetime.now(timezone.utc),idempotency_key='stale-test-note',clarification_ref='B-17:quality',clarification_version=before['version']-1)
    with pytest.raises(Conflict):service.create_note(repo,body,DEMO_ACTORS['operator'])
    assert repo.load()==before
    body.clarification_version=before['version']
    note=service.create_note(repo,body,DEMO_ACTORS['operator'])
    assert note['clarification_context']['version']==before['version']
    assert service.create_note(repo,body,DEMO_ACTORS['operator'])['id']==note['id']


@pytest.mark.parametrize('case',json.loads((ROOT/'evaluation/answer_checks.json').read_text())['cases'],ids=lambda c:c['id'])
def test_development_question_suite(repo,case):
    service.seed(repo);result=answer_question(repo.load(),'B-17',case['question'])
    assert result['intent']==case['intent']
    assert result['abstained']==(case['intent'] is None)
    for item in result['items']:
        assert all(cid in repo.load()['claims'] for cid in item['claim_ids'])
        assert all(nid in repo.load()['notes'] for nid in item['note_ids'])
        assert set(repo.load()['claims'][cid]['note_id'] for cid in item['claim_ids']) <= set(item['note_ids'])


def test_history_lists_superseded_and_current_and_later_review(repo):
    old=add(repo,'quantity-15')[0];confirm(repo,old)
    prior=repo.load()['version']
    new=add(repo,'quantity-50')[0];confirm(repo,new,supersedes=[old['id']])
    answer=answer_question(repo.load(),'B-17','What changed?')
    assert 'Recorded history' in answer['answer'] and answer['comparison_snapshot'] is None
    assert {i['kind'] for i in answer['items']}=={'current','superseded'}
    with repo.transaction() as state:state['snapshots']['previous-shift']={'version':prior}
    answer=answer_question(repo.load(),'B-17','What changed?')
    # The newer claim references the old source via its explicit supersession history.
    assert answer['comparison_snapshot']['version']==prior
    assert new['id'] in answer['claim_ids']


def test_seal_task_completion_does_not_release_hold(repo,monkeypatch):
    text='Seal kharab hai. Quality inspection pending hai. Seal inspect karna hai.'
    actor=DEMO_ACTORS['operator']
    note=service.create_note(repo,NoteCreate(batch_id='B-17',recorded_at=datetime.now(timezone.utc),idempotency_key='seal-demo'),actor)
    service.submit_transcript(repo,note['id'],text,actor)
    raw={'claims':[{'property':'quality','value':'pending','excerpt':'Quality inspection pending hai'}, {'property':'task','value':'Inspect carton seals','excerpt':'Seal inspect karna hai','owner':'Quality reviewer'}]}
    monkeypatch.setattr(providers,'extract',lambda *a: (providers.validate_extraction(raw,text),'mock-extraction'))
    service.process_note(repo,note['id'])
    for c in list(repo.load()['claims'].values()):confirm(repo,c)
    task=next(c for c in repo.load()['claims'].values() if c['property']=='task')
    from shiftproof.models import TaskUpdate
    service.update_task(repo,task['id'],TaskUpdate(expected_version=repo.load()['version'],action='complete',reason='Inspection performed; awaiting quality decision'),DEMO_ACTORS['quality'])
    assert batch(repo)['quality']=='pending'
    assert any('Quality' in i['text'] or 'quality' in i['text'] for i in answer_question(repo.load(),'B-17','What is pending?')['items'])


def test_rest_model_output_steps_not_sdk_output_text(monkeypatch):
    setup_gemini(monkeypatch)
    body={'status':'completed','steps':[{'type':'thought','signature':'opaque'}, {'type':'model_output','content':[{'type':'text','text':json.dumps({'claims':[{'property':'quality','value':'pending','excerpt':'quality pending'}]})}]}]}
    monkeypatch.setattr(providers.httpx,'post',lambda *a,**kw:httpx.Response(200,request=httpx.Request('POST','https://generativelanguage.googleapis.com/v1beta/interactions'),json=body))
    result,_=providers.extract('quality pending','B-17')
    assert result.claims[0].value=='pending'
