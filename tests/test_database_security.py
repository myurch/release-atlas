"""Database injection, input rejection and transaction-integrity regression tests.

Attack strings are synthetic data. SQL/source-code examples must round trip
verbatim while selectors, executable SQL and invalid structures are rejected.
"""
import importlib
import json
import sqlite3
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.assistant import AssistantReply
from backend.models import MAX_REVISION, Source, SourceInput, Workspace, digest
from backend.source_actions import SourceActions
from backend.store import Store

ORIGIN = {'Origin': 'http://testserver'}
ATTACKS = [
    "x'); DROP TABLE workspace; --",
    "' OR 1=1; DELETE FROM saved_workspaces; --",
    "'; PRAGMA writable_schema=ON; --",
    "'; UPDATE workspace SET revision=999; --",
    "'; SELECT load_extension('/tmp/not-an-extension'); --",
    '<script>fetch("/api/demo")</script>',
]


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path,auth_enabled=True,passcode='code',origins=['http://testserver'])
    with TestClient(app) as client:
        assert client.post('/api/login',headers=ORIGIN,json={'name':'Reviewer','passcode':'code'}).status_code == 200
        yield client, app


def database_state(path):
    """Inspect through an independent connection, not the restricted app handle."""
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        schema = db.execute('SELECT type,name,sql FROM sqlite_schema ORDER BY type,name').fetchall()
        active = db.execute('SELECT * FROM workspace').fetchall()
        saved = db.execute('SELECT * FROM saved_workspaces ORDER BY id').fetchall()
    return schema, active, saved


@pytest.mark.parametrize('attack', ATTACKS)
def test_source_fields_store_attack_strings_as_inert_data(client, attack):
    client, app = client
    store = app.state.store
    schema = database_state(store.path)[0]
    source = {'title':attack, 'version':attack, 'text':'🧭 Café\n'+attack+'\n\tSELECT * FROM workspace;',
              'url':'https://example.org/?q='+quote(attack), 'license':attack}
    response = client.post('/api/sources',headers=ORIGIN,json={'revision':0,'source':source})
    assert response.status_code == 200, response.text
    saved = response.json()['sources'][0]
    assert {key:saved[key] for key in source} == source
    assert saved['sha256'] == digest(source['text'])
    reopened = Store(store.path).read()
    assert reopened.sources[0].model_dump() == saved
    assert reopened.revision == 1 and len(reopened.sources) == 1
    assert database_state(store.path)[0] == schema
    # Saving another valid source proves subsequent writes and schema still work.
    assert client.post('/api/sources',headers=ORIGIN,json={'revision':1,'source':{'title':'Valid','version':'2','text':'Added a feature.'}}).status_code == 200


def test_names_notes_profile_questions_and_imports_cannot_execute_sql(client):
    client, app = client
    attack = "x'); DROP TABLE saved_workspaces; --"
    assert client.post('/api/login',headers=ORIGIN,json={'name':attack,'passcode':'code'}).status_code == 200
    state = client.post('/api/demo',headers=ORIGIN,json={'revision':0}).json()
    claim = state['claims'][0]['id']
    state = client.put('/api/claims/'+claim+'/review',headers=ORIGIN,
        json={'revision':state['revision'],'status':'applicable','note':attack}).json()
    assert state['claims'][0]['review']['note'] == attack and state['audit'][-1]['by'] == attack
    profile = client.put('/api/profile',headers=ORIGIN,json={'revision':state['revision'],'usage':[{'component':attack,'entity':'valid_api'}]})
    assert profile.status_code == 200 and profile.json()['usage'][0]['component'] == attack
    state = client.post('/api/analyze',headers=ORIGIN,json={'revision':profile.json()['revision']}).json()
    question = client.post('/api/query',headers=ORIGIN,json={'revision':state['revision'],'question':attack,'use_ai':False})
    assert question.status_code == 200 and question.json()['answer']['question'] == attack
    state = question.json()['workspace']
    state['title'] = attack
    imported = client.post('/api/import',headers=ORIGIN,json={'revision':state['revision'],'workspace':state})
    assert imported.status_code == 200 and imported.json()['title'] == attack
    created = client.post('/api/workspaces',headers=ORIGIN,json={'revision':imported.json()['revision'],'title':attack})
    assert created.status_code == 200 and created.json()['title'] == attack
    snapshot = app.state.store.snapshot()
    assert len(snapshot['workspaces']) == 2 and all(row['title'] == attack for row in snapshot['workspaces'])
    database_state(app.state.store.path)


def test_full_length_unicode_source_is_bound_as_data_not_limited_as_sql(client):
    client, app = client
    text = ("🧭\tSQL;\r\n" * 1500)  # 12,000 Unicode code points, larger than the SQL statement limit.
    assert len(text) == 12000
    response = client.post('/api/sources',headers=ORIGIN,
        json={'revision':0,'source':{'title':'Maximum source','version':'1','text':text}})
    assert response.status_code == 200
    saved = app.state.store.read().sources[0]
    assert saved.text == text and saved.sha256 == digest(text)
    database_state(app.state.store.path)


