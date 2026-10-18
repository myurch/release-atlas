"""OpenAI wire contracts and safety boundaries, using synthetic mocked responses."""
import json
from pathlib import Path

import httpx
import pytest

from backend.assistant import AssistantRequest, assist
from backend.models import Workspace
from backend.providers import ProviderConfig, ProviderError, generate


def response(answer):
    return {'status': 'completed', 'output': [
        {'type': 'reasoning', 'summary': []},
        {'type': 'message', 'role': 'assistant', 'content': [
            {'type': 'output_text', 'text': json.dumps(answer)}]}]}


def config():
    return ProviderConfig(key='synthetic-test-key')


def test_environment_defaults_and_secret_scope(monkeypatch):
    for name in ['ATLAS_LLM_KIND', 'ATLAS_LLM_BASE', 'ATLAS_LLM_MODEL', 'ATLAS_LLM_KEY']:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-test-key')
    actual = ProviderConfig.environment()
    assert actual.kind == 'openai' and actual.model == 'gpt-6-luna'
    assert actual.base == 'https://api.openai.com/v1' and actual.key == 'synthetic-test-key'
    assert actual.key not in repr(actual)
    monkeypatch.setenv('ATLAS_LLM_KEY', 'override')
    assert ProviderConfig.environment().key == 'override'
    monkeypatch.delenv('ATLAS_LLM_KEY')
    monkeypatch.setenv('ATLAS_LLM_KIND', 'ollama')
    actual = ProviderConfig.environment()
    assert actual.key == '' and actual.model == 'gemma4:12b'
    assert actual.base == 'http://localhost:11434'
    with pytest.raises(ValueError, match='OpenAI provider requires'):
        ProviderConfig(base='https://another-provider.invalid/v1', key='secret').validate()


@pytest.mark.asyncio
async def test_luna_chat_wire_contract_and_read_only_context():
    state = Workspace(title='Synthetic review')
    before = state.model_dump()
    def handle(request):
        assert str(request.url) == 'https://api.openai.com/v1/responses'
        assert request.headers['authorization'] == 'Bearer synthetic-test-key'
        payload = json.loads(request.content)
        assert payload['model'] == 'gpt-6-luna'
        assert payload['store'] is False and payload['stream'] is False
        assert payload['reasoning'] == {'effort': 'none'}
        assert payload['max_output_tokens'] == 1500
        assert not {'temperature', 'max_tokens', 'previous_response_id'} & payload.keys()
        assert [tool['name'] for tool in payload['tools']] == ['calculate']
        assert payload['parallel_tool_calls'] is False
        fmt = payload['text']['format']
        assert fmt['type'] == 'json_schema' and fmt['strict'] is True
        assert fmt['schema']['additionalProperties'] is False
        assert set(fmt['schema']['required']) == {'answer', 'citations', 'uncertainty', 'source_citations'}
        assert 'synthetic-test-key' not in json.dumps(payload)
        assert 'default' not in fmt['schema']['properties']['citations']
        assert fmt['schema']['properties']['citations']['maxItems'] == 0
        assert fmt['schema']['properties']['source_citations']['maxItems'] == 0
        return httpx.Response(200, json=response({'answer': 'No sources are saved.', 'citations': [], 'uncertainty': ''}))
    answer = await assist(config(), state, AssistantRequest(revision=0, message='Do you see sources?'), httpx.MockTransport(handle))
    assert answer.answer == 'No sources are saved.' and state.model_dump() == before


@pytest.mark.asyncio
async def test_luna_generation_and_citation_validation():
    evidence = [{'claim': {'id': 'c-synthetic', 'quote': 'Added `new_api`.'}}]
    def handle(request):
        payload = json.loads(request.content)
        assert payload['max_output_tokens'] == 1200
        assert payload['text']['format']['schema']['properties']['citations']['items']['enum'] == ['c-synthetic']
        return httpx.Response(200, json=response({'answer': 'A new API was added.', 'citations': ['c-synthetic'], 'uncertainty': 'Check your usage.'}))
    assert (await generate(config(), 'What changed?', evidence, httpx.MockTransport(handle))).citations == ['c-synthetic']
    bad = response({'answer': 'Unsupported.', 'citations': ['invented'], 'uncertainty': ''})
    with pytest.raises(ProviderError, match='outside the retrieved set'):
        await generate(config(), 'What changed?', evidence, httpx.MockTransport(lambda r: httpx.Response(200, json=bad)))


