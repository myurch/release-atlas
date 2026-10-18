"""Retrieval invariants, fallbacks and context guards without paid model calls."""
import json
from pathlib import Path

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend import semantic
from backend.assistant import AssistantRequest, ChatMessage, assistant_context, assist
from backend.app import create_app
from backend.models import Source, SourceInput, Workspace
from backend.nlp import analyze
from backend.providers import ProviderConfig
from backend.source_context import build_index, effective_query, source_passages, scoped_sources, RetrievalReport


def source(title,text,version='1.0'):
    return Source.create(SourceInput(title=title,text=text,version=version))


def corpus():
    return Workspace(sources=[
        source('Identity guide','Verify the supplied password against the stored hash before establishing a signed-in session. Reject incorrect credentials after expiry.'),
        source('Authentication API','Authentication verifies who a caller is. Call `verify_token()` to check a bearer credential.'),
        source('Client settings','Configure `IDENTITY_KEY` to validate the signed credential supplied by each client.'),
        source('Report printing','Generate PDF reports with colored charts. Set page margins and choose a printer.'),
        source('SQL storage','Create tables and configure the database connection pool for saving reports.'),
        source('Logging','Choose log file rotation and JSON output for application events.'),
    ])


@pytest.fixture
def statistical(monkeypatch):
    monkeypatch.setattr(semantic,'configuration',lambda:(None,'Statistical encoder selected in configuration.'))
    build_index.cache_clear()
    yield
    build_index.cache_clear()


def test_lexical_and_terminology_channels_find_authentication_without_forcing_decoys(statistical):
    state=corpus()
    passages,coverage=source_passages(state,'How does authentication work?')
    ids={p['source_id'] for p in passages}
    assert state.sources[0].id in ids and state.sources[1].id in ids
    assert state.sources[3].id not in ids
    report=RetrievalReport.model_validate(coverage['retrieval'])
    assert report.encoder=='statistical-lsa' and report.fallback
    assert any('terminology match' in p.reasons for p in report.passages)
    assert not any('semantic match' in p.reasons for p in report.passages)


def test_purpose_verbs_cannot_independently_select_unrelated_setup(statistical):
    state=corpus()
    rows,c=source_passages(state,'How do I configure authentication?')
    assert state.sources[4].id not in {p['source_id'] for p in rows}


def test_entities_use_exact_identity_and_case_preserved_quotes(statistical):
    state=corpus()
    rows,c=source_passages(state,'Explain IDENTITY_KEY')
    assert rows[0]['source_id']==state.sources[2].id
    assert 'exact entity' in c['retrieval']['passages'][0]['reasons']
    assert 'IDENTITY_KEY' in rows[0]['quote']


def test_no_relevance_does_not_fill_budget_with_every_source(statistical):
    rows,c=source_passages(corpus(),'zzqvxy florpz quxx')
    assert rows==[] and c['retrieval']['passages']==[]
    assert c['partial'] and c['included_sources']==0


def test_empty_workspace_is_bounded_and_readable(statistical):
    rows,c=source_passages(Workspace(),'Summarize all sources')
    assert rows==[] and not c['partial'] and c['total_sources']==0
    assert RetrievalReport.model_validate(c['retrieval'])


def test_ambient_selected_source_cannot_override_a_standalone_subject(statistical):
    state=corpus()
    rows,c=source_passages(state,'How does authentication work?',state.sources[3].id)
    assert state.sources[3].id not in {p['source_id'] for p in rows}


@pytest.mark.parametrize('question,expected',[
    ('Use only Identity guide for authentication.',{0}),
    ('Use only the selected source.',{2}),
    ('Use only source "missing title".',set()),
    ('How does HTTP version 1.1 handle requests?',{0,1,2}),
])
def test_source_scope_is_server_resolved(question,expected):
    state=corpus();state.sources=state.sources[:3]
    allowed,_=scoped_sources(state,question,state.sources[2].id)
    assert allowed=={state.sources[i].id for i in expected}


def test_version_rules_include_comparisons_and_explicit_highest(statistical):
    state=Workspace(sources=[source('Snapshot','There are four bagels.','1.0'),source('Snapshot','There are eight bagels.','2.0')])
    for q,expected in [('Use version 1.0 to count bagels.',{0}),('Use the highest version for bagels.',{1}),('Compare version 1.0 and version 2.0.',{0,1}),('Use only version 9.0.',set())]:
        rows,_=source_passages(state,q)
        assert {p['source_id'] for p in rows}=={state.sources[i].id for i in expected}


