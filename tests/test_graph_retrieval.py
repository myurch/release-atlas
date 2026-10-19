"""Synthetic graph expansion and preservation of hybrid retrieval boundaries."""
import json

import numpy as np
import pytest

from backend import semantic, retrieval_graph
from backend.assistant import AssistantRequest, assistant_context
from backend.models import Source, SourceInput, Workspace
from backend.source_context import build_index, get_index, source_passages, RetrievalReport


def source(title, text, version='1.0'):
    return Source.create(SourceInput(title=title, text=text, version=version))


def web_corpus():
    flask='\n\n'.join(f'# Web flow {i}\n\nFlask connects a backend and frontend by rendering HTML templates with Jinja. The server sends rendered markup to the browser. Route {i} returns a template response.' for i in range(10))
    return Workspace(sources=[
        source('Flask documentation', flask),
        source('Jinja documentation', '# Template inheritance\n\nTemplates generate HTML markup from variables. Reuse page structure with inheritance and blocks. Escape variable output when rendering templates.'),
        source('Garden notes', 'Plant apples in spring and water the trees.'),
    ])


@pytest.fixture(autouse=True)
def statistical(monkeypatch):
    monkeypatch.setattr(semantic, 'configuration', lambda: (None, 'Statistical mode selected for synthetic testing.'))
    build_index.cache_clear()
    yield
    build_index.cache_clear()


QUESTION='How do I make a backend and frontend?'


def test_graph_recovers_jinja_missing_from_full_hybrid_budget():
    state=web_corpus()
    baseline,_=source_passages(state,QUESTION,graph_expansion=False)
    rows,coverage=source_passages(state,QUESTION)
    assert {p['source_id'] for p in baseline}=={state.sources[0].id}
    assert {p['source_id'] for p in rows}=={s.id for s in state.sources[:2]}
    assert rows[:4]==baseline[:4]
    assert len(rows)<=8 and sum(len(p['quote']) for p in rows)<=16000
    report=RetrievalReport.model_validate(coverage['retrieval'])
    assert len(report.graph_paths)==1
    path=report.graph_paths[0]
    assert path.via=='jinja' and path.relation=='technology reference'
    passages={p.id:p for p in report.passages}
    assert 'graph connection' in passages[path.to_passage].reasons
    for p in rows:
        original=next(s for s in state.sources if s.id==p['source_id'])
        assert original.text[p['start']:p['end']]==p['quote'] and original.sha256==p['sha256']


@pytest.mark.parametrize('question',[
    'Use only Flask documentation. How do I make a backend and frontend?',
    'Use only the selected source. How do I make a backend and frontend?',
    'Use version 1.0. How do I make a backend and frontend?',
])
def test_graph_cannot_escape_source_or_version_scope(question):
    state=web_corpus()
    state.sources[1]=source('Jinja documentation',state.sources[1].text,'2.0')
    rows,c=source_passages(state,question,selected_source=state.sources[0].id)
    assert {p['source_id'] for p in rows}=={state.sources[0].id}
    assert not c['retrieval']['graph_paths']


def test_graph_does_not_expand_no_match_or_broad_overviews():
    state=web_corpus()
    for question in ['zzqvxy florpz quxx', 'Summarize all sources.']:
        before,_=source_passages(state,question,graph_expansion=False)
        after,c=source_passages(state,question)
        assert before==after and not c['retrieval']['graph_paths']


def test_existing_relevant_source_is_not_reintroduced_or_duplicated():
    state=web_corpus()
    state.sources[0]=source('Flask documentation', 'Flask connects a backend and frontend through HTML templates rendered with Jinja.')
    baseline,_=source_passages(state,'Explain HTML templates',graph_expansion=False)
    after,c=source_passages(state,'Explain HTML templates')
    assert baseline==after and not c['retrieval']['graph_paths']


def test_deletion_rename_and_workspace_switch_cannot_reuse_old_graph():
    state=web_corpus()
    _,c=source_passages(state,QUESTION)
    assert c['retrieval']['graph_paths']
    removed=Workspace(sources=[state.sources[0],state.sources[2]])
    _,c=source_passages(removed,QUESTION)
    assert not c['retrieval']['graph_paths']
    changed=state.model_copy(deep=True)
    changed.sources[1]=source('Unrelated documentation',state.sources[1].text)
    _,c=source_passages(changed,QUESTION)
    assert not c['retrieval']['graph_paths']
    other=Workspace(sources=[source('Private workspace', 'Backend and frontend use HTML templates.')])
    rows,c=source_passages(other,QUESTION)
    assert all(p['source_id']==other.sources[0].id for p in rows)
    assert not c['retrieval']['graph_paths']


