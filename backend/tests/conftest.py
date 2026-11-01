import pytest
from shiftproof.config import settings
from shiftproof.repository import repository

@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv('SHIFTPROOF_ENV', 'local')
    monkeypatch.setenv('SHIFTPROOF_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('EXTRACTION_PROVIDER', 'scripted')
    monkeypatch.setenv('SHIFTPROOF_DURABLE_JOBS','false')
    monkeypatch.setenv('SHIFTPROOF_REQUIRE_DATA_POLICY','false')
    monkeypatch.setenv('SHIFTPROOF_SHARED_USAGE_DB', str(tmp_path / 'shared-usage.sqlite3'))
    monkeypatch.setenv('GEMINI_MODEL_ID', 'gemini-3.8-flash')
    settings.cache_clear()
    yield
    settings.cache_clear()

@pytest.fixture
def repo():
    return repository()

@pytest.fixture
def organization_api():
    from test_organizations import account, item
    from shiftproof.identity import tenant_repo
    client, org, _ = account()
    item(client, org, 'B-17')
    return client, org, tenant_repo({'id': org, 'industry': 'manufacturing'})
