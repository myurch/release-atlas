"""Atomic source batches and literal full-text deletion without SQL/filter execution."""
import importlib
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.assistant import AssistantReply, AssistantRequest, assist, assistant_context
from backend.models import Answer, Source, SourceInput, Workspace
from backend.providers import ProviderConfig
from backend.source_actions import SourceActions, delete_source, tool_definition

ORIGIN = {'Origin':'http://testserver'}


def fields(**changes):
    return {'title':'','version':'','text':'','url':'','license':'',**changes}


def arguments(action='delete_sources',**changes):
    return {**fields(),'action':action,'source_id':'','sources':[],'source_ids':[],'contains':'',**changes}


def state_with_sources():
    return Workspace(sources=[Source.create(SourceInput(title=title,version=str(i),text=text))
        for i,(title,text) in enumerate([('Apple guide','We have APPLES.'),('Pears','Only pears.'),('Apples in title','No fruit here.')])])


def test_literal_filter_searches_all_full_sources_and_returns_bounded_model_metadata():
    state = Workspace(sources=[Source.create(SourceInput(title=f'Notes {i}',version=str(i),
        text='x'*9000+(' APPLES.' if i%2 == 0 else ' pears.'))) for i in range(30)])
    request = AssistantRequest(revision=0,message='Delete all sources that mention apples.')
    assert assistant_context(state,request)['source_coverage']['partial']
    before = state.model_dump()
    actions = SourceActions(state,request.message)
    result = actions.prepare(json.dumps(arguments(contains='apples')))
    assert result['status'] == 'awaiting_user_confirmation' and result['count'] == 15
    assert [item.source_id for item in actions.prepared.items] == [s.id for s in state.sources[::2]]
    assert len(json.dumps(result)) < 10000 and 'xxxxxxxxxx' not in json.dumps(result)
    assert all('source' not in item for item in result['items'])
    assert state.model_dump() == before


@pytest.mark.parametrize('term',['%', '_', '.*', "' OR 1=1 --"])
def test_filter_treats_sql_wildcards_quotes_and_regex_as_literal_text(term):
    state = Workspace(sources=[Source.create(SourceInput(title='Example',version='1',text='Literal '+term)),
                               Source.create(SourceInput(title='Other',version='2',text='Ordinary text'))])
    actions = SourceActions(state,'Delete all sources containing '+term)
    result = actions.prepare(json.dumps(arguments(contains=term)))
    assert result['count'] == 1 and actions.prepared.items[0].source_id == state.sources[0].id


def test_literal_whitespace_is_not_trimmed_into_a_broader_filter():
    state = Workspace(sources=[Source.create(SourceInput(title='Exact',version='1',text='Some apples here.')),
        Source.create(SourceInput(title='Other',version='2',text='pineapples'))])
    actions = SourceActions(state,'Delete all sources containing exactly " apples ".')
    result = actions.prepare(json.dumps(arguments(contains=' apples ')))
    assert result['count'] == 1 and actions.prepared.match_text == ' apples '
    assert actions.prepared.items[0].source_id == state.sources[0].id


def test_batch_defaults_increment_within_the_batch_and_preserve_unicode_text():
    state = Workspace()
    actions = SourceActions(state,'Create three sources.')
    result = actions.prepare(json.dumps(arguments('add_sources',sources=[fields(),fields(text='🧭 Café\r\n\t15 apples.'),fields()])))
    assert result['count'] == 3 and state.sources == []
    assert [item.source.title for item in actions.prepared.items] == ['Source 1','Source 2','Source 3']
    assert actions.prepared.items[1].source.text == '🧭 Café\r\n\t15 apples.'
    assert len({item.source_id for item in actions.prepared.items}) == 3
    assert 'error' in actions.prepare(json.dumps(arguments('add_sources',sources=[fields()])))


def test_explicit_source_text_cannot_be_silently_replaced_by_defaults():
    actions = SourceActions(Workspace(),'Add a source containing exactly: There are 8 apples.')
    result = actions.prepare(json.dumps(arguments('add_sources',sources=[fields()])))
    assert 'supplied source text' in result['error'] and actions.prepared is None
    assert actions.prepare(json.dumps(arguments('add_sources',sources=[fields(text='There are 8 apples.')])) )['count'] == 1


