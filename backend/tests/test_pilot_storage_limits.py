"""Phone drafts can retry after a full server without replacing source audio."""
from types import SimpleNamespace
from shiftproof import organizations_api
from test_organizations import account
from test_pilot_scope import team_shift, create_note, wav


def test_storage_full_retains_empty_source_and_allows_exact_audio_retry(monkeypatch):
    owner,org,_=account();team=team_shift(owner,org);note_id=create_note(owner,org,team)
    path=f'/organizations/{org}/notes/{note_id}'
    original_disk_usage=organizations_api.shutil.disk_usage
    monkeypatch.setattr(organizations_api.shutil,'disk_usage',lambda path:SimpleNamespace(free=0))
    response=owner.put(path+'/audio',content=wav(),headers={'Content-Type':'audio/wav'})
    assert response.status_code==507,response.text
    assert owner.get(path).json()['has_audio'] is False
    monkeypatch.setattr(organizations_api.shutil,'disk_usage',original_disk_usage)
    assert owner.put(path+'/audio',content=wav(),headers={'Content-Type':'audio/wav'}).status_code==200
    before=owner.get(f'/organizations/{org}/workspace').json()['version']
    duplicate=owner.put(path+'/audio',content=wav(),headers={'Content-Type':'audio/wav'})
    assert duplicate.status_code==200 and duplicate.json()['duplicate'] is True
    assert owner.get(f'/organizations/{org}/workspace').json()['version']==before
    assert owner.get(path+'/audio').content==wav()
