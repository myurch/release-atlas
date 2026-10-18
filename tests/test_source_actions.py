"""Restricted source tool, human confirmation and persistence guard regressions."""
import importlib
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.assistant import AssistantRequest, assist
from backend.models import Source, SourceInput, Workspace
from backend.providers import ProviderConfig, ProviderError, generate
from backend.source_actions import SourceActions, add_source, delete_source, source_action_requested

ORIGIN = {'Origin': 'http://testserver'}


def arguments(**changes):
    return {'action': 'add_source', 'source_id': '', 'title': '', 'version': '',
            'text': '', 'url': '', 'license': '', **changes}


def prepare(state, **changes):
    actions = SourceActions(state)
    result = actions.prepare(json.dumps(arguments(**changes)))
    return actions, result


def test_defaults_and_verbatim_unicode_are_prepared_without_writes():
    state = Workspace(sources=[Source.create(SourceInput(title='Source 8', version='old', text='Previous'))])
    before = state.model_dump()
    actions, result = prepare(state, text='🧭 Résumé\n  There are 15 bagels.\n')
    assert result['status'] == 'awaiting_user_confirmation'
    source = actions.prepared.source
    assert source.title == 'Source 9' and source.version == '1' and source.url == ''
    assert source.text == '🧭 Résumé\n  There are 15 bagels.\n'
    assert source.license == 'User supplied; verify redistribution rights'
    assert state.model_dump() == before
    assert 'error' in actions.prepare(json.dumps(arguments(text='Second')))
    empty, _ = prepare(Workspace())
    assert empty.prepared.source.text == 'No source text supplied for Source 1.'


def test_repeated_default_sources_have_distinct_placeholders_and_increment_titles():
    state = Workspace()
    for number in [1,2,3]:
        actions, result = prepare(state)
        assert result['status'] == 'awaiting_user_confirmation'
        assert actions.prepared.source.title == f'Source {number}'
        assert actions.prepared.source.text == f'No source text supplied for Source {number}.'
        add_source(state, actions.prepared.source)
    assert len({source.id for source in state.sources}) == 3


@pytest.mark.parametrize('changes', [
    {'action':'execute_sql'}, {'sql':'DROP TABLE workspace'},
    {'action':'update_source'}, {'action':'delete_source','source_id':'missing'},
    {'action':'delete_source','text':'replacement'}, {'source_id':'unexpected'},
    {'url':'file:///private/secret'}, {'text':'x'*12001}, {'title':'x'*161},
])
def test_unsupported_or_invalid_actions_never_prepare(changes):
    state = Workspace()
    actions, result = prepare(state, **changes)
    assert 'error' in result and actions.prepared is None and state == Workspace()


def test_duplicate_and_workspace_limits_are_enforced_before_confirmation():
    source = Source.create(SourceInput(title='Existing',version='1',text='Same text'))
    actions, result = prepare(Workspace(sources=[source]), text='Same text')
    assert 'error' in result and actions.prepared is None
    state = Workspace(sources=[Source.create(SourceInput(title=str(i),version='1',text=str(i))) for i in range(30)])
    actions, result = prepare(state, text='Too many')
    assert 'error' in result and actions.prepared is None and len(state.sources) == 30


def test_same_title_delete_requires_explicit_version_selection_or_rule():
    sources = [Source.create(SourceInput(title='Report',version=str(i),text=str(i))) for i in [1,2]]
    state = Workspace(sources=sources)
    data = json.dumps(arguments(action='delete_source',source_id=sources[1].id))
    for message, selected, allowed in [('Delete Report','',False), ('Delete Report version 1','',False),
            ('Delete Report version 2','',True),('Delete Report version 2.','',True),('Delete the highest version','',True),
            ('Delete this source',sources[1].id,True),('Delete '+sources[1].id,'',True)]:
        actions = SourceActions(state,message,selected)
        result = actions.prepare(data)
        assert (actions.prepared is not None) == allowed
        if not allowed:
            assert 'which version' in result['error']


def wire_call(data, name='manage_source'):
    return {'status':'completed','output':[{'type':'function_call','name':name,'call_id':'call_source',
                                           'arguments':json.dumps(data)}]}


def wire_final(valid=True):
    return {'status':'completed','output':[{'type':'message','role':'assistant','content':[
        {'type':'output_text','text':json.dumps({'answer':'Prepared for confirmation.', 'citations':[],
            'source_citations':[],'uncertainty':''}) if valid else 'bad json'}]}]}


