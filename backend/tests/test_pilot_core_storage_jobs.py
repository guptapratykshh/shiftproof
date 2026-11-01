from audio_fixture import pcm_frames
"""Factory pilot regressions. All provider outputs are explicit test doubles."""
import copy
import io
import json
import sqlite3
import wave
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from shiftproof import durable_jobs, providers, service
from shiftproof.fixtures import ACTORS as DEMO_ACTORS
from shiftproof.config import settings
from shiftproof.engine import handover
from shiftproof.models import NoteCreate, Candidate, Extraction, ResolveRequest, TranscriptReview, TaskUpdate, AckRequest
from shiftproof.repository import Conflict, LocalRepository, empty_state


def typed(repo, text='Packing complete.'):
    n = service.create_note(repo, NoteCreate(batch_id='B-17', recorded_at=datetime.now(timezone.utc),
        idempotency_key='pilot-note-' + str(len(repo.load()['notes']))), DEMO_ACTORS['operator'])
    service.submit_transcript(repo, n['id'], text, DEMO_ACTORS['operator'])
    return n['id']


def extracted(repo, monkeypatch, claims, text='Packing complete.'):
    ident = typed(repo, text)
    monkeypatch.setattr(providers, 'extract', lambda *args: (Extraction(claims=[Candidate(**c) for c in claims]), 'test-fixture'))
    service.process_note(repo, ident)
    return repo.load()['notes'][ident]


def confirm(repo, cid, role='supervisor'):
    return service.resolve(repo, cid, ResolveRequest(expected_version=repo.load()['version'],
        action='confirm', reason='Reviewed the supplied source'), DEMO_ACTORS[role])


def test_two_independent_tasks_can_both_be_reviewed(repo, monkeypatch):
    note = extracted(repo, monkeypatch, [dict(property='task', value='Inspect seals', excerpt='Inspect seals'),
        dict(property='task', value='Replace labels', excerpt='replace labels')], 'Inspect seals and replace labels.')
    for cid in note['claim_ids']:
        confirm(repo, cid)
    tasks = handover(repo.load())['batches'][0]['tasks']
    assert {t['title'] for t in tasks} == {'Inspect seals', 'Replace labels'}
    assert all(repo.load()['claims'][cid]['status'] == 'confirmed' for cid in note['claim_ids'])


def test_revised_source_requires_explicit_reconciliation(repo, monkeypatch):
    packing = extracted(repo, monkeypatch, [dict(property='packing', value='complete', excerpt='Packing complete')])
    quality = extracted(repo, monkeypatch, [dict(property='quality', value='cleared', excerpt='Quality cleared')], 'Quality cleared.')
    confirm(repo, packing['claim_ids'][0]); confirm(repo, quality['claim_ids'][0], 'quality')
    assert handover(repo.load())['batches'][0]['status'] == 'verified'
    service.submit_transcript(repo, packing['id'], 'Microphone test only.', DEMO_ACTORS['operator'], repo.load()['version'])
    monkeypatch.setattr(providers, 'extract', lambda *args: (Extraction(claims=[], uncertainty='No operational report'), 'test-fixture'))
    service.process_note(repo, packing['id'])
    service.review_transcript(repo, packing['id'], TranscriptReview(expected_version=repo.load()['version'],
        claims=[], no_operational_update=True, reason='Corrected transcript contains no operational report'), DEMO_ACTORS['supervisor'])
    view = handover(repo.load())['batches'][0]
    assert view['status'] != 'verified'
    assert any(r['code'] == 'source_revision' for r in view['readiness_reasons'])
    assert repo.load()['claims'][packing['claim_ids'][0]]['source_review_pending']
    confirm(repo, packing['claim_ids'][0])
    assert not repo.load()['claims'][packing['claim_ids'][0]]['source_review_pending']
    assert handover(repo.load())['batches'][0]['status'] == 'verified'


def test_unchanged_review_and_transcript_do_not_invalidate_ack(repo, monkeypatch):
    note = extracted(repo, monkeypatch, [dict(property='packing', value='complete', excerpt='Packing complete')])
    confirm(repo, note['claim_ids'][0])
    service.acknowledge(repo, AckRequest(expected_version=repo.load()['version'], readback='Quality remains unverified'), DEMO_ACTORS['operator'])
    before = repo.load()
    confirm(repo, note['claim_ids'][0])
    service.submit_transcript(repo, note['id'], 'Packing complete.', DEMO_ACTORS['operator'], before['version'])
    assert repo.load() == before