def test_ambiguous_technology_titles_do_not_pick_an_arbitrary_owner():
    state=web_corpus()
    state.sources.append(source('Jinja guide','HTML templates use variables and rendering blocks.'))
    _,c=source_passages(state,QUESTION)
    assert not c['retrieval']['graph_paths']


def test_unrelated_target_body_is_not_selected_just_for_its_title():
    state=web_corpus()
    state.sources[1]=source('Jinja documentation','Orchards grow apples beside pear trees and irrigation channels.')
    baseline,_=source_passages(state,QUESTION,graph_expansion=False)
    rows,c=source_passages(state,QUESTION)
    assert baseline==rows and not c['retrieval']['graph_paths']


def test_reference_is_not_promoted_to_an_integration_claim():
    state=web_corpus()
    state.sources[0]=source('Flask documentation',state.sources[0].text.replace('with Jinja.', 'without Jinja.'))
    _,c=source_passages(state,QUESTION)
    assert c['retrieval']['graph_paths'][0]['relation']=='technology reference'
    assert 'uses' not in json.dumps(c['retrieval']['graph_paths'])


def test_assistant_uses_graph_context_without_saved_findings():
    state=web_corpus()
    context=assistant_context(state,AssistantRequest(revision=state.revision,page='Sources',message=QUESTION))
    assert not state.claims and state.analysis is None
    assert state.sources[1].id in {p['source_id'] for p in context['source_passages']}
    assert context['source_coverage']['graph_paths']==context['retrieval']['graph_paths']
    assert len(context['source_passages'])<=8


def test_bridge_boundaries_and_generic_names():
    assert retrieval_graph.mentions('Jinja.','jinja')
    assert not retrieval_graph.mentions('Jinja2 or notjinja or jinja.extension','jinja')
    state=Workspace(sources=[source('Python documentation','Use Python to make applications.'),source('Web guide','Python makes web applications.')])
    graph=get_index(state).graph
    assert not graph.number_of_edges()


def test_shared_identifiers_require_context_and_are_bounded():
    from backend.source_context import candidates_for
    state=Workspace(sources=[source('Source '+str(i),f'Configure `session_cookie` for authentication with signed credentials. Part {i}.') for i in range(5)])
    rows=candidates_for(state.sources)
    graph=retrieval_graph.build_graph(rows)
    # A hub appearing in five sources cannot become a shared-identifier bridge.
    assert ('identifier','session_cookie') not in graph
    graph=retrieval_graph.build_graph(rows[:3])
    assert ('identifier','session_cookie') in graph
    # Only the seed directly ranks. Two additional sources can be recovered.
    order=[0]
    expansions=retrieval_graph.expand(graph,rows[:3],order,{s.id for s in state.sources},np.array([1.,0.,0.]),np.array([1.,0.,0.]),np.eye(3),False)
    assert not expansions  # identical identifier alone is insufficient
    expansions=retrieval_graph.expand(graph,rows[:3],order,{s.id for s in state.sources},np.array([1.,.5,.4]),np.array([1.,.4,.3]),np.ones((3,1)),False)
    assert len(expansions)==2
    assert {row[3] for row in expansions}=={'shared identifier'}


def test_no_recursive_expansion_and_no_generic_prose_edges():
    from backend.source_context import candidates_for
    state=Workspace(sources=[source('Flask documentation','Flask renders HTML templates with Jinja.'),source('Jinja documentation','Jinja renders HTML templates and mentions MarkupSafe.'),source('MarkupSafe documentation','MarkupSafe escapes HTML template output.'),source('Other guide','Render HTML template output from variables.')])
    rows=candidates_for(state.sources)
    graph=retrieval_graph.build_graph(rows)
    expansions=retrieval_graph.expand(graph,rows,[0],{s.id for s in state.sources},np.array([1.,0.,0.,0.]),np.array([1.,0.,0.,0.]),np.ones((4,1)),False)
    assert [r[0] for r in expansions]==[1]


