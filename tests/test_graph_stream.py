"""Private Graph-page retrieval streaming, with mocked generation only."""
import importlib
import json

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import Response

from backend.app import create_app
from backend.assistant import AssistantReply, AssistantRequest
from backend.providers import ProviderConfig, ProviderError

ORIGIN={'Origin':'http://testserver'}
HEADERS={**ORIGIN,'Accept':'application/x-ndjson'}


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path,auth_enabled=False,origins=['http://testserver'],provider=ProviderConfig(kind='compatible',model='mock'))


def endpoint(app):
    return next(route.endpoint for route in app.routes if getattr(route,'path','')=='/api/assistant')


def test_stream_wire_report_matches_final_and_request_is_read_only(app,monkeypatch):
    module=importlib.import_module('backend.app')
    calls=[]
    original=module.assistant_context
    def context(state,data):
        calls.append('retrieve')
        return original(state,data)
    async def generate(config,state,data,*,context):
        calls.append('generate')
        return AssistantReply(answer='No saved source text yet.',retrieval=context['retrieval'])
    monkeypatch.setattr(module,'assistant_context',context)
    monkeypatch.setattr(module,'assist',generate)
    before=app.state.store.snapshot()
    with TestClient(app) as client:
        response=client.post('/api/assistant',json={'revision':0,'page':'Graph','message':'How do these docs connect?'},headers=HEADERS)
    assert response.status_code==200 and response.headers['content-type'].startswith('application/x-ndjson')
    assert response.headers['cache-control']=='no-store'
    frames=[json.loads(line) for line in response.text.splitlines()]
    assert [f['type'] for f in frames]==['retrieval','answer']
    assert frames[0]['retrieval']==frames[1]['data']['retrieval']
    assert calls==['retrieve','generate'] and app.state.store.snapshot()==before


@pytest.mark.asyncio
async def test_progress_is_yielded_before_generation_starts_and_uses_exact_context(app,monkeypatch):
    module=importlib.import_module('backend.app')
    calls=[];contexts=[]
    original=module.assistant_context
    def context(state,data):
        result=original(state,data);contexts.append(result);calls.append('retrieve');return result
    async def generate(config,state,data,*,context):
        assert context is contexts[0]
        calls.append('generate')
        return AssistantReply(answer='Read the supplied passages.',retrieval=context['retrieval'])
    monkeypatch.setattr(module,'assistant_context',context)
    monkeypatch.setattr(module,'assist',generate)
    req=Request({'type':'http','method':'POST','path':'/api/assistant','headers':[(b'accept',b'application/x-ndjson')]})
    response=await endpoint(app)(AssistantRequest(revision=0,page='Graph',message='Show connections.'),req)
    first=json.loads(await anext(response.body_iterator))
    assert first['type']=='retrieval' and calls==['retrieve']
    final=json.loads(await anext(response.body_iterator))
    assert final['type']=='answer' and calls==['retrieve','generate']
    await response.body_iterator.aclose()


@pytest.mark.asyncio
async def test_cancelling_after_progress_releases_busy_lock_without_generation(app,monkeypatch):
    module=importlib.import_module('backend.app')
    calls=[]
    async def generate(*args,**kwargs): calls.append(1);return AssistantReply(answer='Unused')
    monkeypatch.setattr(module,'assist',generate)
    req=Request({'type':'http','method':'POST','path':'/api/assistant','headers':[(b'accept',b'application/x-ndjson')]})
    data=AssistantRequest(revision=0,page='Graph',message='Explain sources.')
    response=await endpoint(app)(data,req)
    assert json.loads(await anext(response.body_iterator))['type']=='retrieval'
    await response.body_iterator.aclose()
    again=await endpoint(app)(data,req)
    assert json.loads(await anext(again.body_iterator))['type']=='retrieval'
    await again.body_iterator.aclose()
    assert not calls


@pytest.mark.parametrize('problem',['provider','revision','session'])
def test_stream_rejects_failures_after_retrieval_without_delivering_answer(tmp_path,monkeypatch,problem):
    module=importlib.import_module('backend.app')
    app=create_app(tmp_path,auth_enabled=problem=='session',passcode='test-code',origins=['http://testserver'])
    async def generate(config,state,data,*,context):
        if problem=='provider': raise ProviderError('Model unavailable for this test.')
        if problem=='revision': app.state.store.save(state,data.revision,'Tester','Changed revision')
        if problem=='session':
            logout=next(route.endpoint for route in app.routes if getattr(route,'path','')=='/api/logout')
            req=Request({'type':'http','headers':[(b'cookie',('atlas_session='+client.cookies.get('atlas_session')).encode())]})
            await logout(req,Response())
        return AssistantReply(answer='Must not be delivered',retrieval=context['retrieval'])
    monkeypatch.setattr(module,'assist',generate)
    with TestClient(app) as client:
        if problem=='session': client.post('/api/login',json={'name':'Tester','passcode':'test-code'},headers=ORIGIN)
        response=client.post('/api/assistant',json={'revision':0,'page':'Graph','message':'Explain docs.'},headers=HEADERS)
    frames=[json.loads(line) for line in response.text.splitlines()]
    assert [f['type'] for f in frames]==['retrieval','error']
    assert frames[-1]['status']=={'provider':502,'revision':409,'session':401}[problem]
    assert 'Must not be delivered' not in response.text