def test_task_assignment_report_and_verification_are_separate(repo, monkeypatch):
    note = extracted(repo, monkeypatch, [dict(property='task', value='Inspect seals', excerpt='Inspect seals')], 'Inspect seals')
    cid = note['claim_ids'][0]; confirm(repo, cid)
    def update(action, role='supervisor', **kwargs):
        return service.update_task(repo, cid, TaskUpdate(expected_version=repo.load()['version'], action=action,
            reason='Checked the task evidence', **kwargs), DEMO_ACTORS[role])
    update('assign', owner='Worker', owner_id=DEMO_ACTORS['operator'].id)
    before = repo.load(); update('assign', owner='Worker', owner_id=DEMO_ACTORS['operator'].id)
    assert repo.load() == before
    with pytest.raises(HTTPException): update('verify')
    with pytest.raises(HTTPException): update('report_complete', 'quality')
    update('report_complete', 'operator')
    assert repo.load()['claims'][cid]['task_status'] == 'reported_complete'
    assert handover(repo.load())['batches'][0]['status'] != 'verified'
    update('verify')
    before = repo.load(); update('verify')
    assert repo.load() == before


def test_repeated_quantity_supersession_is_nonmaterial(repo, monkeypatch):
    first = extracted(repo, monkeypatch, [dict(property='quantity',value=15,excerpt='15')], '15')
    confirm(repo,first['claim_ids'][0])
    second = extracted(repo, monkeypatch, [dict(property='quantity',value=50,excerpt='50')], '50')
    def review():
        return service.resolve(repo,second['claim_ids'][0],ResolveRequest(expected_version=repo.load()['version'],action='confirm',
            reason='Corrected the quantity',supersedes=first['claim_ids']),DEMO_ACTORS['supervisor'])
    review();before=repo.load();review();assert repo.load()==before


def test_required_quantity_is_explicit_and_target_remains_informational(repo, monkeypatch):
    for claim, text, role in [(dict(property='packing', value='complete', excerpt='Packing complete'), 'Packing complete', 'supervisor'),
        (dict(property='quality', value='cleared', excerpt='Quality cleared'), 'Quality cleared', 'quality'),
        (dict(property='quantity', value=15, excerpt='15 cartons'), '15 cartons', 'supervisor')]:
        note = extracted(repo, monkeypatch, [claim], text); confirm(repo, note['claim_ids'][0], role)
    assert handover(repo.load())['batches'][0]['status'] == 'verified'
    with repo.transaction() as state:
        state['work_items'] = {'B-17': {'id':'B-17', 'name':'Pilot batch', 'target':500, 'required_dispatch_quantity':500}}
    assert handover(repo.load())['batches'][0]['status'] != 'verified'
    with repo.transaction() as state:
        state['quantity_exceptions'] = {'B-17': {'reason':'Approved partial dispatch', 'actor':DEMO_ACTORS['supervisor'].model_dump()}}
    # An older unbound exception cannot authorize a new requirement.
    assert handover(repo.load())['batches'][0]['status'] != 'verified'
    with repo.transaction() as state:
        state['quantity_exceptions']['B-17'].update(required_dispatch_quantity=500, accepted_quantity=15)
    view = handover(repo.load())['batches'][0]
    assert view['status'] == 'verified'
    assert any(r['code'] == 'quantity_exception' for r in view['readiness_reasons'])
    quantity_claim = note['claim_ids'][0]
    with repo.transaction() as state:
        state['work_items']['B-17']['required_dispatch_quantity'] = 600
    assert handover(repo.load())['batches'][0]['status'] != 'verified'
    with repo.transaction() as state:
        state['work_items']['B-17']['required_dispatch_quantity'] = 500
    assert handover(repo.load())['batches'][0]['status'] == 'verified'
    corrected = extracted(repo, monkeypatch, [dict(property='quantity', value=10, excerpt='10 cartons')], 'Actually 10 cartons')
    service.resolve(repo, corrected['claim_ids'][0], ResolveRequest(expected_version=repo.load()['version'],
        action='confirm', reason='Reviewed lower corrected count', supersedes=[quantity_claim]), DEMO_ACTORS['supervisor'])
    view = handover(repo.load())['batches'][0]
    assert view['quantity'] == 10 and view['status'] != 'verified'
    assert any(r['code'] == 'quantity_exception_review' for r in view['readiness_reasons'])