@pytest.mark.parametrize('data',[
    arguments(), arguments(contains=' '), arguments(contains='not supplied by the user'),
    arguments(contains='apples',source_ids=['s-missing']), arguments(source_ids=['s-missing']),
    arguments(contains='apples',text='replace'), arguments(contains='apples',source_id='s-missing'),
    arguments('add_sources'), arguments('add_sources',sources=[fields()]*31),
    arguments('add_sources',sources=[fields(),fields(url='javascript:alert(1)')]),
    arguments('add_sources',sources=[fields(text='same'),fields(text='same')]),
    arguments('add_sources',sources=[fields(text='valid'),fields(text='invalid\x00')]),
    arguments('add_sources',sources=[fields()],contains='apples'),
])
def test_invalid_batch_is_rejected_without_partial_changes(data):
    state = state_with_sources()
    before = state.model_dump()
    actions = SourceActions(state,'Delete all sources that mention apples, or create sources.')
    assert 'error' in actions.prepare(json.dumps(data)) and actions.prepared is None
    assert state.model_dump() == before


def test_no_matches_does_not_prepare_deletion_and_empty_filter_is_not_delete_all():
    actions = SourceActions(state_with_sources(),'Delete sources mentioning bananas.')
    assert 'No saved source' in actions.prepare(json.dumps(arguments(contains='bananas')))['error']
    assert actions.prepared is None
    assert 'error' in actions.prepare(json.dumps(arguments()))


def test_duplicate_ids_and_capacity_overflow_reject_the_entire_batch():
    state = state_with_sources()
    actions = SourceActions(state,'Delete these sources.')
    ids = [state.sources[0].id]*2
    assert 'error' in actions.prepare(json.dumps(arguments(source_ids=ids)))
    state = Workspace(sources=[Source.create(SourceInput(title=str(i),version=str(i),text=str(i))) for i in range(29)])
    actions = SourceActions(state,'Create two sources.')
    assert 'error' in actions.prepare(json.dumps(arguments('add_sources',sources=[fields(),fields()])))
    assert actions.prepared is None and len(state.sources) == 29


def test_single_id_batch_cannot_bypass_ambiguous_single_delete_guard():
    state = Workspace(sources=[Source.create(SourceInput(title='Report',version=str(i),text=str(i))) for i in [1,2]])
    actions = SourceActions(state,'Delete Report.')
    assert 'which version' in actions.prepare(json.dumps(arguments(source_ids=[state.sources[1].id])))['error']
    assert 'which version' in actions.prepare(json.dumps(arguments(source_ids=[s.id for s in state.sources])))['error']
    assert 'Several sources match' in actions.prepare(json.dumps(arguments(contains='Report')))['error']


def test_batch_deletion_counts_shared_answers_once_and_preserves_surviving_evidence():
    state = Workspace.model_validate_json(Path('data/demo-snapshot.json').read_text())
    ids = [s.id for s in state.sources[:2]]
    claims = [next(c.id for c in state.claims if c.source_id == source_id) for source_id in ids]
    survivor = next(c.id for c in state.claims if c.source_id not in ids)
    state.answers = [Answer(id='shared',question='Q',answer='A',citations=claims,uncertainty='',method='fixture',at=''),
                     Answer(id='survives',question='Q',answer='A',citations=[survivor],uncertainty='',method='fixture',at='')]
    actions = SourceActions(state,'Delete these two sources.')
    actions.prepare(json.dumps(arguments(source_ids=ids)))
    assert actions.prepared.removed_answers == 1
    expected = state.model_copy(deep=True)
    for source_id in ids:
        delete_source(expected,source_id)
    assert actions.prepared.removed_findings == len(state.claims)-len(expected.claims)
    assert len(state.answers) == 2 and expected.answers[0].id == 'survives'


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path,auth_enabled=True,passcode='code',origins=['http://testserver'],provider=ProviderConfig(key='synthetic'))
    with TestClient(app) as client:
        client.post('/api/login',headers=ORIGIN,json={'name':'Reviewer','passcode':'code'})
        yield client,app


def mock_model(monkeypatch,data):
    async def fake(config,state,request):
        calls = 0
        def handle(http_request):
            nonlocal calls
            calls += 1
            body = json.loads(http_request.content)
            if calls == 1:
                tool = body['tools'][1]
                assert tool['name'] == 'manage_source' and tool['strict']
                assert set(tool['parameters']['required']) == set(tool['parameters']['properties'])
                assert set(tool['parameters']['$defs']['SourceFields']['required']) == set(fields())
                public = {key:data[key] for key in ['action','sources','source_ids','contains']}
                output = [{'type':'function_call','name':'manage_source','call_id':'batch-call','arguments':json.dumps(public)}]
            else:
                result = json.loads(body['input'][-1]['output'])
                assert result['status'] == 'awaiting_user_confirmation'
                output = [{'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps(
                    {'answer':'Prepared, not saved.','citations':[],'source_citations':[],'uncertainty':''})}]}]
            return httpx.Response(200,json={'status':'completed','output':output})
        return await assist(config,state,request,httpx.MockTransport(handle))
    monkeypatch.setattr(importlib.import_module('backend.app'),'assist',fake)


