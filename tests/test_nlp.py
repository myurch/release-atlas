import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from sklearn.metrics import f1_score

from backend.models import Source, SourceInput, Usage, Workspace
from backend.nlp import analyze, assertion, classify, entities, retrieve

ROOT = Path(__file__).resolve().parents[1]


def demo():
    data = json.loads((ROOT/'data/demo-input.json').read_text())
    return Workspace(title=data['title'], sources=[Source.create(SourceInput(**s)) for s in data['sources']], usage=[Usage(**u) for u in data['usage']])


def test_classification_held_out():
    examples = json.loads((ROOT/'data/evaluation.json').read_text())['examples']
    actual = [label for label, _ in classify([text for _, text in examples])]
    expected = [label for label, _ in examples]
    assert f1_score(expected, actual, average='macro') >= 0.70, list(zip(expected, actual))


def test_entity_offsets_conflicts_and_topics():
    state = analyze(demo())
    assert len(state.claims) == 12
    assert len(state.topics) == 4
    conflicts = [c for c in state.claims if c.conflicts]
    assert len(conflicts) == 2
    versions = {s.id:s.version for s in state.sources}
    assert all(versions[c.source_id] == '2.0' for c in conflicts)
    assert entities('Use `retry_limit` with fetchRecords and pool_size.') == ['fetchrecords', 'pool_size', 'retry_limit']
    assert assertion('The `retry_limit` is not removed.', 'retry_limit') is None
    for c in state.claims:
        s = next(s for s in state.sources if s.id == c.source_id)
        assert s.text[c.start:c.end] == c.quote
    assert any(n.kind == 'component' for n in state.graph.nodes)


def test_graph_bridge_retrieval():
    state = analyze(demo())
    baseline = retrieve(state, 'What affects Checkout service?', 'lexical')
    graph = retrieve(state, 'What affects Checkout service?', 'graph')
    assert not baseline
    assert len(graph) >= 2
    assert any('retry_limit' in row['claim']['entities'] for row in graph)
    assert not retrieve(state, 'quuxnotaword', 'lexical')


def test_import_rejects_forged_quote_and_hash():
    payload = analyze(demo()).model_dump()
    payload['claims'][0]['quote'] = 'A fabricated quote'
    with pytest.raises(ValidationError):
        Workspace.model_validate(payload)
    payload = demo().model_dump()
    payload['sources'][0]['text'] += 'modified'
    with pytest.raises(ValidationError):
        Workspace.model_validate(payload)


def test_blank_tiny_unicode_and_excessive_sources():
    with pytest.raises(ValidationError):
        SourceInput(title='x', version='1.0', text='   ')
    state = Workspace(sources=[Source.create(SourceInput(title='Unicode', version='1.0', text='  支持 `example_option`。\n'))])
    result = analyze(state)
    assert result.claims[0].start == 2
    assert result.claims[0].entities == ['example_option']
    with pytest.raises(ValueError, match='200 claims'):
        analyze(Workspace(sources=[Source.create(SourceInput(title='many', version='1.0', text='line\n'*201))]))
