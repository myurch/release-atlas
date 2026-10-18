"""Structural/semantic regressions use original synthetic documentation only."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from sklearn.metrics import f1_score

from backend.document_parser import parse_document
from backend.document_classifier import classify_documents
from backend.technical_entities import extract_entities
from backend.models import Source, SourceInput, Workspace
from backend.nlp import analyze, retrieve
from backend.store import Store

RST = '''Harbor Web
==========

Harbor Web is a toolkit for HTTP and WSGI applications. It provides
request handling and response streaming without imposing a database.

It includes:

* A routing system that maps paths to handlers and builds URLs
  for a response. This continuation belongs to the same feature.
* A request object for headers, form data and cookies.
* A test client that sends requests without a running server.
* An interactive debugger to inspect stack traces during development.

Installing
----------

Install and update using pip:

.. code-block:: text

    pip install -U harbor-web

A Simple Example
----------------

.. code-block:: python

    from harbor.wrappers import Request, Response

    @Request.application
    def application(request):
        return Response("Hello")

Configuration
-------------

Set the `REQUEST_TIMEOUT` environment variable to 30. The default
controls how long the client waits before returning an error.

Links
-----

* Documentation: https://example.invalid/docs
* Issue tracker: https://example.invalid/issues

.. _HTTP: https://example.invalid/http
'''


def workspace(text=RST):
    return Workspace(sources=[Source.create(SourceInput(title='Harbor Web README',version='1.0',text=text))])


def test_rst_structure_preserves_wrapping_and_indented_code():
    blocks = parse_document(RST)
    quotes = [RST[b.start:b.end] for b in blocks]
    assert all(q.strip() == q for b,q in zip(blocks,quotes) if b.kind not in ('code','table'))
    assert any('toolkit for HTTP' in q and '\nrequest handling' in q for q in quotes)
    assert any('routing system' in q and 'continuation belongs' in q for q in quotes)
    code = [b for b in blocks if b.kind == 'code']
    assert len(code) == 2
    assert code[0].headings == ('Harbor Web','Installing')
    assert code[1].headings == ('Harbor Web','A Simple Example')
    assert 'return Response' in RST[code[1].start:code[1].end]
    assert not any(q.startswith('.. _HTTP') for q in quotes)
    assert all(b.start < b.end for b in blocks)
    literal='    first = 1\n    second = 2'
    block=parse_document(literal)[0]
    assert block.kind == 'code' and literal[block.start:block.end] == literal


def test_markdown_code_table_bullet_and_hierarchy():
    text = '# Guide\n\n## Setup\n\nInstall the package\nwith pip.\n\n- A feature\n  continued here.\n- Another one\n\n```python\n# not a heading\nprint("hello")\n\nprint("done")\n```\n\n## Options\n\n| Key | Value |\n| --- | --- |\n| PORT | 80 |\n'
    blocks = parse_document(text)
    assert [b.kind for b in blocks] == ['paragraph','list-item','list-item','code','table']
    assert blocks[-1].headings == ('Guide','Options')
    assert '# not a heading' in text[blocks[3].start:blocks[3].end]
    assert text[blocks[0].start:blocks[0].end] == 'Install the package\nwith pip.'


@pytest.mark.parametrize('ending',['\n','\r\n'])
def test_unicode_offsets_exact_and_entity_spellings(ending):
    state = analyze(workspace(('# Guide\n\n🧭 Résumé: use `camelCase` and `request_timeout`.\n\n## Example\n\n```python\nfrom harbor.wrappers import Request, Response\nResponse("hello")\n```').replace('\n',ending)))
    for c in state.claims:
        source = state.sources[0]
        assert source.text[c.start:c.end] == c.quote
        for mention in c.document.mentions:
            assert source.text[mention.start:mention.end] == mention.name
    assert any(m.name=='camelCase' for c in state.claims for m in c.document.mentions)
    assert any(m.name=='Response' and m.kind=='api' for c in state.claims for m in c.document.mentions)


def test_typed_rules_do_not_match_prose_imports_or_execute_code():
    text = 'Generating URLs from paths is useful.\nfrom harbor.wrappers import Request, Response\n@Request.application\ndef handler(request):\n    return Response("hello")\nPORT_NUMBER = 80\nPOST /api/widgets\npip install harbor\n'
    rows = extract_entities(text)
    actual = {(m.name,m.kind) for m in rows}
    assert ('paths','package') not in actual
    assert ('Request','api') in actual and ('Response','api') in actual
    assert ('Request.application','api') in actual
    assert ('harbor.wrappers','package') in actual
    assert ('PORT_NUMBER','configuration') in actual
    assert ('POST /api/widgets','endpoint') in actual
    assert ('pip install harbor','command') in actual
    assert all(text[m.start:m.end] == m.name for m in rows)


def test_pipeline_purposes_topics_and_representatives():
    state = analyze(workspace())
    p = state.analysis.pipeline
    assert p.passages == len(state.claims) and p.code_blocks == 2
    assert p.embedding_dimensions == 48 and p.training_examples == 72
    install = next(c for c in state.claims if 'pip install -U' in c.quote)
    example = next(c for c in state.claims if 'from harbor.wrappers' in c.quote)
    assert install.document.purpose == 'installation'
    assert example.document.purpose == 'example'
    assert example.topic == 0 and example.document.topic_strength == 0
    assert all(t.id>0 for t in state.topics)
    assert all(t.count == sum(c.topic == t.id for c in state.claims) for t in state.topics)
    assert all(len(t.terms)==len(t.weights) for t in state.topics)
    assert all(state.claims[next(i for i,c in enumerate(state.claims) if c.id==ident)].topic == t.id for t in state.topics for ident in t.representatives)
    assert all('code-block' not in term for t in state.topics for term in t.terms)
    assert any(c.document.examples for c in state.claims)


@pytest.mark.parametrize('text',['A short document.','the and or is to of','alpha beta gamma.\n\nalpha beta gamma.\n\nalpha beta gamma.\n\nalpha beta gamma.'])
def test_tiny_repetitive_or_stopword_corpora_do_not_force_topics(text):
    state = analyze(workspace(text))
    assert not state.topics
    assert any('No topics' in n or 'no topics' in n for n in state.analysis.pipeline.notices)


def test_unseen_vocabulary_abstains():
    result = classify_documents(['zzqvxy florpz quxx'])[0]
    assert result['purpose'] == 'other'
    assert not result['examples']


def test_held_out_purpose_classification_is_separate_from_training():
    root=Path(__file__).resolve().parents[1]/'data'
    cases=json.loads((root/'document-evaluation.json').read_text())['examples']
    training=json.loads((root/'document-training.json').read_text())['examples']
    assert not {text for _,text in cases} & {text for _,text in training}
    actual=[r['purpose'] for r in classify_documents([t for _,t in cases])]
    assert f1_score([label for label,_ in cases],actual,average='macro') >= .70, list(zip(cases,actual))


def test_large_prose_splits_but_code_and_table_stay_intact():
    text='A useful explanation about a client. '*120+'\n\n```python\n'+('x = 1\n'*350)+'```'
    blocks=parse_document(text)
    assert len([b for b in blocks if b.kind=='code'])==1
    assert all(b.end-b.start<=1800 for b in blocks if b.kind=='paragraph')
    assert max(b.end-b.start for b in blocks if b.kind=='code')>1800


@pytest.mark.parametrize('mutation',[
    lambda c: setattr(c.document.mentions[0],'name','forged'),
    lambda c: setattr(c.document.mentions[0],'start',c.start-1 if c.start else 999),
    lambda c: setattr(c.document.mentions[0],'normalized','forged'),
])
def test_import_rejects_forged_entity_offsets(mutation):
    state=analyze(workspace())
    claim=next(c for c in state.claims if c.document.mentions)
    mutation(claim)
    with pytest.raises(ValidationError): Workspace.model_validate(state.model_dump())


def test_legacy_snapshots_and_reviews_remain_compatible(tmp_path):
    state=analyze(workspace())
    from backend.models import Review
    claim=state.claims[0]
    claim.review=Review(status='applicable',note='Read original context',by='Reviewer',at='2026-10-17')
    again=analyze(state)
    assert again.claims[0].review.note=='Read original context'
    payload=again.model_dump()
    for c in payload['claims']: c.pop('document')
    payload['analysis'].pop('pipeline')
    for t in payload['topics']:
        for name in ('weights','representatives','source_count'): t.pop(name)
    legacy=Workspace.model_validate(payload)
    assert legacy.claims[0].document is None
    assert analyze(legacy).analysis.pipeline
    store=Store(tmp_path/'docs.sqlite3')
    store.save(again,store.read().revision,'Reviewer','NLP analysis')
    restored=store.read()
    assert restored.analysis.pipeline == again.analysis.pipeline
    assert restored.claims[0].document == again.claims[0].document
    assert retrieve(restored,'request headers','vector')


def test_bounded_passage_count_uses_blocks_not_wrapped_lines():
    state=analyze(workspace('word\n'*201))
    assert len(state.claims)==1
    with pytest.raises(ValueError,match='200 claims'):
        analyze(workspace('- item\n'*201))


def test_topic_representatives_cannot_point_outside_their_members():
    state=analyze(workspace())
    state.topics[0].representatives=['c-nonexistent']
    with pytest.raises(ValidationError,match='topic representative'):
        Workspace.model_validate(state.model_dump())


def test_analysis_route_persists_pipeline_with_existing_revision_guards(tmp_path):
    from fastapi.testclient import TestClient
    from backend.app import create_app
    app=create_app(tmp_path,auth_enabled=False,origins=['http://testserver'])
    origin={'Origin':'http://testserver'}
    with TestClient(app) as client:
        response=client.post('/api/sources',json={'revision':0,'source':workspace().sources[0].model_dump(exclude={'id','sha256'})},headers=origin)
        assert response.status_code==200
        revision=response.json()['revision']
        response=client.post('/api/analyze',json={'revision':revision},headers=origin)
        assert response.status_code==200
        data=response.json()
        assert data['analysis']['pipeline']['version']=='documentation-v1'
        assert all(c['document'] for c in data['claims'])
        assert client.get('/api/export').json()['analysis']['pipeline']==data['analysis']['pipeline']
        assert client.post('/api/analyze',json={'revision':revision},headers=origin).status_code==409
        assert client.post('/api/analyze',json={'revision':data['revision']}).status_code==403
