"""Opt-in paid behavioral evaluation through Atlas's production assistant adapter.

Synthetic inputs only. No user workspace is opened or modified. Automated checks
are outcome heuristics; inspect stored answers before accepting the result.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

import httpx
from backend import assistant
from backend.config import load_env
from backend.providers import ProviderConfig, ProviderError
from backend.calculator import INSTRUCTIONS as CALCULATION_INSTRUCTIONS
from backend.source_actions import INSTRUCTIONS as SOURCE_INSTRUCTIONS
from assistant_cases import cases


class Meter(httpx.AsyncBaseTransport):
    def __init__(self):
        self.inner = httpx.AsyncHTTPTransport()
        self.calls = 0
        self.last_output = []
        self.tool_results = []
        self.seen_results = set()
        self.usage = {'input_tokens':0,'output_tokens':0}

    async def handle_async_request(self, request):
        self.calls += 1
        self.last_output = []
        for item in json.loads(request.content).get('input', []):
            if item.get('type') == 'function_call_output' and item['call_id'] not in self.seen_results:
                self.seen_results.add(item['call_id'])
                self.tool_results.append(json.loads(item['output']))
        response = await self.inner.handle_async_request(request)
        await response.aread()
        if response.status_code == 200:
            body = response.json()
            self.last_output = [part.get('text', '') for item in body.get('output', [])
                                for part in item.get('content', []) if part.get('type') == 'output_text']
            usage = body.get('usage', {})
            for key in self.usage:
                self.usage[key] += usage.get(key, 0)
        return response

    async def aclose(self):
        await self.inner.aclose()


def grade(case, reply, state):
    # Word-number normalization keeps the checks independent of surface formatting.
    text = reply.answer.casefold()
    for word, value in {'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fifteen':15}.items():
        text = re.sub(r'\b'+word+r'\b', str(value), text)
    problems = []
    if reply.source_action is not None:
        problems.append('Unexpected source action for a read-only evaluation question')
    if case.lead:
        lead = text[:220]
        if not re.search(case.lead, lead, re.I):
            problems.append('Expected result missing near the beginning')
        if re.search(r'cannot|can.t|unable|not possible', lead):
            problems.append('Response refuses an answerable question')
    for pattern in case.must:
        if not re.search(pattern, text, re.I):
            problems.append('Missing expected answer content: '+pattern)
    for pattern in case.forbidden:
        if re.search(pattern, reply.answer, re.I):
            problems.append('Forbidden output: '+pattern)
    source_ids = {p.source_id for p in reply.source_passages}
    source_ids |= {c.source_id for c in state.claims if c.id in reply.citations}
    titles = {s.title for s in state.sources if s.id in source_ids}
    for title in case.cited:
        if title not in titles:
            problems.append('Missing supporting citation: '+title)
    return problems


async def main(args):
    if not args.live:
        raise SystemExit('Use --live to authorize billable API requests with synthetic data only.')
    load_env()
    config = ProviderConfig.environment()
    if config.kind != 'openai' or config.model != 'gpt-6-luna' or not config.key.strip():
        raise SystemExit('Configure GPT-6 Luna and OPENAI_API_KEY in .env or the server environment. No request sent.')
    selected = [c for c in cases() if args.suite == 'all' or c.suite == args.suite]
    if args.case:
        selected = [c for c in selected if c.name in args.case]
    if not selected:
        raise SystemExit('No matching cases')
    report = {'label':args.label,'model':config.model,'reasoning_effort':'none',
              'created_at':datetime.now(timezone.utc).isoformat(), 'grader_version':2,
              'prompt_sha256':hashlib.sha256((assistant.MANUAL+'\n'+CALCULATION_INSTRUCTIONS).encode()).hexdigest(),
              'prompt':assistant.MANUAL+'\n'+CALCULATION_INSTRUCTIONS,
              'source_action_prompt_when_enabled':SOURCE_INSTRUCTIONS, 'synthetic_only':True,'cases':[],
              'limitations':['Finite synthetic evaluation; no universal correctness guarantee',
                             'Automated outcome checks require human inspection of answers',
                             'Conservative cost estimate ignores input caching discounts']}
    destination = ROOT / 'validation' / ('assistant-eval-'+args.label+'.json')
    meter = Meter()
    try:
        for repetition in range(args.repeats):
            for case in selected:
                state, request = case.input()
                started = time.monotonic()
                tool_start = len(meter.tool_results)
                enabled = assistant.source_action_requested(state, request.message, request.selected_source)
                effective = report['prompt'] + ('\n'+SOURCE_INSTRUCTIONS if enabled else '')
                row = {'name':case.name,'repetition':repetition+1,'question':case.question,
                       'source_tools_enabled':enabled,'prompt_sha256':hashlib.sha256(effective.encode()).hexdigest()}
                try:
                    # A new transport per request matches the production client's lifecycle.
                    reply = await assistant.assist(config, state, request, meter)
                    issues = grade(case, reply, state)
                    row['tool_results'] = meter.tool_results[tool_start:]
                    if case.tool_result and not any(r.get('result') == case.tool_result for r in row['tool_results']):
                        issues.append('Expected backend calculation result was not used')
                    row.update(reply=reply.model_dump(), problems=issues, passed=not issues)
                except ProviderError as error:
                    row.update(passed=False, problems=[str(error)], raw_model_output=meter.last_output)
                    if any(term in str(error) for term in ['API key','quota','denied access']):
                        raise
                row['elapsed_seconds'] = round(time.monotonic()-started, 3)
                report['cases'].append(row)
                report.update(requests=meter.calls, usage=meter.usage.copy(),
                              estimated_cost_usd=round((meter.usage['input_tokens']*.10+meter.usage['output_tokens']*.50)/1_000_000,6))
                report['passed'] = sum(r['passed'] for r in report['cases'])
                report['total'] = len(report['cases'])
                report['result'] = 'PASS' if report['passed'] == report['total'] else 'FAIL'
                destination.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
                print(json.dumps({'name':case.name,'run':repetition+1,'passed':row['passed'],'problems':row['problems'],
                                  'answer':row.get('reply',{}).get('answer','')[:700]}), flush=True)
    except ProviderError as error:
        raise SystemExit(str(error)) from None
    print(json.dumps({'report':str(destination),'result':report['result'],'passed':report['passed'],
                      'total':report['total'],'requests':meter.calls,'estimated_cost_usd':report['estimated_cost_usd']}))
    if report['result'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--suite', choices=['core','extended','holdout','clarification','calculation','all'], default='core')
    parser.add_argument('--repeats', type=int, choices=[1,2,3], default=1)
    parser.add_argument('--label', default='candidate', type=lambda s: s if re.fullmatch('[a-z0-9-]+',s) else parser.error('Use a lowercase label'))
    parser.add_argument('--case', action='append')
    asyncio.run(main(parser.parse_args()))