def test_repository_migrates_legacy_without_rewriting_archive(tmp_path):
    path = tmp_path / 'legacy.sqlite3'; legacy = empty_state()
    legacy['notes']['old'] = {'id':'old', 'batch_id':'B-17', 'transcripts':[{'text':'Original'}]}
    raw = json.dumps(legacy)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE workspace (id INTEGER PRIMARY KEY, document TEXT NOT NULL)')
        db.execute('INSERT INTO workspace VALUES (1,?)', (raw,))
    repo = LocalRepository(path)
    assert repo.load() == legacy
    with repo.transaction() as state:
        state['notes']['new'] = {'id':'new', 'batch_id':'B-18'}
        state['version'] += 1
    assert len(LocalRepository(path).load()['notes']) == 2
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT document FROM workspace').fetchone()[0] == raw
        assert db.execute("SELECT count(*) FROM workspace_records WHERE collection='notes'").fetchone()[0] == 2


def test_repository_reads_and_noops_never_update_storage(repo):
    statements=[]; original=repo.connect
    def traced():
        db=original(); db.set_trace_callback(statements.append); return db
    with patch.object(repo, 'connect', traced):
        repo.load()
        with repo.transaction(): pass
    assert not any(sql.lstrip().upper().startswith(('UPDATE ', 'INSERT ', 'DELETE ')) for sql in statements)


def test_repository_diff_writes_and_paginated_scope(repo):
    with repo.transaction() as state:
        for n in range(4):
            state['notes'][str(n)] = {'id':str(n), 'batch_id':'B-17' if n<3 else 'B-18', 'shift_id':'shift-1', 'created_at':str(n)}
    statements=[]; original=repo.connect
    def traced():
        db=original(); db.set_trace_callback(statements.append); return db
    with patch.object(repo, 'connect', traced):
        with repo.transaction() as state: state['notes']['1']['status']='received'
    writes=[sql for sql in statements if sql.lstrip().upper().startswith('INSERT INTO WORKSPACE_RECORDS')]
    assert len(writes)==1
    assert [n['id'] for n in repo.query_records('notes',batch_id='B-17',shift_id='shift-1',limit=2)] == ['2','1']
    assert [n['id'] for n in repo.query_records('notes',batch_id='B-17',limit=2,offset=2)] == ['0']


def test_scoped_reads_join_evidence_without_loading_other_teams(repo):
    with repo.transaction() as state:
        state['work_items'] = {key: {'id':key, 'name':key} for key in ('A','B')}
        for key, shift in [('A','shift-a'), ('B','shift-b')]:
            state['notes']['n'+key] = {'id':'n'+key, 'batch_id':key, 'shift_id':shift}
            state['claims']['c'+key] = {'id':'c'+key, 'batch_id':key, 'note_id':'n'+key}
            state['resolutions']['r'+key] = {'id':'r'+key, 'claim_id':'c'+key, 'action':'confirm'}
            state['resolutions']['manual'+key] = {'id':'manual'+key, 'note_id':'n'+key, 'action':'manual_extraction'}
            state['jobs']['j'+key] = {'id':'j'+key, 'note_id':'n'+key}
            state['snapshots']['s'+key] = {'id':'s'+key, 'shift_id':shift}
            state['acknowledgements']['a'+key] = {'id':'a'+key, 'shift_id':shift}
    index = repo.load_index()
    assert set(index['work_items']) == {'A','B'}
    assert all(index[key] == {} for key in ('notes','claims','resolutions','jobs','snapshots','acknowledgements'))
    scoped = repo.load_scoped(['A'], shift_ids=['shift-a'])
    assert set(scoped['work_items']) == {'A'} and set(scoped['notes']) == {'nA'}
    assert set(scoped['resolutions']) == {'rA','manualA'}
    assert set(scoped['jobs']) == {'jA'}
    assert set(scoped['snapshots']) == {'sA'} and set(scoped['acknowledgements']) == {'aA'}
    assert repo.load_scoped(['A'])['snapshots'] == {}
    before = repo.load()
    with repo.transaction(batch_ids=['A']) as selected:
        assert set(selected['notes']) == {'nA'}
        selected['notes']['nA']['status']='received'
    after = repo.load()
    assert after['notes']['nA']['status']=='received'
    assert after['notes']['nB']==before['notes']['nB']
    assert after['resolutions']==before['resolutions'] and after['snapshots']==before['snapshots']


