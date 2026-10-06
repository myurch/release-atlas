"""Assistant boundaries: bounded model context, read-only requests and stale sessions."""
import importlib
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.assistant import AssistantAnswer, AssistantRequest, assist, assistant_context
from backend.models import Workspace
from backend.providers import ProviderConfig, ProviderError

ORIGIN = {'Origin': 'http://testserver'}


def demo():
    return Workspace.model_validate_json(Path('data/demo-snapshot.json').read_text())


def test_context_selects_evidence_and_never_sends_stale_findings():
    state = demo()
    request = AssistantRequest(revision=state.revision, page='Evidence', selected_claim=state.claims[-1].id, message='What does this mean?')
    context = assistant_context(state, request)
    assert context['analysis_ready'] and context['evidence'][0]['id'] == state.claims[-1].id
    assert len(context['evidence']) <= 8
    assert all(len(c['quote']) <= 2000 for c in context['evidence'])
    assert 'audit' not in context and 'answers' not in context
    request.selected_claim = ''
    request.selected_source = state.sources[-1].id
    context = assistant_context(state, request)
    assert context['evidence'][0]['source']['title'] == state.sources[-1].title
    state.usage = []
    context = assistant_context(state, request)
    assert not context['analysis_ready'] and context['evidence'] == [] and context['finding_count'] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['ollama', 'compatible'])
async def test_provider_contract_citations_and_text_limits(kind):
    state = demo()
    claim = next(c.id for c in state.claims if not c.conflicts)
    query = AssistantRequest(revision=state.revision, message='Explain this.', selected_claim=claim)
    def transport(content):
        def response(request):
            payload = json.loads(request.content)
            assert payload['stream'] is False
            assert len(payload['messages']) == 2 and payload['messages'][0]['role'] == 'system'
            data = json.loads(payload['messages'][1]['content'])
            assert data['context']['selected_claim'] == claim
            assert 'api_key' not in data
            body = {'message': {'content': content}} if kind == 'ollama' else {'choices': [{'message': {'content': content}}]}
            return httpx.Response(200, json=body)
        return httpx.MockTransport(response)
    config = ProviderConfig(kind=kind, model='test')
    answer = await assist(config, state, query, transport(json.dumps({'answer': 'Read this passage.', 'citations': [claim, claim]})))
    assert answer.citations == [claim]
    for content in ['not JSON', json.dumps({'answer': 'Unsupported', 'citations': ['missing']}), json.dumps({'answer': 'x' * 4001}), json.dumps({'answer': 'Hello', 'extra': 'bad'})]:
        with pytest.raises(ProviderError):
            await assist(config, state, query, transport(content))
    guide = await assist(config, state, query, transport('{"answer":"Open Sources","citations":[]}'))
    assert guide.citations == []


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, passcode='test-code', origins=['http://testserver'])
    with TestClient(app) as client:
        assert client.post('/api/login', json={'name': 'Reviewer', 'passcode': 'test-code'}, headers=ORIGIN).status_code == 200
        yield client, app


def test_chat_is_read_only_and_rejects_invalid_context(client, monkeypatch):
    client, app = client
    calls = []
    async def fake(config, state, request):
        calls.append(request)
        return AssistantAnswer(answer='Add release notes in Sources.')
    monkeypatch.setattr(importlib.import_module('backend.app'), 'assist', fake)
    before = app.state.store.snapshot()
    data = {'revision': 0, 'page': 'Overview', 'message': 'How do I start?'}
    reply = client.post('/api/assistant', json=data, headers=ORIGIN)
    assert reply.status_code == 200 and reply.json()['revision'] == 0
    assert app.state.store.snapshot() == before
    for edit, status in [({'revision': 1}, 409), ({'message': '   '}, 422), ({'message': 'x' * 2001}, 422), ({'selected_claim': 'missing'}, 422), ({'selected_source': 'missing'}, 422), ({'page': 'Secret'}, 422), ({'history': [{'role': 'system', 'content': 'bad'}]}, 422), ({'history': [{'role': 'user', 'content': 'q'}] * 11}, 422)]:
        assert client.post('/api/assistant', json={**data, **edit}, headers=ORIGIN).status_code == status
    assert client.post('/api/assistant', json=data).status_code == 403
    assert len(calls) == 1 and app.state.store.snapshot() == before
    client.post('/api/logout', headers=ORIGIN)
    assert client.post('/api/assistant', json=data, headers=ORIGIN).status_code == 401


def test_chat_rejects_response_if_workspace_switches_during_generation(client, monkeypatch):
    client, app = client
    async def switch(config, state, request):
        app.state.store.create(Workspace(title='Different review'), state.revision, 'Peer')
        return AssistantAnswer(answer='Old response must not reach new review')
    monkeypatch.setattr(importlib.import_module('backend.app'), 'assist', switch)
    reply = client.post('/api/assistant', json={'revision': 0, 'message': 'Explain'}, headers=ORIGIN)
    assert reply.status_code == 409
    state = app.state.store.read()
    assert state.title == 'Different review' and state.revision == 1 and state.answers == []


def test_provider_failure_does_not_modify_workspace(client, monkeypatch):
    client, app = client
    before = app.state.store.snapshot()
    async def failed(*args):
        raise ProviderError('Model is unavailable')
    monkeypatch.setattr(importlib.import_module('backend.app'), 'assist', failed)
    reply = client.post('/api/assistant', json={'revision': 0, 'message': 'Explain'}, headers=ORIGIN)
    assert reply.status_code == 502 and app.state.store.snapshot() == before


@pytest.mark.asyncio
async def test_model_cannot_silently_cite_only_one_side_of_a_known_conflict():
    state = demo()
    claim = next(c for c in state.claims if c.conflicts)
    request = AssistantRequest(revision=state.revision, message='Compare the conflicting passages', selected_claim=claim.id)
    context = assistant_context(state, request)
    assert context['conflicts']
    for citations, rejected in [([claim.id], True), ([claim.id, claim.conflicts[0]], False)]:
        transport = httpx.MockTransport(lambda r: httpx.Response(200, json={'message': {'content': json.dumps({'answer': 'The documents disagree.', 'citations': citations})}}))
        if rejected:
            with pytest.raises(ProviderError, match='opposing evidence'):
                await assist(ProviderConfig(), state, request, transport)
        else:
            answer = await assist(ProviderConfig(), state, request, transport)
            assert 'conflicting statements' in answer.uncertainty


@pytest.mark.asyncio
async def test_inflight_chat_rechecks_auth_and_prevents_overlapping_model_calls(tmp_path, monkeypatch):
    import asyncio
    app = create_app(tmp_path, passcode='test-code', origins=['http://testserver'])
    started, finish = asyncio.Event(), asyncio.Event()
    async def held(*args):
        started.set()
        await finish.wait()
        return AssistantAnswer(answer='Must not be delivered after logout')
    monkeypatch.setattr(importlib.import_module('backend.app'), 'assist', held)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://testserver', headers=ORIGIN) as client:
        assert (await client.post('/api/login', json={'name': 'Reviewer', 'passcode': 'test-code'})).status_code == 200
        before = app.state.store.snapshot()
        data = {'revision': 0, 'message': 'Help'}
        first = asyncio.create_task(client.post('/api/assistant', json=data))
        await asyncio.wait_for(started.wait(), 2)
        assert (await client.post('/api/assistant', json=data)).status_code == 409
        assert (await client.post('/api/logout')).status_code == 200
        finish.set()
        assert (await first).status_code == 401
        assert app.state.store.snapshot() == before