def test_nonorderable_versions_do_not_invent_latest():
    state=Workspace(sources=[source('Commit','A document.','commit:abc')])
    allowed,notices=scoped_sources(state,'Use the latest version.','')
    assert not allowed and notices


def test_followup_carries_user_subject_but_new_question_drops_it():
    history=[ChatMessage(role='user',content='Explain authentication.'),ChatMessage(role='assistant',content='Printing reports.')]
    assert 'authentication' in effective_query('How do I configure it?',history)
    assert effective_query('How do I print a report?',history)=='How do I print a report?'
    assert 'Printing reports' not in effective_query('How do I configure it?',history)


def test_cache_reuses_sources_but_invalidates_title_text_and_version(statistical):
    state=corpus()
    source_passages(state,'authentication')
    before=build_index.cache_info()
    source_passages(state,'printing')
    assert build_index.cache_info().hits==before.hits+1
    for s in [source('Updated title',state.sources[0].text),source('Identity guide','New password guidance.'),source('Identity guide',state.sources[0].text,'2.0')]:
        changed=state.model_copy(deep=True);changed.sources[0]=s
        before=build_index.cache_info().misses
        source_passages(changed,'authentication')
        assert build_index.cache_info().misses==before+1


def test_queries_remain_independent_between_workspaces(statistical):
    a=Workspace(sources=[source('Private A','Authentication uses `secret_a`.')])
    b=Workspace(sources=[source('Private B','Authentication uses `secret_b`.')])
    source_passages(a,'authentication')
    rows,_=source_passages(b,'authentication')
    assert all(p['source_id']==b.sources[0].id and 'secret_a' not in p['quote'] for p in rows)


def test_unicode_crlf_spans_and_code_windows_remain_exact(statistical):
    text='# 🧭 Guide\r\n\r\n```python\r\n'+('print("Résumé")\r\n'*100)+'# use zebra_timeout here\r\n```'
    state=Workspace(sources=[source('Unicode',text)])
    rows,c=source_passages(state,'Explain zebra_timeout')
    assert rows and 'zebra_timeout' in rows[0]['quote']
    for p in rows:
        assert text[p['start']:p['end']]==p['quote'] and len(p['quote'])<=2000
        assert p['id']==f"p-{p['source_id']}-{p['start']}-{p['end']}"


def test_broad_overviews_prioritize_source_coverage(statistical):
    state=Workspace(sources=[source(f'Document {i}',f'Synthetic text {i}. '*300) for i in range(12)])
    rows,c=source_passages(state,'Summarize all sources',state.sources[-1].id)
    assert rows[0]['source_id']==state.sources[-1].id
    assert len({p['source_id'] for p in rows})==8
    assert sum(len(p['quote']) for p in rows)<=16000 and c['partial']
    assert c['retrieval']['mode']=='overview'


def test_findings_cannot_reintroduce_unrelated_documents(statistical):
    state=analyze(corpus())
    context=assistant_context(state,AssistantRequest(revision=0,message='Explain authentication.'))
    ids={p['source_id'] for p in context['source_passages']}
    by_id={c.id:c for c in state.claims}
    assert state.sources[3].id not in ids
    assert all(by_id[c['id']].source_id in ids for c in context['evidence'])


def test_known_conflict_partner_is_packed_and_not_counted_as_semantic_evidence(statistical):
    state=Workspace(sources=[source('Release','Removed `retry_limit`.','2.0'),source('Reference','The `retry_limit` setting remains supported.','2.0')])
    state=analyze(state)
    context=assistant_context(state,AssistantRequest(revision=0,message='Explain retry_limit'))
    assert context['conflicts'] and len({p['source_id'] for p in context['source_passages']})==2
    assert all(all(group for group in pair['citation_groups']) for pair in context['conflicts'])