def test_unpatched_sqlite_cannot_enable_wal(tmp_path, monkeypatch):
    monkeypatch.setenv('SHIFTPROOF_SQLITE_WAL','true')
    monkeypatch.setattr(sqlite3, 'sqlite_version_info', (3,50,4))
    with pytest.raises(RuntimeError, match='WAL deployment requires'):
        LocalRepository(tmp_path/'wal.sqlite3')


def test_partial_writes_cannot_overwrite_unloaded_or_exact_id_foreign_sources(repo):
    with repo.transaction() as state:
        state['work_items'] = {key:{'id':key} for key in ('A','B')}
        state['notes']['nB'] = {'id':'nB','batch_id':'B','status':'received'}
        state['claims']['cB'] = {'id':'cB','batch_id':'B','note_id':'nB'}
    before = repo.load()
    with pytest.raises(Conflict, match='identifier'):
        with repo.transaction(batch_ids=['A']) as state:
            state['notes']['nB'] = {'id':'nB','batch_id':'A'}
    with pytest.raises(Conflict, match='another work item'):
        with repo.transaction(batch_ids=['A'], record_ids={'notes':['nB']}) as state:
            state['notes']['nB']['status'] = 'discarded'
    with pytest.raises(Conflict, match='another work item'):
        with repo.transaction(batch_ids=['A']) as state:
            state['claims']['new'] = {'id':'new','batch_id':'B','note_id':'nB'}
    with pytest.raises(Conflict, match='internal transaction scope'):
        with repo.transaction(batch_ids=['A']) as state:
            state['_transaction_batch_ids'].append('B')
    assert repo.load() == before


def test_missing_material_cache_bootstraps_complete_history_once(repo):
    with repo.transaction() as state:
        state['work_items'] = {key:{'id':key,'team_id':key,'location_id':'L'} for key in ('A','B')}
        state['shift_occurrences'] = {key:{'id':key,'team_id':key,'location_id':'L'} for key in ('A','B')}
        state['assignments'] = {}
        for key in ('A','B'):
            state['notes']['n'+key] = {'id':'n'+key,'batch_id':key,'status':'processed','revision':1}
            state['claims']['c'+key] = {'id':'c'+key,'batch_id':key,'note_id':'n'+key,'value':'pending'}
    before = repo.load()
    with repo.connect() as db:
        db.execute("DELETE FROM workspace_metadata WHERE key='material_items'")
    with repo.transaction(batch_ids=['A']):
        pass
    restored = repo.load()
    assert restored == before
    assert '_transaction_batch_ids' not in restored
    with repo.transaction(batch_ids=['A']) as state:
        assert set(state['notes']) == {'nA'}
        state['claims']['cA']['value'] = 'complete'
    after = repo.load()
    assert after['handovers']['A']['version'] == before['handovers']['A']['version'] + 1
    assert after['handovers']['B'] == before['handovers']['B']
    assert after['material_items']['B'] == before['material_items']['B']
    assert after['notes']['nB'] == before['notes']['nB']
    assert '_transaction_batch_ids' not in after


def test_durable_job_is_idempotent_and_records_attempts(repo, monkeypatch):
    note = typed(repo)
    job = durable_jobs.enqueue(repo, note, DEMO_ACTORS['operator'])
    assert durable_jobs.enqueue(repo, note, DEMO_ACTORS['operator'])['id'] == job['id']
    def fake(text, batch, reserve, context):
        reserve()
        return Extraction(claims=[Candidate(property='packing', value='complete', excerpt='Packing complete')]), 'test-fixture'
    monkeypatch.setattr(providers,'extract',fake)
    assert durable_jobs.run_once(repo)
    result=repo.load()['jobs'][job['id']]
    assert result['status']=='succeeded' and result['attempts']=={'extraction':1}
    before=repo.load(); assert not durable_jobs.run_once(repo); assert repo.load()==before
    assert durable_jobs.retry(repo,job['id'],DEMO_ACTORS['operator'])['status']=='succeeded'


