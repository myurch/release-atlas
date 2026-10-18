import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.models import Workspace
from backend.providers import ProviderConfig, ProviderError, embed, generate
from backend.store import Store

ORIGIN = {'Origin':'http://testserver'}


@pytest.fixture
def clients(tmp_path):
    app = create_app(tmp_path,auth_enabled=True,passcode='test-access-code',origins=['http://testserver'])
    with TestClient(app) as a, TestClient(app) as b:
        for client,name in [(a,'Alex'),(b,'Blair')]:
            assert client.post('/api/login',json={'name':name,'passcode':'test-access-code'},headers=ORIGIN).status_code==200
        yield a,b,app



def test_auth_disabled_by_default_keeps_write_guards(tmp_path, monkeypatch):
    monkeypatch.delenv('ATLAS_AUTH_ENABLED', raising=False)
    app = create_app(tmp_path, origins=['http://testserver'])
    with TestClient(app) as client:
        state = client.get('/api/state').json()
        assert state['auth_enabled'] is False and state['user'] == 'Local reviewer'
        assert not (tmp_path/'access-code').exists()
        assert client.post('/api/login', json={'name':'Alex','passcode':'unused'}, headers=ORIGIN).status_code == 404
        assert client.post('/api/demo', json={'revision':0}).status_code == 403
        assert client.get('/api/state', headers={'Host':'evil.invalid'}).status_code == 400
        assert client.post('/api/import', content='x'*2_000_001, headers=ORIGIN).status_code == 413
        saved = client.post('/api/demo', json={'revision':0}, headers=ORIGIN)
        assert saved.status_code == 200
        assert saved.json()['audit'][-1]['by'] == 'Local reviewer'
        assert client.post('/api/demo', json={'revision':0}, headers=ORIGIN).status_code == 409
        assert client.get('/api/export').status_code == 200
        assert client.post('/api/logout', headers=ORIGIN).status_code == 200
        assert client.get('/api/state').status_code == 200


def test_auth_can_be_enabled_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLAS_AUTH_ENABLED', '1')
    app = create_app(tmp_path, origins=['http://testserver'])
    code_path = tmp_path/'access-code'
    code = code_path.read_text().strip()
    assert code and code_path.stat().st_mode & 0o777 == 0o600
    with TestClient(app) as client:
        assert client.get('/api/state').status_code == 401
        assert client.post('/api/login', json={'name':'Alex','passcode':'wrong'}, headers=ORIGIN).status_code == 401
        assert client.post('/api/login', json={'name':'Alex','passcode':code}, headers=ORIGIN).status_code == 200
        assert client.get('/api/state').json()['auth_enabled'] is True
        assert client.get('/api/state').json()['user'] == 'Alex'
        assert client.post('/api/logout', headers=ORIGIN).status_code == 200
        assert client.get('/api/state').status_code == 401
    assert create_app(tmp_path, origins=['http://testserver']).state.auth_enabled
    assert code_path.read_text().strip() == code


def test_invalid_auth_configuration_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLAS_AUTH_ENABLED', 'yes')
    with pytest.raises(ValueError, match='ATLAS_AUTH_ENABLED must be 0 or 1'):
        create_app(tmp_path)


def test_two_reviewers_atomic_conflict_and_restart(clients,tmp_path):
    a,b,app = clients
    state = a.post('/api/demo',json={'revision':0},headers=ORIGIN).json()
    claim = state['claims'][0]['id']
    response = a.put(f'/api/claims/{claim}/review',json={'revision':1,'status':'applicable','note':'Checked usage'},headers=ORIGIN)
    assert response.status_code==200
    assert response.json()['claims'][0]['review']['by']=='Alex'
    stale = b.put(f'/api/claims/{claim}/review',json={'revision':1,'status':'not-applicable'},headers=ORIGIN)
    assert stale.status_code==409
    fresh = b.get('/api/state').json()['workspace']
    assert fresh['revision']==2 and fresh['claims'][0]['review']['note']=='Checked usage'
    reopened=Store(tmp_path/'workspace.sqlite3').read()
    assert reopened.revision==2 and reopened.claims[0].review.by=='Alex'
    assert [x.by for x in reopened.audit]==['Alex','Alex']


