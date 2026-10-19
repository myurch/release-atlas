"""Bounded workspace assistance, validated citations and confirmable source proposals."""
from __future__ import annotations

import json
from typing import Literal

from pydantic import Field
from starlette.concurrency import run_in_threadpool

from .models import MAX_REVISION, Strict, Workspace
from .nlp import source_digest
from .source_context import SourcePassage, RetrievalReport, source_passages
from .providers import ProviderConfig, ProviderError, answer_content, openai_answer, post
from .prompts import EVIDENCE_POLICY
from .source_actions import PreparedSourceAction, SourceActions, source_action_requested

Page = Literal['Overview', 'Evidence', 'Sources', 'Graph', 'Questions', 'Activity']


class ChatMessage(Strict):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=4000)


class AssistantRequest(Strict):
    revision: int = Field(ge=0, le=MAX_REVISION-1, strict=True)
    page: Page = 'Overview'
    selected_claim: str = Field(default='', max_length=100)
    selected_source: str = Field(default='', max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=10)


class AssistantAnswer(Strict):
    answer: str = Field(min_length=1, max_length=4000)
    citations: list[str] = Field(default_factory=list, max_length=8)
    uncertainty: str = Field(default='', max_length=1000)
    source_citations: list[str] = Field(default_factory=list, max_length=8)


class AssistantReply(AssistantAnswer):
    source_passages: list[SourcePassage] = Field(default_factory=list, max_length=8)
    source_action: PreparedSourceAction | None = None
    retrieval: RetrievalReport | None = None


MANUAL = EVIDENCE_POLICY + '\n' + '''You are Atlas, the assistant inside Release Atlas.
Use plain language and concise paragraphs, usually under 180 words. Use numbered steps for workflows.
Lead with the result. No em dashes, HTML or Markdown tables.

Available context:
context.sources inventories every saved source with title, version and identity. Join each source_passage
by source_id to that inventory to understand its version. Only source_passages contains readable original
text; evidence contains analyzed findings. Read saved text even before analysis or when there are zero
findings. If analysis_ready is false, ignore old findings and answer from current source_passages.
If source_coverage.partial is true, answer from the supplied passages and mention that coverage is partial;
do not describe the answer as a complete review of all saved text. Do not refuse a supported local answer.
Only when manage_source is supplied, you may propose adding or deleting a bounded source batch for user confirmation.
Without that tool, source changes are unavailable. You cannot make any other workspace changes,
run code, browse, inspect disk files or upload files. You may explain
code present in the supplied source text. General knowledge is allowed when clearly distinguished from
workspace facts. Do not claim actions were performed or files were inspected.

Application workflow:
- Sources has fields Source title, Version, Source URL (optional), License / permission, Source text,
  and Save source. Paste text, fill the required fields and save. Saving does not run analysis automatically.
  Source URLs are references, not automatic scraping. In live mode each saved card has a Delete source
  icon with inline confirmation; it removes dependent findings and answers, then requires reanalysis.
  The GitHub release feed imports public release notes. PDF, Word and folder uploads are unsupported.
- Overview's usage profile lists application component | exact API_or_setting identifier. Choose Save
  profile, then Analyze sources to create findings, topics and a graph. Suggest analysis when needed for
  those features, not as a prerequisite for reading or summarizing saved text.
- Evidence has filters, exact quotes, source links, same-version conflict candidates and review decisions.
  Classification scores are uncalibrated, entity/conflict extraction uses rules and usage matches are suggestions.
- Graph follows source/finding/identifier/component connections. Questions retrieves evidence using lexical,
  statistical vector or graph methods and can save a model-drafted cited answer. This chat is separate,
  private to the current browser view and does not save shared answers or review decisions.
- Activity lists the latest 200 changes. Workspaces creates or switches saved reviews; switching affects
  connected users. Export snapshot includes source text and review names. Import validates a JSON snapshot
  and creates a separate saved workspace in live mode. Standalone/hosted views cannot run live analysis or
  model chat. The beginner tutorial uses prepared temporary data and never writes to the API or calls models.
For guidance use exact UI labels and the supplied next_steps when relevant to the actual question.

Return exactly one JSON object with answer (string), citations (list of provided finding IDs, possibly
empty), uncertainty (short string, possibly empty), source_citations (list of provided passage IDs,
possibly empty). Citation IDs are separate from answer text.'''