def test_expired_job_resumes_saved_transcription_after_crash(repo, monkeypatch):
    note=service.create_note(repo,NoteCreate(batch_id='B-17',recorded_at=datetime.now(timezone.utc),idempotency_key='voice-crash'),DEMO_ACTORS['operator'])
    data=io.BytesIO()
    with wave.open(data,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000);wav.writeframes(pcm_frames(4000, 8000))
    path=repo.data_dir/note['audio_key'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data.getvalue())
    job=durable_jobs.enqueue(repo,note['id'],DEMO_ACTORS['operator'])
    monkeypatch.setattr(providers,'transcribe',lambda audio:('Packing complete.','test-prisma'))
    def crash(text,batch,reserve,context): reserve(); raise SystemExit('simulated worker termination')
    monkeypatch.setattr(providers,'extract',crash)
    with pytest.raises(SystemExit): durable_jobs.run_once(repo)
    assert repo.load()['notes'][note['id']]['transcripts'][0]['kind']=='prisma_verbatim'
    with repo.transaction() as state:state['jobs'][job['id']]['lease_until']='2000-01-01T00:00:00+00:00'
    monkeypatch.setattr(providers,'transcribe',lambda audio:pytest.fail('Completed transcription must be reused'))
    def recovered(text,batch,reserve,context):
        reserve(); return Extraction(claims=[Candidate(property='packing',value='complete',excerpt='Packing complete')]),'recovered'
    monkeypatch.setattr(providers,'extract',recovered)
    assert durable_jobs.run_once(repo)
    final=repo.load()['jobs'][job['id']]
    assert final['status']=='succeeded'
    assert final['attempts']=={'transcription':1,'extraction':2}


def test_durable_budget_survives_two_crashes(repo, monkeypatch):
    note=typed(repo);job=durable_jobs.enqueue(repo,note,DEMO_ACTORS['operator'])
    def crash(text,batch,reserve,context):reserve();raise SystemExit()
    monkeypatch.setattr(providers,'extract',crash)
    for _ in range(2):
        with pytest.raises(SystemExit):durable_jobs.run_once(repo)
        with repo.transaction() as state:state['jobs'][job['id']]['lease_until']='2000-01-01T00:00:00+00:00'
    durable_jobs.run_once(repo)
    assert repo.load()['jobs'][job['id']]['status']=='failed'
    assert repo.load()['jobs'][job['id']]['error_category']=='attempts_exhausted'
    assert repo.load()['jobs'][job['id']]['attempts']['extraction']==2
    retried=durable_jobs.retry(repo,job['id'],DEMO_ACTORS['supervisor'])
    assert retried['status']=='queued' and len(retried['attempt_history'])==1


def test_real_data_is_blocked_before_any_provider_call(repo, monkeypatch):
    note=typed(repo);repo.organization_id='test-organization'
    with repo.transaction() as state:
        state['data_policy']={'mode':'real','provider_terms_approved':True,'recording_consent':True,'spending_cap_confirmed':True,'retention_days':30}
    monkeypatch.setattr(providers,'extract',lambda *args:pytest.fail('Free provider must not receive real data'))
    service.process_note(repo,note)
    saved=repo.load()['notes'][note]
    assert saved['status']=='manual_review' and saved['error_category']=='real_data_provider_unapproved'
    assert saved['transcripts'][0]['text']=='Packing complete.'
    with pytest.raises(providers.ProviderError):service.check_provider_policy(repo,'speech')