@pytest.mark.asyncio
async def test_source_citation_schema_uses_only_current_passage_ids():
    from backend.models import Source, SourceInput
    state = Workspace(sources=[Source.create(SourceInput(title='Synthetic count', version='1', text='There are 8 bagels.'))])
    def handle(request):
        payload = json.loads(request.content)
        context = json.loads(payload['input'][1]['content'])['context']
        identifiers = [p['id'] for p in context['source_passages']]
        properties = payload['text']['format']['schema']['properties']
        assert properties['source_citations']['items']['enum'] == identifiers
        assert properties['citations']['maxItems'] == 0
        return httpx.Response(200, json=response({'answer':'There are 8 bagels.', 'citations':[],
                                                 'uncertainty':'', 'source_citations':identifiers}))
    result = await assist(config(), state, AssistantRequest(revision=0, message='How many?'), httpx.MockTransport(handle))
    assert result.source_passages[0].quote == state.sources[0].text


@pytest.mark.asyncio
async def test_luna_conflict_pairs_still_require_both_citations():
    state = Workspace.model_validate_json(Path('data/demo-snapshot.json').read_text())
    claim = next(c for c in state.claims if c.conflicts)
    query = AssistantRequest(revision=state.revision, message='Explain the conflict.', selected_claim=claim.id)
    for citations, rejected in [([claim.id], True), ([claim.id, claim.conflicts[0]], False)]:
        body = response({'answer': 'The sources disagree.', 'citations': citations, 'uncertainty': ''})
        transport = httpx.MockTransport(lambda r: httpx.Response(200, json=body))
        if rejected:
            with pytest.raises(ProviderError, match='opposing evidence'):
                await assist(config(), state, query, transport)
        else:
            assert len((await assist(config(), state, query, transport)).citations) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('body', [
    {'status': 'incomplete', 'output': []},
    {'status': 'failed', 'error': {'message': 'private provider details'}},
    {'status': 'completed', 'output': None},
    {'status': 'completed', 'output': [None]},
    {'status': 'completed', 'output': []},
    {'status': 'completed', 'output': [{'type': 'message', 'role': 'assistant', 'content': [{'type': 'refusal', 'refusal': 'private details'}]}]},
    {'status': 'completed', 'output': [{'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'not JSON'}]}]},
    response({'answer': 'x' * 4001, 'citations': [], 'uncertainty': ''}),
])
async def test_luna_rejects_incomplete_refused_and_invalid_answers(body):
    state = Workspace()
    with pytest.raises(ProviderError) as caught:
        await assist(config(), state, AssistantRequest(revision=0, message='Help'), httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    assert 'private' not in str(caught.value) and state.revision == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('status, expected', [(401, 'API key'), (403, 'permissions'), (404, 'unavailable'), (429, 'billing'), (503, 'HTTP 503')])
async def test_luna_actionable_errors_do_not_echo_provider_data(status, expected):
    transport = httpx.MockTransport(lambda r: httpx.Response(status, json={'error': {'message': 'synthetic-test-key private prompt'}}))
    with pytest.raises(ProviderError, match=expected) as caught:
        await assist(config(), Workspace(), AssistantRequest(revision=0, message='Help'), transport)
    assert 'synthetic-test-key' not in str(caught.value) and 'private prompt' not in str(caught.value)


@pytest.mark.asyncio
async def test_missing_key_never_makes_a_request():
    def unexpected(request):
        pytest.fail('A missing key must not send a request')
    with pytest.raises(ProviderError, match='OPENAI_API_KEY'):
        await assist(ProviderConfig(), Workspace(), AssistantRequest(revision=0, message='Help'), httpx.MockTransport(unexpected))