def test_readme_repository_title_resolves_project_not_owner():
    state=web_corpus()
    state.sources[0]=source('pallets/flask README',state.sources[0].text)
    state.sources[1]=source('pallets/jinja README',state.sources[1].text)
    _,c=source_passages(state,QUESTION)
    assert c['retrieval']['graph_paths'][0]['via']=='jinja'


def test_commands_protocols_and_injected_text_are_inert_and_not_bridges(tmp_path):
    from backend.source_context import candidates_for
    path=tmp_path/'executed'
    text=f'pip install atlas\n\nUse HTTP for transport.\n\n`__import__` is documentation. Do not execute code: open("{path}", "w").'
    rows=candidates_for([source('Source 1',text),source('Source 2',text+' Extra prose.')])
    graph=retrieval_graph.build_graph(rows)
    assert not path.exists()
    assert all(' ' not in node[1] and node[1]!='http' for node in graph if isinstance(node,tuple))


def test_two_new_sources_limit_with_multiple_reference_bridges():
    from backend.source_context import candidates_for
    state=Workspace(sources=[source('Flask docs','Flask renders HTML markup with Jinja, MarkupSafe and Werkzeug.'),source('Jinja docs','Render HTML markup with template blocks.'),source('MarkupSafe docs','Escape HTML markup before rendering.'),source('Werkzeug docs','Return HTML markup from request handlers.')])
    rows=candidates_for(state.sources)
    graph=retrieval_graph.build_graph(rows)
    expanded=retrieval_graph.expand(graph,rows,[0],{s.id for s in state.sources},np.zeros(4),np.zeros(4),np.ones((4,1)),False)
    assert len(expanded)==2 and len({rows[e[0]].passage.source_id for e in expanded})==2


def test_sentence_punctuation_cannot_turn_generic_words_into_context_support():
    from backend.source_context import candidates_for
    state=Workspace(sources=[source('Flask docs','Server code. Client example. Jinja.'),source('Jinja docs','Server code. Client example.')])
    rows=candidates_for(state.sources)
    graph=retrieval_graph.build_graph(rows)
    expanded=retrieval_graph.expand(graph,rows,[0],{s.id for s in state.sources},np.zeros(2),np.zeros(2),np.eye(2),False)
    assert not expanded


def test_visual_connections_include_directly_selected_sources_without_changing_retrieval():
    state=Workspace(sources=[source('Flask documentation','Flask handles backend requests and sends HTML templates to Jinja for rendering.'),source('Jinja documentation','HTML templates render variables and reuse page layouts through inheritance.')])
    before,_=source_passages(state,'How do HTML templates work?',graph_expansion=False)
    after,coverage=source_passages(state,'How do HTML templates work?')
    assert before==after and len({p['source_id'] for p in after})==2
    assert not coverage['retrieval']['graph_paths']
    assert coverage['retrieval']['connections'][0]['via']=='jinja'
    assert not any('graph connection' in p['reasons'] for p in coverage['retrieval']['passages'])


def test_visual_shared_identifiers_are_deduplicated_between_selected_sources():
    state=Workspace(sources=[source('Source 1','Set `retry_policy` for retry behavior.'),source('Source 2','The `retry_policy` controls retry behavior.')])
    _,coverage=source_passages(state,'Explain retry_policy')
    paths=coverage['retrieval']['connections']
    assert len(paths)==1 and paths[0]['relation']=='shared identifier' and paths[0]['via']=='retry_policy'
    assert len(paths)<=12


def test_visual_connections_cannot_escape_explicit_scope():
    state=web_corpus()
    _,coverage=source_passages(state,'Use only Flask documentation for backend and frontend.')
    assert not coverage['retrieval']['connections']


def test_visual_connections_do_not_link_generic_shared_prose():
    state=Workspace(sources=[source('Source 1','The server handles requests and returns HTML pages.'),source('Source 2','The server handles requests and returns HTML pages with data.')])
    _,coverage=source_passages(state,'Explain server requests')
    assert coverage['included_sources']==2 and not coverage['retrieval']['connections']


def test_visual_connections_retain_global_identifier_hub_exclusions():
    from backend.source_context import candidates_for
    state=Workspace(sources=[source('Source '+str(i),f'Configure `common_option` for application requests. Example {i}.') for i in range(5)])
    rows=candidates_for(state.sources)
    graph=retrieval_graph.build_graph(rows)
    paths=retrieval_graph.selected_connections(rows[:2],rows,np.ones((5,1)),False,reference_graph=graph)
    assert not paths