@pytest.mark.parametrize('page,headers',[('Overview',HEADERS),('Graph',ORIGIN)])
def test_existing_json_protocol_remains_available(app,monkeypatch,page,headers):
    async def generate(*args): return AssistantReply(answer='Plain JSON reply.')
    monkeypatch.setattr(importlib.import_module('backend.app'),'assist',generate)
    with TestClient(app) as client:
        response=client.post('/api/assistant',json={'revision':0,'page':page,'message':'Explain docs.'},headers=headers)
    assert response.headers['content-type'].startswith('application/json') and response.json()['answer']=='Plain JSON reply.'


def test_stream_preserves_origin_revision_and_input_guards(app):
    with TestClient(app) as client:
        data={'revision':0,'page':'Graph','message':'Explain docs.'}
        assert client.post('/api/assistant',json=data,headers={'Accept':'application/x-ndjson'}).status_code==403
        assert client.post('/api/assistant',json={**data,'revision':1},headers=HEADERS).status_code==409
        assert client.post('/api/assistant',json={**data,'context':{}},headers=HEADERS).status_code==422


@pytest.mark.asyncio
async def test_busy_is_rechecked_before_stream_body_iteration(app):
    req=Request({'type':'http','method':'POST','path':'/api/assistant','headers':[(b'accept',b'application/x-ndjson')]})
    data=AssistantRequest(revision=0,page='Graph',message='Explain sources.')
    first=await endpoint(app)(data,req)
    second=await endpoint(app)(data,req)
    assert json.loads(await anext(first.body_iterator))['type']=='retrieval'
    rejected=json.loads(await anext(second.body_iterator))
    assert rejected['type']=='error' and rejected['status']==409
    await first.body_iterator.aclose()
    await second.body_iterator.aclose()


def test_changed_revision_during_retrieval_is_never_published(app,monkeypatch):
    module=importlib.import_module('backend.app')
    original=module.assistant_context
    def context(state,data):
        result=original(state,data)
        app.state.store.save(state,data.revision,'Tester','Changed while indexing')
        return result
    monkeypatch.setattr(module,'assistant_context',context)
    with TestClient(app) as client:
        response=client.post('/api/assistant',json={'revision':0,'page':'Graph','message':'Explain sources.'},headers=HEADERS)
    frames=[json.loads(line) for line in response.text.splitlines()]
    assert len(frames)==1 and frames[0]['type']=='error' and frames[0]['status']==409
    assert 'retrieval' not in frames[0]


def test_streamed_source_proposal_still_requires_explicit_confirmation(app,monkeypatch):
    from backend.source_actions import SourceActions
    async def generate(config,state,data,*,context):
        actions=SourceActions(state)
        actions.prepare(json.dumps({'action':'add_source','source_id':'','title':'Synthetic stream source','version':'1','text':'There are four bagels.','url':'','license':''}))
        return AssistantReply(answer='Prepared for confirmation.',source_action=actions.prepared,retrieval=context['retrieval'])
    monkeypatch.setattr(importlib.import_module('backend.app'),'assist',generate)
    before=app.state.store.snapshot()
    with TestClient(app) as client:
        response=client.post('/api/assistant',json={'revision':0,'page':'Graph','message':'Add a source.'},headers=HEADERS)
        frames=[json.loads(line) for line in response.text.splitlines()]
        assert [f['type'] for f in frames]==['retrieval','answer']
        assert 'token' not in frames[0] and app.state.store.snapshot()==before
        plan=frames[-1]['data']['source_action']
        assert plan['token'] and plan['revision']==0
        confirmed=client.post('/api/assistant/source-action',json={'token':plan['token'],'revision':0},headers=ORIGIN)
        assert confirmed.status_code==200 and app.state.store.read().sources[0].title=='Synthetic stream source'


def test_stream_uses_actual_cross_source_graph_report_without_reanalysis(app,monkeypatch):
    from backend import semantic
    from backend.source_context import build_index
    from tools.graph_retrieval_probe import corpus
    monkeypatch.setattr(semantic,'configuration',lambda:(None,'Statistical test encoder.'))
    build_index.cache_clear()
    state=app.state.store.save(corpus(),0,'Tester','Synthetic sources')
    captured=[]
    async def generate(config,state,data,*,context):
        captured.append(context)
        assert context['retrieval']['graph_paths']
        return AssistantReply(answer='Use the supplied Flask and Jinja passages.',retrieval=context['retrieval'])
    monkeypatch.setattr(importlib.import_module('backend.app'),'assist',generate)
    with TestClient(app) as client:
        response=client.post('/api/assistant',json={'revision':state.revision,'page':'Graph','message':'How do I make a backend and frontend?'},headers=HEADERS)
    frames=[json.loads(line) for line in response.text.splitlines()]
    assert frames[0]['retrieval']==frames[1]['data']['retrieval']==captured[0]['retrieval']
    assert frames[0]['retrieval']['graph_paths'][0]['via']=='jinja'
    assert app.state.store.read()==state and not state.claims
    build_index.cache_clear()