def test_confirmed_chat_source_code_cannot_execute_or_create_files(client,monkeypatch,tmp_path):
    client, app = client
    marker = tmp_path/'must-not-exist'
    text = (f"ATTACH DATABASE '{marker}' AS stolen;\n"
            "DROP TABLE workspace;\n"
            f"__import__('pathlib').Path('{marker}').write_text('owned')\n"
            '<script>alert("owned")</script>')
    schema = database_state(app.state.store.path)[0]
    async def fake(config,state,request):
        actions = SourceActions(state,request.message)
        result = actions.prepare(json.dumps({'action':'add_source','source_id':'','title':'Code example',
            'version':'1','text':text,'url':'','license':''}))
        assert result['status'] == 'awaiting_user_confirmation'
        return AssistantReply(answer='Prepared, not saved.',source_action=actions.prepared)
    monkeypatch.setattr(importlib.import_module('backend.app'),'assist',fake)
    response = client.post('/api/assistant',headers=ORIGIN,json={'revision':0,'message':'Add a source containing my code example.'})
    assert response.status_code == 200 and app.state.store.read().revision == 0
    plan = response.json()['source_action']
    response = client.post('/api/assistant/source-action',headers=ORIGIN,json={'revision':0,'token':plan['token']})
    assert response.status_code == 200
    assert app.state.store.read().sources[0].text == text
    assert not marker.exists() and database_state(app.state.store.path)[0] == schema


@pytest.mark.parametrize('attack', ATTACKS[:5])
def test_injected_workspace_source_and_token_selectors_leave_database_unchanged(client,attack):
    client, app = client
    before = database_state(app.state.store.path)
    assert client.post('/api/workspaces/switch',headers=ORIGIN,json={'revision':0,'id':attack}).status_code == 422
    assert client.request('DELETE','/api/sources/'+quote(attack,safe=''),headers=ORIGIN,json={'revision':0}).status_code in (404,405)
    assert client.post('/api/assistant/source-action',headers=ORIGIN,json={'revision':0,'token':attack+'x'*32}).status_code in (409,422)
    with pytest.raises(ValueError,match='identifier'):
        app.state.store.switch(attack,0,'Reviewer')
    assert database_state(app.state.store.path) == before


@pytest.mark.parametrize('value',[True,False,0.0,'0',-1,MAX_REVISION,MAX_REVISION+1,10**100])
def test_revisions_are_strict_bounded_and_invalid_writes_are_atomic(client,value):
    client, app = client
    before = database_state(app.state.store.path)
    bodies = [('/api/sources',{'source':{'title':'Valid','version':'1','text':'Example'}}),
              ('/api/workspaces',{'title':'Other'}),('/api/assistant',{'message':'Hello'}),
              ('/api/assistant/source-action',{'token':'x'*43})]
    for path,fields in bodies:
        assert client.post(path,headers=ORIGIN,json={'revision':value,**fields}).status_code == 422
    with pytest.raises(ValueError,match='revision'):
        app.state.store.save(Workspace(),value,'Reviewer','Invalid write')
    with pytest.raises(ValueError,match='revision'):
        app.state.store.create(Workspace(),value,'Reviewer')
    assert database_state(app.state.store.path) == before


@pytest.mark.parametrize('control',['\x00','\x01','\x08','\x0b','\x0c','\x1b','\x1f','\x7f','\ud800'])
def test_invalid_unicode_and_control_characters_rejected_across_write_paths(client,control):
    client, app = client
    before = database_state(app.state.store.path)
    text = 'Sensitive input'+control
    requests = [
        ('/api/sources',{'revision':0,'source':{'title':'Title','version':'1','text':text}}),
        ('/api/sources',{'revision':0,'source':{'title':text,'version':'1','text':'Valid'}}),
        ('/api/workspaces',{'revision':0,'title':text}),
        ('/api/profile',{'revision':0,'usage':[{'component':text,'entity':'valid_api'}]}),
        ('/api/query',{'revision':0,'question':text}),
        ('/api/login',{'name':text,'passcode':'code'}),
        ('/api/assistant',{'revision':0,'message':text}),
        ('/api/assistant',{'revision':0,'message':'Hello','history':[{'role':'user','content':text}]}),
        ('/api/import',{'revision':0,'workspace':{'title':text}}),
    ]
    for path,body in requests:
        response = client.request('PUT' if path == '/api/profile' else 'POST',path,
            headers={**ORIGIN,'Content-Type':'application/json'},content=json.dumps(body))
        assert response.status_code == 422, (path,response.text)
        assert 'Sensitive input' not in response.text
    assert database_state(app.state.store.path) == before


def test_invalid_review_and_mutated_model_cannot_bypass_store_validation(client):
    client, app = client
    state = client.post('/api/demo',headers=ORIGIN,json={'revision':0}).json()
    before = database_state(app.state.store.path)
    response = client.put('/api/claims/'+state['claims'][0]['id']+'/review',headers=ORIGIN,
        json={'revision':1,'status':'applicable','note':'invalid\x00note'})
    assert response.status_code == 422
    mutated = app.state.store.read()
    mutated.sources[0].text += '\x00injected'
    with pytest.raises(ValueError):
        app.state.store.save(mutated,1,'Reviewer','Mutation')
    with pytest.raises(ValueError):
        app.state.store.save(app.state.store.read(),1,'Reviewer\x00','Bad actor')
    assert database_state(app.state.store.path) == before


