from audio_fixture import pcm_frames
import io
import json
import time
import wave
import pytest
from fastapi.testclient import TestClient
from shiftproof.api import app
from shiftproof import identity, providers
from shiftproof.config import settings
from shiftproof.repository import repository


def account(industry='manufacturing',email='owner@example.com'):
    c=TestClient(app)
    r=c.post('/auth/signup',json=dict(name='Test Owner',email=email,password='a-long-test-password',organization_name='Factory One',industry=industry,timezone='Asia/Kolkata'))
    assert r.status_code==201,r.text
    c.headers['X-CSRF-Token']=r.json()['csrf_token']
    return c,r.json()['organization_id'],r.json()

def item(c,org,key='BATCH-77'):
    r=c.post(f'/organizations/{org}/work-items',json=dict(id=key,name='Test work item',line='Line A'))
    assert r.status_code==201,r.text
    return key

def state(c,org):
    r=c.get(f'/organizations/{org}/workspace'); assert r.status_code==200,r.text
    return r.json()

def note(c,org,work='BATCH-77',text='Quality pending',key=None):
    from datetime import datetime,timezone
    body=dict(batch_id=work,recorded_at=datetime.now(timezone.utc).isoformat(),idempotency_key=key or 'note-key-'+str(time.time_ns()))
    r=c.post(f'/organizations/{org}/notes',json=body);assert r.status_code==201,r.text
    n=r.json()['note']['id']
    r=c.post(f'/organizations/{org}/notes/{n}/transcript',json={'transcript':text});assert r.status_code==200,r.text
    return n

def extract(c,org,monkeypatch,claims,text='Quality pending',work='BATCH-77'):
    n=note(c,org,work,text)
    def fake(transcript,batch,reserve,context):
        return providers.validate_extraction({'claims':claims},transcript,context),'test-request'
    monkeypatch.setattr(providers,'extract',fake)
    r=c.post(f'/organizations/{org}/notes/{n}/process',json={});assert r.status_code==202,r.text
    return c.get(f'/organizations/{org}/notes/{n}').json()

def resolve(c,org,claim,action='confirm',supersedes=()):
    return c.post(f'/organizations/{org}/claims/{claim}/resolve',json=dict(action=action,reason='Reviewed source evidence',expected_version=state(c,org)['version'],supersedes=list(supersedes)))


def test_real_signup_empty_workspace_and_hashes():
    c,org,signup=account()
    s=state(c,org);assert s['batches']==[] and s['notes']==[]
    assert c.get('/auth/session').json()['organizations'][0]['access']=='owner'
    assert s['actor']['role']=='supervisor'
    with identity.database() as db:
        user=db.execute('SELECT * FROM users').fetchone()
        assert user['password'].startswith('$argon2')
        assert signup['recovery_codes'][0] not in user['recovery']
    assert 'HttpOnly' in c.post('/auth/login',json={'email':'owner@example.com','password':'a-long-test-password'}).headers['set-cookie']


def test_auth_csrf_origin_and_logout_revocation():
    c,org,_=account();cookie=c.cookies.get(identity.COOKIE)
    c.headers.pop('X-CSRF-Token')
    assert c.post('/organizations',json={'name':'Other','industry':'maintenance'}).status_code==403
    c.headers['X-CSRF-Token']=c.get('/auth/session').json()['csrf_token']
    assert c.post('/organizations',json={'name':'Other','industry':'maintenance'},headers={'Origin':'https://evil.example'}).status_code==403
    assert c.post('/auth/login',json={'email':'owner@example.com','password':'a-long-test-password'},headers={'Origin':'https://evil.example'}).status_code==403
    assert c.post('/auth/logout',json={}).status_code==200
    c.cookies.set(identity.COOKIE,cookie)
    assert c.get('/auth/session').status_code==401


def test_recovery_is_single_use_and_revokes_sessions():
    c,org,result=account();other=TestClient(app)
    body=dict(email='owner@example.com',code=result['recovery_codes'][0],password='changed-long-password')
    assert other.post('/auth/recover',json=body).status_code==200
    assert c.get('/auth/session').status_code==401
    assert other.post('/auth/recover',json=body).status_code==400
    assert other.post('/auth/login',json={'email':'owner@example.com','password':'changed-long-password'}).status_code==200