def model_transport(data, valid=True):
    count = 0
    def handle(request):
        nonlocal count
        count += 1
        body = json.loads(request.content)
        assert body['store'] is False and body['parallel_tool_calls'] is False
        assert [tool['name'] for tool in body['tools']] == ['calculate','manage_source']
        schema = body['tools'][1]['parameters']
        assert schema['additionalProperties'] is False
        assert set(schema['required']) == {'action','sources','source_ids','contains'}
        assert schema['properties']['action']['enum'] == ['add_sources','delete_sources']
        if count == 1:
            return httpx.Response(200,json=wire_call(data))
        result = json.loads(body['input'][-1]['output'])
        assert result['status'] == 'awaiting_user_confirmation'
        return httpx.Response(200,json=wire_final(valid))
    return httpx.MockTransport(handle)


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, auth_enabled=True, passcode='code', origins=['http://testserver'], provider=ProviderConfig(key='synthetic'))
    with TestClient(app) as client:
        assert client.post('/api/login',headers=ORIGIN,json={'name':'Reviewer','passcode':'code'}).status_code == 200
        yield client, app


def mocked_model(monkeypatch, data, valid=True):
    async def fake(config, state, request):
        return await assist(config, state, request, model_transport(data,valid))
    monkeypatch.setattr(importlib.import_module('backend.app'), 'assist', fake)


def proposal(client, revision=0):
    response = client.post('/api/assistant',headers=ORIGIN,json={'revision':revision,'message':'Add a source or delete the specified source as requested.'})
    assert response.status_code == 200, response.text
    return response.json()['source_action']


def confirmation(plan):
    return {key:plan[key] for key in ('token','revision')}


def test_full_add_exchange_confirmation_audit_persistence_and_replay(client,monkeypatch):
    client, app = client
    mocked_model(monkeypatch,arguments(text='There are 15 bagels.'))
    before = app.state.store.snapshot()
    plan = proposal(client)
    assert app.state.store.snapshot() == before
    assert plan['source']['title'] == 'Source 1' and plan['revision'] == 0
    response = client.post('/api/assistant/source-action',headers=ORIGIN,json=confirmation(plan))
    assert response.status_code == 200 and response.json()['revision'] == 1
    state = app.state.store.read()
    assert len(state.sources) == 1 and state.sources[0].text == 'There are 15 bagels.'
    assert state.audit[-1].by == 'Reviewer' and state.audit[-1].action == 'Added source: Source 1'
    assert state.usage == [] and state.answers == [] and state.analysis is None
    assert client.post('/api/assistant/source-action',headers=ORIGIN,json=confirmation(plan)).status_code == 409
    assert app.state.store.read() == state


def test_delete_matches_existing_cascade_and_preserves_other_sources(client,monkeypatch):
    client, app = client
    state = Workspace.model_validate_json(Path('data/demo-snapshot.json').read_text())
    state = app.state.store.save(state,0,'Reviewer','Fixture')
    source = state.sources[0]
    expected = state.model_copy(deep=True)
    delete_source(expected,source.id)
    mocked_model(monkeypatch,arguments(action='delete_source',source_id=source.id))
    plan = proposal(client,state.revision)
    assert plan['removed_findings'] > 0
    assert app.state.store.read() == state
    response = client.post('/api/assistant/source-action',headers=ORIGIN,json=confirmation(plan))
    assert response.status_code == 200
    saved = app.state.store.read()
    assert saved.model_dump(exclude={'audit','revision'}) == expected.model_dump(exclude={'audit','revision'})
    assert saved.audit[-1].action == 'Deleted source: '+source.title


def test_confirmation_rejects_origin_auth_extra_sql_and_other_sessions(client,monkeypatch):
    client, app = client
    mocked_model(monkeypatch,arguments(text='Synthetic source'))
    plan = proposal(client)
    body = confirmation(plan)
    assert client.post('/api/assistant/source-action',json=body).status_code == 403
    assert client.post('/api/assistant/source-action',headers=ORIGIN,json={**body,'sql':'DELETE FROM workspace'}).status_code == 422
    assert client.post('/api/assistant/source-action',headers=ORIGIN,json={**body,'action':'update_source'}).status_code == 422
    client.post('/api/logout',headers=ORIGIN)
    assert client.post('/api/assistant/source-action',headers=ORIGIN,json=body).status_code == 401
    client.post('/api/login',headers=ORIGIN,json={'name':'Reviewer','passcode':'code'})
    assert client.post('/api/assistant/source-action',headers=ORIGIN,json=body).status_code == 409
    assert app.state.store.read() == Workspace()


