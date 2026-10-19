"""Synthetic versioned demo import requires no network and preserves write guards."""
import importlib
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.demo_documents import DEMO_DOCUMENT_KEYS, BUNDLE_DIR, load_demo_documents
from backend.models import Source, SourceInput

ORIGIN = {'Origin': 'http://testserver'}
PATH = '/api/sources/demo-documents'


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Any attempt to fetch from GitHub, including raw URLs, fails this test.
    async def no_network(*args, **kwargs):
        raise AssertionError('Demo import must never use the network')
    monkeypatch.setattr(importlib.import_module('backend.app'), 'fetch_readme', no_network)
    monkeypatch.setattr(httpx.AsyncClient, 'send', no_network)
    app = create_app(tmp_path, auth_enabled=True, passcode='code', origins=['http://testserver'])
    with TestClient(app) as client:
        client.post('/api/login', headers=ORIGIN, json={'name': 'Reviewer', 'passcode': 'code'})
        yield client, app


def test_import_adds_fixed_six_without_network_and_repeat_skips(client):
    client, app = client
    first = client.post(PATH, headers=ORIGIN, json={'revision': 0})
    assert first.status_code == 200
    data = first.json()
    assert data['imported'] == list(DEMO_DOCUMENT_KEYS)
    assert data['skipped'] == data['failed'] == []
    assert len(data['workspace']['sources']) == 6
    assert data['workspace']['revision'] == 1
    assert len(data['workspace']['audit']) == 1
    for (_, expected), actual in zip(load_demo_documents(), data['workspace']['sources']):
        assert actual == expected.model_dump()
    second = client.post(PATH, headers=ORIGIN, json={'revision': 1}).json()
    assert second['imported'] == second['failed'] == []
    assert second['skipped'] == list(DEMO_DOCUMENT_KEYS)
    assert second['workspace']['revision'] == 1
    assert app.state.store.read().model_dump() == data['workspace']


def test_import_preserves_existing_sources_and_skips_partial_previous_import(client):
    client, app = client
    state = app.state.store.read()
    existing = Source.create(SourceInput(title='Existing', version='1', text='Keep this unchanged.'))
    state.sources = [existing, load_demo_documents()[-1][1]]
    app.state.store.save(state, 0, 'Reviewer', 'Existing documents')
    response = client.post(PATH, headers=ORIGIN, json={'revision': 1})
    assert response.status_code == 200
    data = response.json()
    assert len(data['imported']) == 5 and data['failed'] == []
    assert data['skipped'] == ['demo/harborapi@3.0']
    assert data['workspace']['sources'][0] == existing.model_dump()
    assert data['workspace']['revision'] == 2


def test_guards_reject_untrusted_fields_before_loading(client, monkeypatch):
    client, app = client
    def unexpected():
        raise AssertionError('Must validate request before loading')
    monkeypatch.setattr(importlib.import_module('backend.app'), 'load_demo_documents', unexpected)
    assert client.post(PATH, json={'revision': 0}).status_code == 403
    assert client.post(PATH, headers=ORIGIN, json={'revision': 1}).status_code == 409
    for extra in ({'url': 'http://localhost/secrets'}, {'sql': 'DROP TABLE workspace'}, {'revision': True}):
        assert client.post(PATH, headers=ORIGIN, json={'revision': 0, **extra}).status_code == 422
    client.post('/api/logout', headers=ORIGIN)
    assert client.post(PATH, headers=ORIGIN, json={'revision': 0}).status_code == 401


def test_workspace_change_during_loading_cancels_import(client, monkeypatch):
    client, app = client
    def changed():
        state = app.state.store.read()
        state.title = 'Changed while loading'
        app.state.store.save(state, 0, 'Reviewer', 'Concurrent edit')
        return load_demo_documents()
    monkeypatch.setattr(importlib.import_module('backend.app'), 'load_demo_documents', changed)
    assert client.post(PATH, headers=ORIGIN, json={'revision': 0}).status_code == 409
    state = app.state.store.read()
    assert state.revision == 1 and state.sources == []