def test_password_change_revokes_all_sessions():
    c,_,_=account();other=TestClient(app)
    other.post('/auth/login',json={'email':'owner@example.com','password':'a-long-test-password'})
    assert c.post('/auth/password',json={'current_password':'a-long-test-password','password':'another-long-password'}).status_code==200
    assert other.get('/auth/session').status_code==401


def test_cross_organization_isolation_including_audio_and_demo():
    a,oa,_=account();b,ob,_=account(email='second@example.com');item(a,oa);item(b,ob)
    n=note(a,oa)
    for suffix in ['/workspace','/export',f'/notes/{n}',f'/notes/{n}/audio','/shifts/shift-B/handover','/shifts/shift-B/snapshots/1']:
        assert b.get('/organizations/'+oa+suffix).status_code==404
    assert b.get(f'/organizations/{ob}/notes/{n}').status_code==404
    assert b.post(f'/organizations/{oa}/notes/{n}/process',json={}).status_code==404
    assert state(b,ob)['notes']==[]
    demo=TestClient(app)
    assert demo.post('/auth/demo',json={'role':'quality'}).status_code==404
    demo.headers['Authorization']='Bearer retired-demo-token'
    assert demo.get('/organizations/'+oa+'/workspace').status_code==401
    assert demo.get('/notes/'+n).status_code==404
    assert TestClient(app).get('/organizations/'+oa+'/workspace').status_code==401


def test_invitation_identity_role_expiry_reuse_and_membership_removal():
    owner,org,_=account();inv=owner.post(f'/organizations/{org}/invitations',json={'email':'worker@example.com','role':'operator'}).json()['join_path'].split('/')[-1]
    wrong,_,_=account(email='wrong@example.com')
    assert wrong.post('/invitations/accept',json={'token':inv}).status_code==403
    worker=TestClient(app);r=worker.post('/auth/signup',json=dict(name='Worker',email='worker@example.com',password='a-worker-long-password',invitation_token=inv))
    assert r.status_code==201,r.text
    worker.headers['X-CSRF-Token']=r.json()['csrf_token']
    me=worker.get('/auth/session').json();assert me['organizations'][0]['role']=='operator'
    assert worker.post('/invitations/accept',json={'token':inv}).status_code==410
    assert worker.post(f'/organizations/{org}/work-items',json={'id':'X','name':'Illegal'}).status_code==403
    assert worker.post(f'/organizations/{org}/invitations',json={'email':'more@example.com','role':'quality'}).status_code==403
    user_id=me['user']['id'];assert owner.delete(f'/organizations/{org}/members/{user_id}').status_code==200
    assert worker.get(f'/organizations/{org}/workspace').status_code==404
    inv2=owner.post(f'/organizations/{org}/invitations',json={'email':'expired@example.com'}).json()['join_path'].split('/')[-1]
    with identity.database() as db: db.execute('UPDATE invitations SET expires=0 WHERE token=?',(identity.digest(inv2),))
    assert worker.get('/invitations/'+inv2).status_code==410


def test_last_owner_and_explicit_operational_permissions():
    c,org,_=account();me=c.get('/auth/session').json()['user']['id']
    assert c.delete(f'/organizations/{org}/members/{me}').status_code==409
    assert c.put(f'/organizations/{org}/members/{me}',json={'access':'member','role':'operator'}).status_code==409
    assert c.put(f'/organizations/{org}/members/{me}',json={'access':'owner','role':'quality'}).status_code==200
    assert c.get('/auth/session').json()['organizations'][0]['role']=='quality'

@pytest.mark.parametrize('industry',['quality_assurance','food_processing','construction','healthcare','facilities'])
def test_preview_never_opens_manufacturing(industry):
    c,org,_=account(industry)
    assert c.get(f'/organizations/{org}').json()['profile']['status']=='preview'
    assert c.get(f'/organizations/{org}/workspace').status_code==409
    assert c.post(f'/organizations/{org}/work-items',json={'id':'X','name':'Something'}).status_code==409
    assert c.put(f'/organizations/{org}/setup',json={'locations':['Location 1'],'teams':['Team 1'],'shifts':['Morning']}).status_code==200