def test_delete_source_cleans_references_and_preserves_other_reviews(clients, tmp_path):
    a, b, _ = clients
    state = a.post('/api/demo', json={'revision':0}, headers=ORIGIN).json()
    result = a.post('/api/query', json={'revision':state['revision'], 'question':'legacy_auth', 'mode':'graph'}, headers=ORIGIN)
    assert result.status_code == 200
    state = a.get('/api/state').json()['workspace']
    cited = result.json()['answer']['citations'][0]
    source_id = next(c['source_id'] for c in state['claims'] if c['id'] == cited)
    survivor = next(c for c in state['claims'] if c['source_id'] != source_id)
    state = a.put(f"/api/claims/{survivor['id']}/review", json={'revision':state['revision'], 'status':'applicable', 'note':'Keep this review'}, headers=ORIGIN).json()
    previous_revision = state['revision']
    removed = {c['id'] for c in state['claims'] if c['source_id'] == source_id}
    saved = a.request('DELETE', f'/api/sources/{source_id}', json={'revision':previous_revision}, headers=ORIGIN)
    assert saved.status_code == 200
    state = saved.json()
    assert state['revision'] == previous_revision + 1
    assert all(s['id'] != source_id for s in state['sources'])
    assert all(c['id'] not in removed and not removed.intersection(c['conflicts']) for c in state['claims'])
    assert not state['answers'] and not state['topics'] and not state['graph']['nodes'] and state['analysis'] is None
    assert next(c for c in state['claims'] if c['id'] == survivor['id'])['review']['note'] == 'Keep this review'
    assert state['audit'][-1]['action'].startswith('Deleted source: ')
    assert state['audit'][-1]['by'] == 'Alex'
    assert Workspace.model_validate(state)
    assert Store(tmp_path/'workspace.sqlite3').read().model_dump() == state
    stale = b.request('DELETE', f'/api/sources/{state["sources"][0]["id"]}', json={'revision':previous_revision}, headers=ORIGIN)
    assert stale.status_code == 409
    assert a.post('/api/analyze', json={'revision':state['revision']}, headers=ORIGIN).status_code == 200


def test_delete_last_unanalyzed_source_and_write_guards(clients):
    a, _, _ = clients
    state = a.post('/api/sources', json={'revision':0, 'source':{'title':'Temporary notes','version':'1','text':'Added an example API.'}}, headers=ORIGIN).json()
    path = '/api/sources/' + state['sources'][0]['id']
    assert a.request('DELETE', path, json={'revision':1}).status_code == 403
    assert a.request('DELETE', path, json={'revision':0}, headers=ORIGIN).status_code == 409
    assert a.request('DELETE', '/api/sources/missing', json={'revision':1}, headers=ORIGIN).status_code == 404
    saved = a.request('DELETE', path, json={'revision':1}, headers=ORIGIN)
    assert saved.status_code == 200 and not saved.json()['sources']
    assert saved.json()['revision'] == 2
    assert a.request('DELETE', path, json={'revision':2}, headers=ORIGIN).status_code == 404
    a.post('/api/logout', headers=ORIGIN)
    assert a.request('DELETE', path, json={'revision':2}, headers=ORIGIN).status_code == 401


def test_auth_origin_host_body_and_logout(clients):
    a,b,app = clients
    assert a.post('/api/demo',json={'revision':0}).status_code==403
    assert a.post('/api/demo',json={'revision':0},headers={'Origin':'https://evil.invalid'}).status_code==403
    assert a.get('/api/health',headers={'Host':'evil.invalid'}).status_code==400
    assert a.post('/api/import',content='x'*2_000_001,headers=ORIGIN).status_code==413
    assert a.post('/api/logout',headers=ORIGIN).status_code==200
    assert a.get('/api/state').status_code==401
    assert b.get('/api/state').status_code==200


def test_exports_queries_and_stale_analysis(clients):
    a,_,_=clients
    state=a.post('/api/demo',json={'revision':0},headers=ORIGIN).json()
    r=a.post('/api/query',json={'revision':1,'question':'What affects Checkout service?','mode':'graph'},headers=ORIGIN)
    assert r.status_code==200
    assert r.json()['answer']['citations']
    assert r.json()['answer']['method']=='graph retrieval'
    assert a.put('/api/profile',json={'revision':2,'usage':[]},headers=ORIGIN).status_code==200
    assert a.post('/api/query',json={'revision':3,'question':'retry_limit'},headers=ORIGIN).status_code==409
    new=a.post('/api/analyze',json={'revision':3},headers=ORIGIN)
    assert new.status_code==200
    saved=a.get('/api/export').json()
    assert Workspace.model_validate(saved)
    assert 'passcode' not in json.dumps(saved) and 'test-access-code' not in json.dumps(saved)
    assert a.post('/api/import',json={'revision':4,'workspace':saved},headers=ORIGIN).status_code==200
    assert a.get('/api/state').json()['workspace']['audit'][-1]['by']=='Alex'