def test_capacity_failure_is_atomic(client):
    client, app = client
    state = app.state.store.read()
    state.sources = [Source.create(SourceInput(title=f'Existing {n}', version='1', text=f'Document {n}')) for n in range(25)]
    app.state.store.save(state, 0, 'Reviewer', 'Existing documents')
    before = app.state.store.read().model_dump()
    assert client.post(PATH, headers=ORIGIN, json={'revision': 1}).status_code == 422
    assert app.state.store.read().model_dump() == before


def test_session_expiry_during_loading_saves_nothing(client, monkeypatch):
    client, app = client
    original = time.time
    def expired():
        monkeypatch.setattr(time, 'time', lambda: original()+13*3600)
        return load_demo_documents()
    monkeypatch.setattr(importlib.import_module('backend.app'), 'load_demo_documents', expired)
    assert client.post(PATH, headers=ORIGIN, json={'revision': 0}).status_code == 401
    assert app.state.store.read().sources == []


@pytest.mark.parametrize('damage', ['missing', 'invalid-json', 'incomplete', 'hash', 'origin', 'repository', 'oversized', 'path-traversal', 'version'])
def test_missing_or_corrupt_bundle_saves_nothing(client, monkeypatch, tmp_path, damage):
    client, app = client
    import shutil
    bundle_dir = tmp_path/'bundle'
    shutil.copytree(BUNDLE_DIR, bundle_dir)
    path = bundle_dir/'manifest.json'
    manifest = json.loads(path.read_text())
    rows = manifest['documents']
    if damage == 'missing':
        path.unlink()
    elif damage == 'invalid-json':
        path.write_text('{')
    elif damage == 'oversized':
        path.write_text('x'*20_001)
    else:
        if damage == 'incomplete':
            rows.pop()
        elif damage == 'hash':
            (bundle_dir/rows[0]['path']).write_text('Tampered document')
        elif damage == 'origin':
            rows[0]['url'] = 'https://example.com/unrelated'
        elif damage == 'repository':
            rows[0]['repository'] = 'other/repository'
        elif damage == 'path-traversal':
            rows[0]['path'] = '../outside.md'
        elif damage == 'version':
            rows[0]['version'] = '4.0'
        path.write_text(json.dumps(manifest))
    monkeypatch.setattr(importlib.import_module('backend.demo_documents'), 'BUNDLE_DIR', bundle_dir)
    before = app.state.store.read().model_dump()
    response = client.post(PATH, headers=ORIGIN, json={'revision': 0})
    assert response.status_code == 503 and 'No sources were saved' in response.json()['detail']
    assert app.state.store.read().model_dump() == before


def test_bundle_preserves_original_synthetic_text_versions_and_reserved_origins():
    rows = load_demo_documents()
    assert len(rows) == 6
    for key, source in rows:
        repo, version = key.split('@')
        assert source.version == version
        assert source.url == f'https://example.invalid/{repo}/blob/v{version}/README.md'
        assert 2000 <= len(source.text) <= 5000
        assert 'fictional documentation' in source.text
        assert 'MIT' in source.license and 'Maryana Yurchyshyna' in source.license
    assert sorted({source.version for _, source in rows}) == ['1.0', '2.0', '3.0']
    assert len({source.sha256 for _, source in rows}) == 6


def test_synthetic_bundle_analyzes_into_topics_entities_and_same_version_conflict(client):
    client, app = client
    assert client.post(PATH, headers=ORIGIN, json={'revision': 0}).status_code == 200
    response = client.post('/api/analyze', headers=ORIGIN, json={'revision': 1})
    assert response.status_code == 200
    state = app.state.store.read()
    assert 30 < len(state.claims) < 150
    assert 2 <= len(state.topics) <= 4
    assert {source.id for source in state.sources} == {claim.source_id for claim in state.claims}
    kinds = {mention.kind for claim in state.claims for mention in claim.document.mentions}
    assert {'endpoint', 'configuration', 'api', 'package'} <= kinds
    by_id = {claim.id: claim for claim in state.claims}
    sources = {source.id: source for source in state.sources}
    pairs = [(claim, by_id[other]) for claim in state.claims for other in claim.conflicts]
    assert pairs
    assert all(sources[a.source_id].version == sources[b.source_id].version for a,b in pairs)
    assert any('retry_limit' in a.quote and 'retry_limit' in b.quote and sources[a.source_id].version == '2.0' for a,b in pairs)
    for claim in state.claims:
        assert sources[claim.source_id].text[claim.start:claim.end] == claim.quote