def assistant_context(state: Workspace, request: AssistantRequest):
    ready = bool(state.analysis and source_digest(state) == state.analysis.source_digest)
    query = request.message
    selected_source = request.selected_source or next((c.source_id for c in state.claims if c.id == request.selected_claim), '')
    passages, coverage = source_passages(state, query, selected_source, history=request.history, selected_claim=request.selected_claim)
    retrieval = coverage.pop('retrieval')
    coverage['encoder'] = retrieval['encoder']
    coverage['notices'] = retrieval['notices']
    coverage['graph_paths'] = retrieval['graph_paths']
    coverage['selection_reasons'] = [{'passage_id':p['id'],'reasons':p['reasons']} for p in retrieval['passages']]
    rows = []
    if ready:
        # Findings can annotate the chosen passages, not introduce an unrelated second retrieval path.
        seen = set()
        for passage in passages:
            matching = [c for c in state.claims if c.source_id == passage['source_id'] and c.start < passage['end'] and c.end > passage['start']]
            matching.sort(key=lambda c:(c.id != request.selected_claim,c.start))
            for claim in matching:
                if claim.id in seen: continue
                seen.add(claim.id)
                source = next(s for s in state.sources if s.id == claim.source_id)
                rows.append({'claim':claim.model_dump(),'source':{'title':source.title,'version':source.version}})
    # Keep conflict partners adjacent so a bounded context cannot hide the opposing passage.
    by_id = {c.id: c for c in state.claims}
    sources = {s.id: s for s in state.sources}
    unique = {}
    for row in rows:
        claim = by_id[row['claim']['id']]
        group = [claim] + [by_id[cid] for cid in claim.conflicts]
        if not all(any(p['source_id']==c.source_id and p['start']<c.end and p['end']>c.start for p in passages) for c in group):
            continue
        missing = [c for c in group if c.id not in unique]
        if len(unique) + len(missing) > 8:
            continue
        for c in missing:
            source = sources[c.source_id]
            unique[c.id] = {'id': c.id, 'quote': c.quote[:2000], 'source': {'title': source.title, 'version': source.version}}
    evidence = list(unique.values())
    def supports(claim):
        return ([claim.id] if claim.id in unique else []) + [p['id'] for p in passages
                if p['source_id'] == claim.source_id and p['start'] < claim.end and p['end'] > claim.start]
    pairs = sorted({tuple(sorted((c.id, other))) for c in state.claims
                    if ready and supports(c) for other in c.conflicts})
    conflicts = [{'claim_ids': list(pair), 'citation_groups': [supports(by_id[cid]) for cid in pair],
                  'status': 'Unresolved opposing statements in the same version; inspect both'} for pair in pairs]
    context = {
        'page': request.page, 'workspace': state.title, 'revision': state.revision,
        'analysis_ready': ready, 'source_count': len(state.sources), 'finding_count': len(state.claims) if ready else 0,
        'reviewed_count': sum(bool(c.review) for c in state.claims) if ready else 0,
        'sources': [{'id': s.id, 'title': s.title, 'version': s.version, 'origin': s.url, 'sha256': s.sha256, 'text_length': len(s.text)} for s in state.sources],
        'source_passages': passages, 'source_coverage': coverage,
        'next_steps': (
            ['Open Sources. Paste documentation into Source text and fill Source title, Version, and License / permission.',
             'Click Save source. Analysis does not run automatically.',
             'Open Overview. Edit usage profile using one component | identifier pair per line, then Save profile.',
             'Click Analyze sources in Overview. Then open Evidence to check quotes and save decisions.']
            if not state.sources else
            ['Check Sources and the usage profile in Overview.', 'Click Analyze sources in Overview.', 'Open Evidence to review the resulting findings.']
            if not ready else
            ['Open Evidence and inspect usage matches or conflicts.', 'Read original quotes and versions before saving a decision and note.', 'Use Graph or Questions for deeper investigation. Export snapshot keeps the saved review.']
        ),
        'usage': [u.model_dump() for u in state.usage], 'selected_claim': request.selected_claim,
        'selected_source': request.selected_source, 'evidence': evidence, 'retrieval':retrieval,
        'conflicts': conflicts,
    }
    return context


