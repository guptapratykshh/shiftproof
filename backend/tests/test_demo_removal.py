import pytest
from fastapi.testclient import TestClient
from shiftproof.api import app

@pytest.mark.parametrize('method,path', [
    ('post', '/auth/demo'), ('post', '/demo/seed'), ('get', '/auth/me'),
    ('get', '/workspace'), ('get', '/samples'), ('get', '/evaluation'),
    ('get', '/notes/fixture-1'), ('get', '/notes/fixture-1/audio'),
    ('post', '/notes'), ('post', '/speech'), ('post', '/questions'),
    ('get', '/shifts/shift-B/handover'), ('get', '/shifts/shift-B/snapshots/1'),
    ('post', '/claims/fixture-1/resolve'), ('post', '/tasks/fixture-1'),
])
def test_removed_demo_endpoints_are_not_registered(method, path):
    response = getattr(TestClient(app), method)(path)
    assert response.status_code == 404

def test_api_schema_contains_only_organization_operations():
    paths=app.openapi()['paths']
    assert '/organizations/{org_id}/notes' in paths
    assert '/organizations/{org_id}/notes/{note_id}/review' in paths
    assert '/auth/signup' in paths
    assert '/auth/demo' not in paths
    assert '/workspace' not in paths