@pytest.mark.parametrize('body',[
    {'revision':0,'sql':'DROP TABLE workspace'},
    {'revision':0,'source':{'title':'Title','version':'1','text':'Example','sql':'DROP TABLE workspace'}},
    {'revision':0,'source':{'title':'Title','version':'1','text':{'$where':'DROP TABLE workspace'}}},
    {'revision':0,'source':{'title':'Title','version':'1','text':'x'*12001}},
])
def test_extra_fields_wrong_types_and_oversized_sources_are_rejected(client,body):
    client, app = client
    before = database_state(app.state.store.path)
    assert client.post('/api/sources',headers=ORIGIN,json=body).status_code == 422
    assert database_state(app.state.store.path) == before


@pytest.mark.parametrize('sql',[
    'DROP TABLE workspace', 'DELETE FROM saved_workspaces',
    'ALTER TABLE workspace ADD COLUMN injected TEXT',
    'CREATE TABLE injected (value TEXT)',
    'PRAGMA writable_schema=ON', 'PRAGMA user_version=999',
    "SELECT load_extension('/tmp/not-an-extension')", 'SELECT randomblob(1000000000)',
    'CREATE TRIGGER injected AFTER UPDATE ON workspace BEGIN DELETE FROM saved_workspaces; END',
])
def test_runtime_connection_denies_schema_changes_deletes_extensions_and_unneeded_functions(tmp_path,sql):
    store = Store(tmp_path/'workspace.sqlite3')
    before = database_state(store.path)
    with pytest.raises(sqlite3.DatabaseError):
        with store.connection() as db:
            db.execute(sql)
    assert database_state(store.path) == before
    assert store.save(Workspace(title='Still writable'),0,'Reviewer','Valid').revision == 1


def test_connection_hardening_and_attach_block_do_not_create_files(tmp_path):
    store = Store(tmp_path/'workspace.sqlite3')
    marker = tmp_path/'attached.sqlite3'
    with store.connection() as db:
        assert db.getconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE)
        assert not db.getconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA)
        assert not db.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION)
        assert db.getlimit(sqlite3.SQLITE_LIMIT_ATTACHED) == 0
        assert db.getlimit(sqlite3.SQLITE_LIMIT_LENGTH) <= 2_000_000
        assert db.getlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH) <= 10_000
        with pytest.raises(sqlite3.DatabaseError):
            db.execute('ATTACH DATABASE ? AS stolen',(str(marker),))
    assert not marker.exists()
    database_state(store.path)


def test_trigger_in_existing_database_cannot_run_on_runtime_or_startup_write(tmp_path):
    store = Store(tmp_path/'workspace.sqlite3')
    with sqlite3.connect(store.path) as db:
        db.execute('CREATE TRIGGER injected AFTER UPDATE ON workspace BEGIN DELETE FROM saved_workspaces; END')
        db.execute('CREATE TRIGGER injected_start BEFORE INSERT ON workspace BEGIN DELETE FROM saved_workspaces; END')
    before = database_state(store.path)
    with pytest.raises(sqlite3.DatabaseError):
        store.save(Workspace(title='Attempt'),0,'Reviewer','Attempt')
    # Startup also refuses schema-origin code rather than trusting an altered file.
    with pytest.raises(sqlite3.DatabaseError):
        Store(store.path)
    assert database_state(store.path) == before


@pytest.mark.parametrize('body',[
    '{"revision":0,"revision":1}',
    '{"revision":0,"source":{"title":"A","title":"B","version":"1","text":"Example"}}',
    '{"revision":NaN}', '{"revision":Infinity}', '{"revision":-Infinity}',
    '{"nested":'+ '['*70 + '0' + ']'*70 + '}',
    '{"nested":'+ '['*2000 + '0' + ']'*2000 + '}',
    '{"revision":'+ '9'*5000 + '}', '[]', 'null', '{"broken":', b'\xff\xfe',
])
def test_malformed_duplicate_nonfinite_and_deep_json_is_rejected_atomically(client,body):
    client, app = client
    before = database_state(app.state.store.path)
    response = client.post('/api/sources',headers={**ORIGIN,'Content-Type':'application/json'},content=body)
    assert response.status_code == 422
    assert database_state(app.state.store.path) == before


@pytest.mark.parametrize('field',['title','version','text','url','license'])
def test_source_tool_rejects_controls_and_duplicate_arguments(field):
    data = {'action':'add_source','source_id':'','title':'','version':'','text':'Example','url':'','license':''}
    data[field] = 'invalid\x00input'
    actions = SourceActions(Workspace(),'Add a source.')
    assert 'error' in actions.prepare(json.dumps(data)) and actions.prepared is None
    duplicate = '{"action":"delete_source",'+json.dumps({**data,field:''})[1:]
    assert 'error' in actions.prepare(duplicate) and actions.prepared is None