async def assist(config: ProviderConfig, state: Workspace, request: AssistantRequest, transport=None, *, context=None):
    source_actions = (SourceActions(state, request.message, request.selected_source)
        if config.kind == 'openai' and source_action_requested(state, request.message, request.selected_source) else None)
    if context is None:
        context = await run_in_threadpool(assistant_context, state, request)
    messages = [{'role': 'system', 'content': MANUAL}, {'role': 'user', 'content': json.dumps({'context': {k:v for k,v in context.items() if k != 'retrieval'}, 'conversation': [m.model_dump() for m in request.history], 'question': request.message}, ensure_ascii=False)}]
    payload = {'model': config.model, 'messages': messages, 'stream': False}
    if config.kind == 'openai':
        content = await openai_answer(config, messages, AssistantAnswer, 1500, transport,
                                     allowed_citations={'citations': [e['id'] for e in context['evidence']],
                                                        'source_citations': [p['id'] for p in context['source_passages']]},
                                     source_actions=source_actions)
    elif config.kind == 'ollama':
        payload.update(format='json', options={'temperature': 0.2, 'num_predict': 1500, 'num_ctx': 16384})
        if config.model.startswith('gpt-oss'): payload['think'] = 'low'
        raw = await post(config, '/api/chat', payload, transport)
        content = answer_content(raw, 'ollama')
    else:
        payload.update(temperature=0.2, max_tokens=1500, response_format={'type':'json_object'})
        if config.model.startswith('gpt-oss'): payload['reasoning_effort'] = 'low'
        raw = await post(config, '/chat/completions', payload, transport)
        content = answer_content(raw, 'compatible')
    try:
        answer = AssistantAnswer.model_validate_json(content)
    except (ValueError, TypeError) as exc:
        raise ProviderError('Assistant returned an invalid answer. Your workspace is unchanged.') from exc
    allowed = {e['id'] for e in context['evidence']}
    if not set(answer.citations).issubset(allowed):
        raise ProviderError('Assistant cited unavailable evidence. Try asking a more specific question.')
    passage_by_id = {p['id']: p for p in context['source_passages']}
    if not set(answer.source_citations).issubset(passage_by_id):
        raise ProviderError('Assistant cited unavailable source text. Try a more specific question.')
    cited = set(answer.citations) | set(answer.source_citations)
    for conflict in context['conflicts']:
        groups = [set(group) for group in conflict['citation_groups']]
        if any(cited & group for group in groups) and not all(cited & group for group in groups):
            raise ProviderError('Assistant omitted opposing evidence. Ask it to compare both conflicting passages, or inspect them in Evidence.')
    if any(any(set(group) & cited for group in c['citation_groups']) for c in context['conflicts']):
        answer.uncertainty = 'The cited sources contain conflicting statements. A conclusion under a stated assumption does not establish which source is correct. ' + answer.uncertainty[:850]
    answer.citations = list(dict.fromkeys(answer.citations))
    answer.answer = answer.answer.replace('\u2014', '; ')
    answer.uncertainty = answer.uncertainty.replace('\u2014', '; ')
    answer.source_citations = list(dict.fromkeys(answer.source_citations))
    if context['source_coverage']['partial']:
        answer.uncertainty = 'Only selected source passages were supplied; this is not a complete review of all source text. ' + answer.uncertainty[:850]
    if source_actions is not None and source_actions.prepared is not None:
        # Server wording, not model prose, is authoritative about mutation status.
        count = len(source_actions.prepared.items)
        answer.answer = f'Prepared {count} source change{"s" if count != 1 else ""}. Review every item below and confirm to apply the batch. No changes have been saved.'
    return AssistantReply(**answer.model_dump(), source_passages=[passage_by_id[cid] for cid in answer.source_citations],
                          source_action=source_actions.prepared if source_actions is not None else None,
                          retrieval=RetrievalReport.model_validate(context['retrieval']))