@pytest.mark.parametrize('industry,first,later',[
 ('manufacturing',('quality','pending'),('packing','complete')),
 ('maintenance',('fault','open'),('operating','running')),
 ('warehousing',('documents','pending'),('packing','complete'))])
def test_hold_survives_later_update_and_wrong_role(industry,first,later,monkeypatch):
    c,org,_=account(industry);item(c,org)
    n=extract(c,org,monkeypatch,[{'property':first[0],'value':first[1],'excerpt':'Original issue'}],text='Original issue')
    hold=n['claim_ids'][0];assert resolve(c,org,hold).status_code==200
    newer=extract(c,org,monkeypatch,[{'property':later[0],'value':later[1],'excerpt':'Later update'}],text='Later update')
    assert resolve(c,org,newer['claim_ids'][0]).status_code==200
    assert state(c,org)['batches'][0]['status']=='hold'
    assert resolve(c,org,hold,'reject').status_code==403
    me=c.get('/auth/session').json()['user']['id'];c.put(f'/organizations/{org}/members/{me}',json={'access':'owner','role':'quality'})
    assert resolve(c,org,hold,'reject').status_code==200
    assert state(c,org)['batches'][0]['status']!='verified' # Other prerequisites still missing.


def test_warehouse_dispatch_does_not_verify_documents(monkeypatch):
    c,org,_=account('warehousing');item(c,org)
    n=extract(c,org,monkeypatch,[{'property':'dispatch','value':'ready','excerpt':'Ready'}],text='Ready')
    resolve(c,org,n['claim_ids'][0])
    v=state(c,org)['batches'][0]
    assert v['status']=='conflict'
    assert any('Documents' in r['text'] for r in v['readiness_reasons'])
    requirements = {r['text']: r['owner'] for r in v['readiness_reasons'] if r['code'] == 'unverified'}
    assert requirements['Packing complete is not human-reviewed'] == 'Shift supervisor'
    assert requirements['Documents verified is not human-reviewed'] == 'Authorized reviewer'


def test_profile_validation_rejects_other_industry_claims(monkeypatch):
    c,org,_=account('maintenance');item(c,org)
    n=extract(c,org,monkeypatch,[{'property':'quality','value':'cleared','excerpt':'Clear'}],text='Clear')
    assert n['status']=='manual_review' and not n['claim_ids']
    r=c.post(f'/organizations/{org}/notes/{n["id"]}/review-transcript',json={'expected_version':state(c,org)['version'],'reason':'Attempt wrong profile','claims':[{'property':'packing','value':'complete','excerpt':'Clear'}]})
    assert r.status_code==422


def test_duplicate_processing_stale_review_and_ack_snapshot(monkeypatch):
    c,org,_=account();item(c,org)
    n=extract(c,org,monkeypatch,[{'property':'packing','value':'complete','excerpt':'Packed'}],text='Packed')
    old=state(c,org)['version'];assert resolve(c,org,n['claim_ids'][0]).status_code==200
    r=c.post(f'/organizations/{org}/claims/{n["claim_ids"][0]}/resolve',json={'action':'confirm','reason':'Concurrent review','expected_version':old})
    assert r.status_code==409
    v=state(c,org)['version'];assert c.post(f'/organizations/{org}/notes/{n["id"]}/process',json={}).status_code==202
    assert state(c,org)['version']==v
    assert c.post(f'/organizations/{org}/shifts/shift-B/acknowledgements',json={'expected_version':v,'readback':'Quality remains unverified'}).status_code==200
    snapshot=c.get(f'/organizations/{org}/shifts/shift-B/snapshots/{v}').json()
    item(c,org,'SECOND')
    assert not state(c,org)['acknowledgements'][0]['current']
    assert c.get(f'/organizations/{org}/shifts/shift-B/snapshots/{v}').json()==snapshot


def test_stale_clarification_does_not_create_note(monkeypatch):
    from datetime import datetime,timezone
    c,org,_=account();item(c,org)
    extract(c,org,monkeypatch,[{'property':'quality','value':'pending','excerpt':'Pending'}],text='Pending')
    s=state(c,org);question=s['batches'][0]['clarification'];item(c,org,'NEW')
    r=c.post(f'/organizations/{org}/notes',json={'batch_id':'BATCH-77','recorded_at':datetime.now(timezone.utc).isoformat(),'idempotency_key':'stale-clarification','clarification_ref':question['id'],'clarification_version':s['version']})
    assert r.status_code==409 and len(state(c,org)['notes'])==1