def test_encoder_failure_rebuilds_all_channels_in_one_statistical_space(monkeypatch):
    build_index.cache_clear()
    monkeypatch.setattr(semantic,'configuration',lambda:(('python','fingerprint','revision'),''))
    monkeypatch.setattr(semantic,'encode',lambda *args: (_ for _ in ()).throw(semantic.SemanticUnavailable('Synthetic encoder failure.')))
    rows,c=source_passages(corpus(),'authentication')
    assert rows and c['retrieval']['encoder']=='statistical-lsa'
    assert c['retrieval']['fallback']=='Synthetic encoder failure.'
    build_index.cache_clear()


@pytest.mark.asyncio
async def test_retrieval_report_is_server_supplied_and_not_duplicated_in_model_context(statistical):
    state=corpus()
    def handle(request):
        payload=json.loads(request.content)
        context=json.loads(payload['messages'][1]['content'])['context']
        assert 'retrieval' not in context and 'retrieval' not in context['source_coverage']
        assert context['source_coverage']['selection_reasons']
        p=context['source_passages'][0]
        return httpx.Response(200,json={'message':{'content':json.dumps({'answer':'The supplied guidance verifies credentials.','source_citations':[p['id']]})}})
    result=await assist(ProviderConfig(kind='ollama',base='http://localhost:11434'),state,AssistantRequest(revision=0,message='Explain authentication'),httpx.MockTransport(handle))
    assert result.retrieval.passages and result.source_passages[0].id in {p.id for p in result.retrieval.passages}


def test_encoder_mode_validation_does_not_read_or_echo_credentials(monkeypatch):
    monkeypatch.setenv('ATLAS_RETRIEVAL_ENCODER','unsupported')
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-do-not-echo')
    with pytest.raises(semantic.SemanticUnavailable,match='Invalid retrieval encoder') as exc: semantic.configuration()
    assert 'synthetic-do-not-echo' not in str(exc.value)


def test_runtime_off_switch(monkeypatch):
    monkeypatch.setenv('ATLAS_RETRIEVAL_ENCODER','statistical')
    assert semantic.configuration()[0] is None


def test_semantic_client_rejects_oversized_input_without_spawning():
    with pytest.raises(semantic.SemanticUnavailable): semantic.encode(['x'*2601],('not-run','hash','rev'))


def test_chat_api_retains_read_only_revision_and_origin_guards(tmp_path,monkeypatch,statistical):
    import importlib
    async def answer(config,path,payload,transport=None):
        context=json.loads(payload['messages'][1]['content'])['context']
        return {'message':{'content':json.dumps({'answer':'The source describes authentication.','source_citations':[context['source_passages'][0]['id']]})}}
    monkeypatch.setattr(importlib.import_module('backend.assistant'),'post',answer)
    app=create_app(tmp_path,auth_enabled=False,origins=['http://testserver'],provider=ProviderConfig(kind='ollama',base='http://localhost:11434'))
    with TestClient(app) as client:
        s=corpus().sources[0]
        assert client.post('/api/sources',headers={'Origin':'http://testserver'},json={'revision':0,'source':s.model_dump(exclude={'id','sha256'})}).status_code==200
        before=app.state.store.snapshot()
        reply=client.post('/api/assistant',headers={'Origin':'http://testserver'},json={'revision':1,'message':'authentication'})
        assert reply.status_code==200 and reply.json()['retrieval']['passages']
        assert app.state.store.snapshot()==before
        assert client.post('/api/assistant',headers={'Origin':'http://testserver'},json={'revision':0,'message':'authentication'}).status_code==409
        assert client.post('/api/assistant',json={'revision':1,'message':'authentication'}).status_code==403


def test_source_only_followup_supplies_the_explicit_version_without_inventing_relevance(statistical):
    state=Workspace(sources=[source('Snapshot','Four bagels.','1.0'),source('Snapshot','Eight bagels.','2.0')])
    rows,c=source_passages(state,'Use the highest version.')
    assert {p['source_id'] for p in rows}=={state.sources[1].id}
    assert c['retrieval']['mode']=='overview'