def test_real_policy_alias_is_restrictive_and_requires_factory_approval(repo, monkeypatch):
    repo.organization_id = 'policy-test'
    monkeypatch.setenv('GEMINI_ACCOUNT_TIER','business');monkeypatch.setenv('GEMINI_BUSINESS_API_KEY','separate-business-test')
    monkeypatch.setenv('GEMINI_BUSINESS_MODEL_ID','pinned-model');monkeypatch.setenv('SHIFTPROOF_BUSINESS_PROVIDER_APPROVED','true')
    monkeypatch.setenv('GEMINI_BUSINESS_TERMS_CONFIRMED','true');monkeypatch.setenv('EXTRACTION_PROVIDER','gemini')
    settings.cache_clear()
    with repo.transaction() as state:
        state['data_policy'] = {'mode':'fictional','data_classification':'real','provider_terms_approved':True,
            'recording_consent':True,'spending_cap_confirmed':True,'retention_days':30}
    assert service.provider_policy_status(repo)['mode'] == 'real'
    with pytest.raises(providers.ProviderError):service.check_provider_policy(repo)
    with repo.transaction() as state:state['data_policy']['factory_approval'] = True
    service.check_provider_policy(repo)
    monkeypatch.setenv('GEMINI_API_KEY','separate-business-test')
    with pytest.raises(providers.ProviderError):service.check_provider_policy(repo)


def test_business_credentials_are_explicit_and_never_fall_back(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','free-test-key')
    monkeypatch.setenv('GEMINI_ACCOUNT_TIER','business')
    monkeypatch.delenv('GEMINI_BUSINESS_API_KEY',raising=False)
    settings.cache_clear()
    assert settings().gemini_key==''
    monkeypatch.setenv('GEMINI_BUSINESS_API_KEY','business-test-key')
    monkeypatch.setenv('GEMINI_BUSINESS_MODEL_ID','pinned-business-test-model')
    settings.cache_clear()
    assert settings().gemini_key=='business-test-key'
    assert settings().gemini_model=='pinned-business-test-model'


def test_demo_budget_cannot_consume_private_bucket(repo, monkeypatch, tmp_path):
    monkeypatch.setenv('MAX_DEMO_CALLS_PER_DAY','1')
    service.reserve_usage(repo)
    with pytest.raises(providers.ProviderError):service.reserve_usage(repo)
    private=LocalRepository(tmp_path/'private.sqlite3');private.organization_id='private'
    service.reserve_usage(private)
    assert private.load()['usage'][datetime.now(timezone.utc).date().isoformat()]['model_calls']==1


def test_removed_member_job_stops_before_provider_request(monkeypatch):
    from test_organizations import account, item, note as make_note
    from shiftproof import identity
    from shiftproof.models import Actor
    client, org, _ = account(); item(client, org)
    note_id = make_note(client, org, text='Packing complete.')
    actor = Actor.model_validate(client.get(f'/organizations/{org}/workspace').json()['actor'])
    repo = identity.tenant_repo(client.get('/organizations/' + org).json())
    job = durable_jobs.enqueue(repo, note_id, actor)
    with identity.database() as db:
        db.execute('DELETE FROM memberships WHERE org_id=? AND user_id=?', (org, actor.id))
    with pytest.raises(HTTPException) as removed_enqueue:
        durable_jobs.enqueue(repo, note_id, actor)
    assert removed_enqueue.value.status_code == 403
    with pytest.raises(HTTPException) as removed_retry:
        durable_jobs.retry(repo, job['id'], actor)
    assert removed_retry.value.status_code == 403
    monkeypatch.setattr(providers, 'extract', lambda *args: pytest.fail('Removed member must not spend provider quota'))
    durable_jobs.run_once(repo)
    assert repo.load()['jobs'][job['id']]['status'] == 'authorization_required'
    assert repo.load()['notes'][note_id]['status'] == 'manual_review'


def test_lost_job_lease_cannot_apply_late_provider_result(repo, monkeypatch):
    note = typed(repo); job = durable_jobs.enqueue(repo, note, DEMO_ACTORS['operator'])
    def fake(text, batch, reserve, context):
        reserve()
        with repo.transaction() as state:
            state['jobs'][job['id']]['lease_token'] = 'another-worker'
        return Extraction(claims=[Candidate(property='packing',value='complete',excerpt='Packing complete')]), 'late-result'
    monkeypatch.setattr(providers, 'extract', fake)
    durable_jobs.run_once(repo)
    after = repo.load()
    assert after['claims'] == {}
    assert after['jobs'][job['id']]['lease_token'] == 'another-worker'
    assert after['notes'][note]['status'] == 'processing'