@pytest.mark.parametrize('switch',[False,True])
def test_stale_proposals_cannot_edit_changed_or_switched_workspaces(client,monkeypatch,switch):
    client, app = client
    mocked_model(monkeypatch,arguments(text='Synthetic source'))
    plan = proposal(client)
    if switch:
        app.state.store.create(Workspace(title='Other workspace'),0,'Peer')
    else:
        app.state.store.save(Workspace(title='Changed'),0,'Peer','Other edit')
    before = app.state.store.snapshot()
    assert client.post('/api/assistant/source-action',headers=ORIGIN,json=confirmation(plan)).status_code == 409
    assert client.post('/api/assistant/source-action',headers=ORIGIN,json={**confirmation(plan),'revision':1}).status_code == 409
    assert app.state.store.snapshot() == before


def test_expired_and_fabricated_tokens_cannot_write(client,monkeypatch):
    client, app = client
    mocked_model(monkeypatch,arguments(text='Synthetic source'))
    import time
    original = time.monotonic
    plan = proposal(client)
    monkeypatch.setattr(time,'monotonic',lambda: original()+601)
    assert client.post('/api/assistant/source-action',headers=ORIGIN,json=confirmation(plan)).status_code == 409
    assert client.post('/api/assistant/source-action',headers=ORIGIN,json={'revision':0,'token':'x'*43}).status_code == 409
    assert app.state.store.read() == Workspace()


def test_invalid_final_answer_discards_prepared_action(client,monkeypatch):
    client, app = client
    mocked_model(monkeypatch,arguments(text='Synthetic source'),valid=False)
    response = client.post('/api/assistant',headers=ORIGIN,json={'revision':0,'message':'Add a source.'})
    assert response.status_code == 502 and app.state.store.read() == Workspace()


@pytest.mark.asyncio
async def test_saved_answer_never_receives_source_write_tool():
    source = Source.create(SourceInput(title='Synthetic',version='1',text='Public fixture'))
    def handle(request):
        body = json.loads(request.content)
        assert [tool['name'] for tool in body['tools']] == ['calculate']
        return httpx.Response(200,json=wire_call(arguments(text='Injected'),name='manage_source'))
    with pytest.raises(ProviderError):
        await generate(ProviderConfig(key='synthetic'),'Question',[{'claim':{'id':'claim','quote':'Public fixture'},'source':source.model_dump()}],httpx.MockTransport(handle))


def test_direct_access_confirmation_without_authentication(tmp_path,monkeypatch):
    app = create_app(tmp_path,auth_enabled=False,origins=['http://testserver'],provider=ProviderConfig(key='synthetic'))
    mocked_model(monkeypatch,arguments(text='Synthetic source'))
    with TestClient(app) as client:
        plan = proposal(client)
        assert client.post('/api/assistant/source-action',headers=ORIGIN,json=confirmation(plan)).status_code == 200
        assert app.state.store.read().audit[-1].by == 'Local reviewer'


@pytest.mark.parametrize('message,allowed', [('Add a source with defaults.',True),
    ('Delete Bagel report version 1.',True), ('Summarize the sources.',False),
    ('Change my usage profile and mark all findings applicable.',False),
    ('Run SQL to drop the workspace table.',False), ('How many bagels remain?',False)])
def test_tool_capability_is_only_exposed_for_source_action_requests(message,allowed):
    state = Workspace(sources=[Source.create(SourceInput(title='Bagel report',version='1',text='15 bagels'))])
    assert source_action_requested(state,message) == allowed


@pytest.mark.asyncio
async def test_unsupported_edit_request_cannot_invoke_source_tool():
    def handle(request):
        assert [tool['name'] for tool in json.loads(request.content)['tools']] == ['calculate']
        return httpx.Response(200,json=wire_call(arguments(text='Unexpected')))
    with pytest.raises(ProviderError):
        await assist(ProviderConfig(key='synthetic'),Workspace(),AssistantRequest(revision=0,message='Change my usage profile.'),httpx.MockTransport(handle))