@pytest.mark.parametrize('result',[
    b'not-json\n',
    b'{"vectors": [[0]], "revision":"r"}\n',
    b'{"vectors": [], "revision":"wrong"}\n',
])
def test_invalid_worker_output_is_rejected_and_process_closed(monkeypatch,result):
    import io,os
    semantic.shutdown()
    read,write=os.pipe()
    os.write(write,result);os.close(write)
    class Process:
        atlas_config=('fake','h','r')
        stdin=io.BytesIO()
        stdout=os.fdopen(read,'rb')
        killed=False
        def poll(self): return None
        def kill(self): self.killed=True
        def wait(self,timeout=None): return 0
    process=Process()
    monkeypatch.setattr(semantic,'PROCESS',process)
    with pytest.raises(semantic.SemanticUnavailable,match='failed or timed out'):
        semantic.encode(['Synthetic text.'],process.atlas_config)
    assert process.killed and semantic.PROCESS is None


def test_worker_timeout_closes_process_without_provider_credentials(monkeypatch):
    import io,os
    semantic.shutdown()
    read,write=os.pipe()
    class Process:
        stdin=io.BytesIO()
        stdout=os.fdopen(read,'rb')
        killed=False
        def poll(self): return None
        def kill(self): self.killed=True
        def wait(self,timeout=None): return 0
    process=Process();calls=[]
    def spawn(args,**kwargs): calls.append((args,kwargs));return process
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-provider-secret')
    monkeypatch.setattr(semantic.subprocess,'Popen',spawn)
    monkeypatch.setattr(semantic.select,'select',lambda *args:([],[],[]))
    with pytest.raises(semantic.SemanticUnavailable): semantic.encode(['Synthetic text.'],('fixed-python','h','r'))
    os.close(write)
    assert process.killed and calls[0][0][1].endswith('tools/semantic_worker.py')
    assert 'OPENAI_API_KEY' not in calls[0][1]['env']
    assert calls[0][1].get('shell',False) is False


def test_server_stop_prevents_worker_restart(monkeypatch):
    semantic.shutdown()
    monkeypatch.setattr(semantic,'STOPPED',False)
    semantic.stop()
    with pytest.raises(semantic.SemanticUnavailable,match='stopping'): semantic.encode(['text'],('not-run','h','r'))
    with pytest.raises(semantic.SemanticUnavailable,match='stopping'): semantic.configuration()
    monkeypatch.setattr(semantic,'STOPPED',False)


@pytest.mark.asyncio
async def test_server_shutdown_stops_semantic_worker_before_waiting_for_connections(monkeypatch):
    import uvicorn
    from backend import __main__ as main
    calls=[]
    monkeypatch.setattr(main,'stop_semantic',lambda:calls.append('worker'))
    async def shutdown(self,sockets=None): calls.append('connections')
    monkeypatch.setattr(uvicorn.Server,'shutdown',shutdown)
    from types import SimpleNamespace
    server=main.AtlasServer(SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(listeners=set()))))
    await server.shutdown()
    assert calls==['worker','connections']


def test_simultaneous_timeout_and_shutdown_take_worker_ownership_once(monkeypatch):
    import io,threading,time
    semantic.shutdown()
    class Process:
        stdin=io.BytesIO();stdout=io.BytesIO();kills=0
        def kill(self): self.kills+=1
        def wait(self,timeout=None): time.sleep(.01)
    proc=Process();monkeypatch.setattr(semantic,'PROCESS',proc)
    errors=[]
    def stop():
        try: semantic.shutdown()
        except Exception as exc: errors.append(exc)
    threads=[threading.Thread(target=stop) for _ in range(2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join(timeout=1)
    assert errors==[] and proc.kills==1 and semantic.PROCESS is None


@pytest.mark.parametrize('label,question,expected',[
    ('commit:abc123','Use only version commit:abc123.',True),
    ('Release Candidate','Use only version "Release Candidate".',True),
    ('commit:abc123','Use only version missing.',False),
    ('1.1','How does HTTP version 1.1 work?',True),
])
def test_exact_non_numeric_version_labels_are_supported(label,question,expected):
    state=Workspace(sources=[source('Reference','Some reference text.',label)])
    allowed,_=scoped_sources(state,question,'')
    assert bool(allowed) is expected


def test_source_restrictions_do_not_match_substrings_or_nested_shorter_titles():
    state=Workspace(sources=[source('Auth','First text.'),source('OAuth guide','Second text.'),source('guide','Third text.')])
    allowed,_=scoped_sources(state,'Use only OAuth guide.','')
    assert allowed=={state.sources[1].id}
