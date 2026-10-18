"""Optional paid OpenAI smoke test using only the project's synthetic review."""
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.assistant import AssistantRequest, assist, assistant_context
from backend.config import load_env
from backend.models import Workspace
from backend.nlp import retrieve
from backend.providers import ProviderConfig, ProviderError, generate


async def main():
    load_env()
    config = ProviderConfig.environment()
    if config.kind != 'openai' or not config.key.strip():
        raise SystemExit('Set OPENAI_API_KEY in the server environment and use ATLAS_LLM_KIND=openai. No request was sent.')
    state = Workspace.model_validate_json((ROOT/'data/demo-snapshot.json').read_text())
    selected = next(c for c in state.claims if c.conflicts)
    start = time.monotonic()
    request = AssistantRequest(
        revision=state.revision, page='Evidence', selected_claim=selected.id,
        message='Summarize what the supplied sources say about retry_limit in version 2.0. Explain their disagreement and cite both passages.')
    chat = await assist(config, state, request)
    conflict = next(pair for pair in assistant_context(state, request)['conflicts'] if selected.id in pair['claim_ids'])
    cited = set(chat.citations) | set(chat.source_citations)
    if not all(cited.intersection(group) for group in conflict['citation_groups']):
        raise ProviderError('Synthetic smoke test did not cite both conflicting passages.')
    evidence = retrieve(state, 'What affects Checkout service?', 'graph')
    answer = await generate(config, 'What needs investigation before upgrading Checkout service?', evidence)
    report = {'result': 'PASS', 'provider': config.kind, 'model': config.model,
              'elapsed_seconds': round(time.monotonic()-start, 3), 'chat': chat.model_dump(),
              'answer': answer.model_dump(), 'requests': 2, 'material': 'Original synthetic Harbor SDK fixture only',
              'limits': ['Real API calls, not a representative quality or latency benchmark',
                         'Citation validation does not establish semantic accuracy']}
    (ROOT/'validation/openai-results.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except ProviderError as exc:
        raise SystemExit(str(exc)) from None