def proposal(client,revision=0,message='Create multiple sources.'):
    response = client.post('/api/assistant',headers=ORIGIN,json={'revision':revision,'message':message})
    assert response.status_code == 200,response.text
    plan = response.json()['source_action']
    return plan, {'revision':revision,'token':plan['token'],'source_ids':[i['source_id'] for i in plan['items']]}


def test_real_adapter_batch_add_commits_once_and_rejects_replay(client,monkeypatch):
    client,app = client
    mock_model(monkeypatch,arguments('add_sources',sources=[fields(text='Apples'),fields(text='Pears')]))
    plan,body = proposal(client)
    assert len(plan['items']) == 2 and app.state.store.read().sources == []
    before = app.state.store.snapshot()
    for ids in [None, [], body['source_ids'][:1], list(reversed(body['source_ids']))]:
        altered = {key:value for key,value in body.items() if key != 'source_ids'}
        if ids is not None:
            altered['source_ids'] = ids
        assert client.post('/api/assistant/source-action',headers=ORIGIN,json=altered).status_code == 409
        assert app.state.store.snapshot() == before
    response = client.post('/api/assistant/source-action',headers=ORIGIN,json=body)
    assert response.status_code == 200 and response.json()['source_ids'] == [i['source_id'] for i in plan['items']]
    saved = app.state.store.read()
    assert saved.revision == 1 and len(saved.audit) == 1 and len(saved.sources) == 2
    assert saved.audit[-1].action == 'Added 2 sources through chat'
    assert client.post('/api/assistant/source-action',headers=ORIGIN,json=body).status_code == 409


def test_real_adapter_filtered_delete_preserves_nonmatching_sources(client,monkeypatch):
    client,app = client
    app.state.store.save(state_with_sources(),0,'Reviewer','Fixture')
    mock_model(monkeypatch,arguments(contains='apples'))
    plan,body = proposal(client,1,'Delete all sources that mention apples.')
    assert len(plan['items']) == 2 and plan['match_text'] == 'apples'
    assert client.post('/api/assistant/source-action',headers=ORIGIN,json=body).status_code == 200
    saved = app.state.store.read()
    assert saved.revision == 2 and [s.title for s in saved.sources] == ['Pears']
    assert saved.audit[-1].action == 'Deleted 2 sources through chat'


@pytest.mark.parametrize('switch',[False,True])
def test_batch_confirmation_never_recomputes_filter_on_changed_workspace(client,monkeypatch,switch):
    client,app = client
    state = app.state.store.save(state_with_sources(),0,'Reviewer','Fixture')
    mock_model(monkeypatch,arguments(contains='apples'))
    _,body = proposal(client,1,'Delete all sources mentioning apples.')
    if switch:
        app.state.store.create(Workspace(title='Other'),1,'Peer')
    else:
        state.sources.append(Source.create(SourceInput(title='New apples',version='new',text='apples')))
        app.state.store.save(state,1,'Peer','New matching source')
    before = app.state.store.snapshot()
    assert client.post('/api/assistant/source-action',headers=ORIGIN,json=body).status_code == 409
    assert client.post('/api/assistant/source-action',headers=ORIGIN,json={**body,'revision':2}).status_code == 409
    assert app.state.store.snapshot() == before


def test_failure_on_second_item_never_saves_first_and_guards_cannot_be_overposted(client,monkeypatch):
    client,app = client
    mock_model(monkeypatch,arguments('add_sources',sources=[fields(text='One'),fields(text='Two')]))
    _,body = proposal(client)
    module = importlib.import_module('backend.app')
    original = module.apply_add_source
    calls = 0
    def fail_second(state,source):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError('Synthetic failure')
        return original(state,source)
    monkeypatch.setattr(module,'apply_add_source',fail_second)
    before = app.state.store.snapshot()
    assert client.post('/api/assistant/source-action',headers=ORIGIN,json={**body,'contains':'anything','sql':'DROP TABLE workspace'}).status_code == 422
    assert client.post('/api/assistant/source-action',json=body).status_code == 403
    assert client.post('/api/assistant/source-action',headers=ORIGIN,json=body).status_code == 422
    assert app.state.store.snapshot() == before
