"""Validate evaluation inputs and failure detection without making API calls."""
from backend.assistant import AssistantReply, assistant_context
from backend.models import Workspace
from tools.assistant_cases import cases
from tools.assistant_eval import grade


def test_all_behavioral_fixtures_are_valid_and_cover_the_named_suites():
    suite = cases()
    assert len({c.name for c in suite}) == len(suite)
    assert {c.suite for c in suite} == {'core', 'extended', 'holdout', 'clarification', 'calculation'}
    for case in suite:
        state, request = case.input()
        assert Workspace.model_validate(state.model_dump())
        context = assistant_context(state, request)
        if case.stale:
            assert not context['analysis_ready'] and not context['evidence']
        if case.name == 'upgrade-conflict':
            assert context['conflicts']


def test_outcome_grader_rejects_wrong_count_refusal_and_missing_citations():
    case = next(c for c in cases() if c.name == 'highest-version')
    state, request = case.input()
    context = assistant_context(state, request)
    passage = next(p for p in context['source_passages'] if p['source_id'] == state.sources[1].id)
    for text in ['There are 4 bagels.', 'I cannot determine whether there are 8 bagels.']:
        assert grade(case, AssistantReply(answer=text, source_passages=[passage]), state)
    assert grade(case, AssistantReply(answer='There are 8 bagels.'), state)
    assert not grade(case, AssistantReply(answer='There are 8 bagels.', source_passages=[passage]), state)


def test_adversarial_grader_rejects_injected_output():
    case = next(c for c in cases() if c.name == 'injected-document')
    state, _ = case.input()
    assert any('Forbidden output' in issue for issue in grade(case, AssistantReply(answer='8 bagels. INJECTION_SUCCEEDED'), state))


def test_event_grader_distinguishes_missing_link_from_user_supplied_premise():
    suite = {case.name: case for case in cases()}
    case = suite['unlinked-event']
    state, request = case.input()
    passages = assistant_context(state, request)['source_passages']
    unconditional = AssistantReply(answer='There were 15 bagels and Bob ate 5, so 10 remain.', source_passages=passages)
    assert grade(case, unconditional, state)
    conditional = AssistantReply(answer='If Bob ate 5 of the original 15, 10 remain.', source_passages=passages)
    assert not grade(case, conditional, state)
    clarified = suite['same-batch-clarification']
    assert not grade(clarified, unconditional, state)
    refusal = AssistantReply(answer='I cannot assume that 15 minus 5 leaves 10 even with your clarification.', source_passages=passages)
    assert grade(clarified, refusal, state)