def test_shared_provider_limit_and_per_org_limit(monkeypatch):
    from shiftproof import service
    c,a,_=account();b=c.post('/organizations',json={'name':'Other','industry':'manufacturing'}).json()['organization_id']
    orga=c.get('/organizations/'+a).json();orgb=c.get('/organizations/'+b).json()
    ra=identity.tenant_repo(orga);rb=identity.tenant_repo(orgb)
    service.reserve_usage(ra,limit=1)
    with pytest.raises(providers.ProviderError):service.reserve_usage(rb,limit=1)
    assert rb.load()['usage']=={}


def test_saved_audio_is_private_and_retry_preserves_transcript(monkeypatch):
    from datetime import datetime,timezone
    c,org,_=account();item(c,org)
    n=c.post(f'/organizations/{org}/notes',json={'batch_id':'BATCH-77','recorded_at':datetime.now(timezone.utc).isoformat(),'idempotency_key':'voice-test-one'}).json()['note']['id']
    out=io.BytesIO()
    with wave.open(out,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(pcm_frames(16000))
    path=f'/organizations/{org}/notes/{n}'
    assert c.put(path+'/audio',content=out.getvalue(),headers={'Content-Type':'audio/wav'}).status_code==200
    calls=[]
    monkeypatch.setattr(providers,'transcribe',lambda audio:(calls.append(1) or 'Unknown speech','prisma-id'))
    assert c.post(path+'/process',json={'transcribe_only':True}).status_code==202
    assert c.post(path+'/process',json={}).status_code==202
    assert c.post(path+'/process',json={}).status_code==202
    assert len(calls)==1
    assert c.get(path+'/audio').content==out.getvalue()
    assert TestClient(app).get(path+'/audio').status_code==401
    assert c.get('/notes/'+n+'/audio').status_code==404
    assert c.get(path).json()['transcripts'][0]['text']=='Unknown speech'


def test_legacy_adoption_preserves_original_history_and_is_idempotent(tmp_path):
    import importlib.util
    from pathlib import Path
    from shiftproof.repository import LocalRepository
    from shiftproof.service import seed
    spec=importlib.util.spec_from_file_location('adopt',Path(__file__).resolve().parents[2]/'scripts/adopt_legacy_workspace.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    c,_,_=account();legacy=tmp_path/'legacy'/'shiftproof.sqlite3';repo=LocalRepository(legacy);seed(repo)
    with repo.transaction() as s:
        s['snapshots']['handover:999']={'version':999,'example':'retained'}
        s['acknowledgements']['old']={'version':999,'snapshot_id':'handover:999'}
    original=repo.load();result=module.adopt(legacy,'owner@example.com','Imported Factory')
    assert module.adopt(legacy,'owner@example.com','Imported Factory')==result
    assert repo.load()==original
    imported=c.get('/organizations/'+result['organization_id']+'/export').json()
    for key in ('notes','claims','resolutions','snapshots','acknowledgements'):assert imported[key]==original[key]
    assert c.get('/workspace').status_code==404
    assert (Path(result['backup'])/'workspace.sqlite3').exists()


def test_reviewer_can_retry_legacy_authored_note_without_changing_its_author(monkeypatch):
    c,org,_=account();item(c,org);n=note(c,org,text='Packing complete ho gayi hai.')
    org_data=c.get('/organizations/'+org).json();repo=identity.tenant_repo(org_data)
    with repo.transaction() as s:
        s['notes'][n]['actor']={'id':'legacy-operator','name':'Original speaker','role':'operator'}
    r=c.post(f'/organizations/{org}/notes/{n}/process',json={})
    assert r.status_code==202,r.text
    saved=c.get(f'/organizations/{org}/notes/{n}').json()
    assert saved['actor']['id']=='legacy-operator' and saved['claim_ids']
    assert c.delete(f'/organizations/{org}/notes/{n}').status_code==403