def test_empty_duplicates_and_invalid_import(clients):
    a,_,_=clients
    assert a.post('/api/analyze',json={'revision':0},headers=ORIGIN).status_code==422
    assert a.post('/api/import',json={'revision':0,'workspace':{'schema_version':99}},headers=ORIGIN).status_code==422
    source={'title':'Notes','version':'1.0','text':'Added `new_api`.'}
    assert a.post('/api/sources',json={'revision':0,'source':source},headers=ORIGIN).status_code==200
    assert a.post('/api/sources',json={'revision':1,'source':source},headers=ORIGIN).status_code==409
    assert a.post('/api/demo',json={'revision':1},headers=ORIGIN).status_code==409


@pytest.mark.asyncio
async def test_bounded_provider_contracts_and_citation_rejection():
    evidence=[{'claim':{'id':'c-one','quote':'A documented change.'}}]
    def response(request):
        payload=json.loads(request.content)
        assert payload['model']=='test-model'
        return httpx.Response(200,json={'message':{'content':json.dumps({'answer':'A change.','citations':['c-one'],'uncertainty':'Review required'})}})
    config=ProviderConfig(kind='ollama',base='http://localhost:11434',model='test-model')
    answer=await generate(config,'what changed?',evidence,httpx.MockTransport(response))
    assert answer.citations==['c-one']
    for content in ['not json',json.dumps({'answer':'wrong','citations':['invented'],'uncertainty':''})]:
        transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'message':{'content':content}}))
        with pytest.raises(ProviderError):await generate(config,'q',evidence,transport)
    with pytest.raises(ProviderError,match='HTTP 503'):
        await generate(config,'q',evidence,httpx.MockTransport(lambda r:httpx.Response(503)))
    with pytest.raises(ProviderError,match='timed out'):
        def timeout(request):raise httpx.ReadTimeout('secret detail must not leak')
        await generate(config,'q',evidence,httpx.MockTransport(timeout))
    compatible=ProviderConfig(kind='compatible',base='http://localhost:11434/v1',model='test-model')
    body={'choices':[{'message':{'content':json.dumps({'answer':'Supported text.','citations':['c-one'],'uncertainty':'Needs review'})}}]}
    assert (await generate(compatible,'q',evidence,httpx.MockTransport(lambda r:httpx.Response(200,json=body)))).answer=='Supported text.'


@pytest.mark.asyncio
async def test_embedding_order_dimensions_and_nonfinite():
    config=ProviderConfig(kind='compatible',base='http://localhost:11434/v1',model='embedding-model')
    good={'data':[{'index':1,'embedding':[0.0,1.0]},{'index':0,'embedding':[1.0,0.0]}]}
    assert await embed(config,['a','b'],httpx.MockTransport(lambda r:httpx.Response(200,json=good)))==[[1.0,0.0],[0.0,1.0]]
    for rows in [[{'index':0,'embedding':[0,0]}],[{'index':0,'embedding':[1,2]},{'index':1,'embedding':[1]}],[{'index':0,'embedding':[1,2]},{'index':0,'embedding':[2,1]}]]:
        with pytest.raises(ProviderError):
            await embed(config,['a','b'],httpx.MockTransport(lambda r:httpx.Response(200,json={'data':rows})))


@pytest.mark.asyncio
async def test_malformed_provider_shapes_and_large_vectors():
    evidence=[{'claim':{'id':'c-one','quote':'A change.'}}]
    for kind in ['ollama','compatible']:
        config=ProviderConfig(kind=kind,model='test')
        for body in [[], {'message':None}, {'choices':[None]}, {'choices':{'bad':True}}]:
            with pytest.raises(ProviderError):
                await generate(config,'q',evidence,httpx.MockTransport(lambda r:httpx.Response(200,json=body)))
        for body in [[], {'embeddings':[[1e308,1e308]]}, {'data':[None]}, {'data':[{'index':'0','embedding':[1,2]}]}]:
            with pytest.raises(ProviderError):
                await embed(config,['a'],httpx.MockTransport(lambda r:httpx.Response(200,json=body)))


def test_stale_analysis_marker_and_unicode_import(clients):
    a,_,_=clients
    state=a.post('/api/demo',json={'revision':0},headers=ORIGIN).json()
    r=a.post('/api/sources',json={'revision':1,'source':{'title':'More notes','version':'3','text':'Added `next_api`.'}},headers=ORIGIN)
    assert r.status_code==200 and r.json()['analysis'] is None
    claim=state['claims'][0]['id']
    assert a.put(f'/api/claims/{claim}/review',json={'revision':2,'status':'applicable'},headers=ORIGIN).status_code==409
    body='{"revision":2,"source":{"title":"Bad","version":"1","text":"\\ud800"}}'
    assert a.post('/api/sources',content=body,headers={**ORIGIN,'Content-Type':'application/json'}).status_code==422
    state['claims'][0]['id']='forged'
    assert a.post('/api/import',json={'revision':2,'workspace':state},headers=ORIGIN).status_code==422


def test_saved_workspaces_preserve_history_and_reject_cross_workspace_writes(clients,tmp_path):
    a,b,app = clients
    initial = a.get('/api/state').json()
    original = initial['active_id']
    demo = a.post('/api/demo',json={'revision':0},headers=ORIGIN).json()
    claim = demo['claims'][0]['id']
    reviewed = a.put(f'/api/claims/{claim}/review',json={'revision':1,'status':'needs-investigation','note':'Keep this review'},headers=ORIGIN).json()
    created = a.post('/api/workspaces',json={'revision':2,'title':'My upgrade'},headers=ORIGIN)
    assert created.status_code==200 and created.json()['sources']==[]
    snapshot = b.get('/api/state').json()
    assert len(snapshot['workspaces'])==2 and snapshot['active_id']!=original
    assert [x['action'] for x in snapshot['workspace']['audit']]==['Created empty workspace']
    assert b.put(f'/api/claims/{claim}/review',json={'revision':2,'status':'applicable'},headers=ORIGIN).status_code==409
    restored = a.post('/api/workspaces/switch',json={'revision':3,'id':original},headers=ORIGIN).json()
    assert restored['revision']==4 and restored['claims']==reviewed['claims']
    assert restored['audit'][:-1]==reviewed['audit']
    assert a.post('/api/workspaces/switch',json={'revision':3,'id':snapshot['active_id']},headers=ORIGIN).status_code==409
    assert a.post('/api/workspaces/switch',json={'revision':4,'id':'0'*32},headers=ORIGIN).status_code==404
    assert a.post('/api/workspaces',json={'revision':4,'title':'   '},headers=ORIGIN).status_code==422
    reopened = Store(tmp_path/'workspace.sqlite3').snapshot()
    assert reopened['workspace']==restored and reopened['active_id']==original
    assert len(reopened['workspaces'])==2
    assert a.post('/api/workspaces',json={'revision':4,'title':'Imported review','workspace':demo},headers=ORIGIN).status_code==200
    assert len(a.get('/api/state').json()['workspaces'])==3
    assert a.post('/api/logout',headers=ORIGIN).status_code==200
    assert a.post('/api/workspaces',json={'revision':5,'title':'Unauthorized'},headers=ORIGIN).status_code==401


def test_original_database_migration_is_lossless_and_idempotent(tmp_path):
    import sqlite3
    path=tmp_path/'workspace.sqlite3'
    state=Workspace.model_validate_json(Path('data/demo-snapshot.json').read_text())
    state.revision=17
    payload=state.model_dump_json()
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE workspace (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL)')
        db.execute('INSERT INTO workspace VALUES (1,17,?)',(payload,))
    first=Store(path).snapshot()
    assert first['workspace']==state.model_dump() and len(first['workspaces'])==1
    assert Store(path).snapshot()==first
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT payload FROM workspace').fetchone()[0]==payload


def test_workspace_capacity_and_import_failure_do_not_replace_saved_data(clients):
    a,_,app=clients
    app.state.store.LIMIT=2
    assert a.post('/api/workspaces',json={'revision':0,'title':'Second'},headers=ORIGIN).status_code==200
    before=a.get('/api/state').json()
    assert a.post('/api/workspaces',json={'revision':1,'title':'Third'},headers=ORIGIN).status_code==422
    bad={'schema_version':99}
    assert a.post('/api/workspaces',json={'revision':1,'title':'Bad','workspace':bad},headers=ORIGIN).status_code==422
    assert a.get('/api/state').json()==before
