"""Bounded server-side model adapters. No browser-supplied endpoints or secrets."""
from __future__ import annotations

import asyncio
import json
import math
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx
from pydantic import Field

from .models import Strict
from .prompts import EVIDENCE_POLICY
from .calculator import Calculation, INSTRUCTIONS as CALCULATION_INSTRUCTIONS, calculate, tool_definition


class ProviderError(Exception):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    kind: str = 'openai'
    base: str = 'https://api.openai.com/v1'
    model: str = 'gpt-6-luna'
    key: str = field(default='', repr=False)
    timeout: float = 90.0

    def validate(self):
        parts = urlsplit(self.base)
        if self.kind not in ('openai', 'ollama', 'compatible') or not self.model.strip():
            raise ValueError('Invalid provider kind or model')
        if parts.username or parts.password or parts.query or parts.fragment or not parts.hostname:
            raise ValueError('Provider base must be an HTTP(S) URL without embedded credentials/query')
        if parts.scheme != 'https' and not (parts.scheme == 'http' and parts.hostname in ('localhost', '127.0.0.1', '::1', 'host.docker.internal')):
            raise ValueError('Remote providers require HTTPS')
        if self.kind == 'openai' and self.base.rstrip('/') != 'https://api.openai.com/v1':
            raise ValueError('The OpenAI provider requires https://api.openai.com/v1')
        return self

    @classmethod
    def environment(cls, prefix='ATLAS_LLM'):
        kind = os.getenv(prefix+'_KIND', 'openai' if prefix == 'ATLAS_LLM' else 'ollama')
        defaults = {'openai': ('https://api.openai.com/v1', 'gpt-6-luna'),
                    'ollama': ('http://localhost:11434', 'gemma4:12b'),
                    'compatible': ('http://localhost:11434/v1', 'gemma4:12b')}
        base, model = defaults.get(kind, ('', ''))
        key = os.getenv(prefix+'_KEY') or (os.getenv('OPENAI_API_KEY', '') if kind == 'openai' else '')
        return cls(kind=kind, base=os.getenv(prefix+'_BASE', base).rstrip('/'),
                   model=os.getenv(prefix+'_MODEL', model if prefix == 'ATLAS_LLM' else ''), key=key).validate()


async def post(config: ProviderConfig, path: str, payload: dict, transport=None):
    config.validate()
    if config.kind == 'openai' and not config.key.strip():
        raise ProviderError('OpenAI API key is missing. Set OPENAI_API_KEY in the server environment and restart Atlas. App guide is available without a key.')
    headers = {'Authorization': 'Bearer '+config.key} if config.key else {}
    try:
        async with asyncio.timeout(config.timeout):
            async with httpx.AsyncClient(timeout=config.timeout, trust_env=False, follow_redirects=False, transport=transport) as client:
                async with client.stream('POST', config.base.rstrip('/')+path, json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        if config.kind == 'openai':
                            messages = {401: 'OpenAI rejected the API key. Check the server credential and restart Atlas.',
                                        403: 'OpenAI denied access. Check the API project and model permissions.',
                                        404: 'The selected OpenAI model is unavailable to this API project.',
                                        429: 'OpenAI API quota or rate limit reached. Check API billing, spend limits and usage, then retry.'}
                            raise ProviderError(messages.get(response.status_code, f'OpenAI API returned HTTP {response.status_code}. Retry later or check the API service status.'))
                        raise ProviderError(f'Model service returned HTTP {response.status_code}. Check server-side provider settings.')
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 8_000_000:
                            raise ProviderError('Model response exceeded the allowed size')
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError('Expected object')
        return result
    except (httpx.HTTPError, TimeoutError) as exc:
        raise ProviderError('Model service unavailable or timed out. Saved evidence is unchanged.') from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProviderError('Model service did not return valid JSON') from exc


def answer_content(raw, kind):
    try:
        message = raw['message'] if kind == 'ollama' else raw['choices'][0]['message']
        content = message['content']
        if not isinstance(content, str):
            raise ValueError('Content must be a string')
        return content
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ProviderError('Model response has an invalid message shape; no answer was saved') from exc


class GeneratedAnswer(Strict):
    answer: str = Field(min_length=1, max_length=8000)
    citations: list[str] = Field(min_length=1, max_length=12)
    uncertainty: str = Field(max_length=2000)


async def calculation_response(config, payload, transport, allowed_ids, source_actions=None):
    """At most three allowlisted tool calls and four API requests within one deadline."""
    seen = set()
    payload['tools'] = [tool_definition(allowed_ids)]
    if source_actions is not None:
        from .source_actions import tool_definition as source_tool
        payload['tools'].append(source_tool([s.id for s in source_actions.state.sources]))
    payload['parallel_tool_calls'] = False
    payload['tool_choice'] = 'auto'
    try:
        async with asyncio.timeout(config.timeout):
            for turn in range(4):
                raw = await post(config, '/responses', payload, transport)
                output = raw.get('output')
                if raw.get('status') != 'completed':
                    raise ProviderError('OpenAI did not complete the answer. Try a shorter question. Your workspace is unchanged.')
                if not isinstance(output, list) or any(not isinstance(item, dict) for item in output):
                    raise ProviderError('OpenAI returned an invalid response shape. Your workspace is unchanged.')
                if any(item.get('type') not in ('function_call', 'message', 'reasoning') for item in output):
                    raise ProviderError('OpenAI returned an unsupported response item. Your workspace is unchanged.')
                calls = [item for item in output if item.get('type') == 'function_call']
                if not calls:
                    return raw
                if turn == 3 or len(calls) != 1:
                    raise ProviderError('Tool call limit reached. Try a simpler question. Your workspace is unchanged.')
                call = calls[0]
                identifier = call.get('call_id')
                names = {'calculate', 'manage_source'} if source_actions is not None else {'calculate'}
                if call.get('name') not in names or not isinstance(identifier, str) or not 1 <= len(identifier) <= 200 or identifier in seen:
                    raise ProviderError('OpenAI requested an unsupported tool call. Your workspace is unchanged.')
                seen.add(identifier)
                arguments = call.get('arguments')
                if not isinstance(arguments, str) or len(arguments) > (80000 if call.get('name') == 'manage_source' else 8000):
                    raise ProviderError('Tool arguments exceeded supported limits.')
                try:
                    if call.get('name') == 'manage_source':
                        result = source_actions.prepare(arguments)
                        payload['input'] = payload['input'] + output + [
                            {'type':'function_call_output', 'call_id':identifier, 'output':json.dumps(result)}]
                        continue
                    data = Calculation.model_validate_json(arguments)
                    if not set(data.citations).issubset(allowed_ids):
                        raise ProviderError('Calculation cited unavailable evidence. Try a more specific question.')
                    result = calculate(data)
                except ValueError:
                    # Do not echo untrusted arguments, validation input or provider details.
                    result = {'error':'Invalid calculation. Check numeric bounds, event amounts, operand count, division by zero and available quantities. Use only the documented schema.'}
                payload['input'] = payload['input'] + output + [
                    {'type':'function_call_output', 'call_id':identifier, 'output':json.dumps(result)}]
    except TimeoutError as error:
        raise ProviderError('Model service unavailable or timed out. Saved evidence is unchanged.') from error


async def openai_answer(config: ProviderConfig, messages: list[dict], contract: type[Strict], max_tokens: int, transport=None, allowed_citations: dict[str, list[str]] | None = None, source_actions=None):
    """Stateless, bounded Responses request; local validation remains authoritative."""
    schema = contract.model_json_schema()
    schema['required'] = list(schema['properties'])
    for prop in schema['properties'].values():
        prop.pop('default', None)
    for name, identifiers in (allowed_citations or {}).items():
        prop = schema['properties'][name]
        if identifiers:
            prop['items']['enum'] = list(dict.fromkeys(identifiers))
        else:
            prop['maxItems'] = 0
    messages = [dict(message) for message in messages]
    messages[0]['content'] += '\n'+CALCULATION_INSTRUCTIONS
    if source_actions is not None:
        from .source_actions import INSTRUCTIONS as SOURCE_INSTRUCTIONS
        messages[0]['content'] += '\n'+SOURCE_INSTRUCTIONS
    payload = {'model': config.model, 'input': messages, 'stream': False, 'store': False,
               'reasoning': {'effort': 'none'}, 'max_output_tokens': max_tokens,
               'text': {'format': {'type': 'json_schema', 'name': contract.__name__, 'strict': True, 'schema': schema}}}
    allowed_ids = {identifier for ids in (allowed_citations or {}).values() for identifier in ids}
    raw = await calculation_response(config, payload, transport, sorted(allowed_ids), source_actions)
    if raw.get('status') != 'completed':
        raise ProviderError('OpenAI did not complete the answer. Try a shorter question. Your workspace is unchanged.')
    try:
        output = raw['output']
        if not isinstance(output, list):
            raise ValueError('Expected output list')
        texts = []
        for item in output:
            if item['type'] != 'message':
                continue
            if item['role'] != 'assistant':
                raise ValueError('Expected assistant message')
            for part in item['content']:
                if part['type'] == 'refusal':
                    raise ProviderError('OpenAI declined this request. Your workspace is unchanged.')
                if part['type'] != 'output_text' or not isinstance(part['text'], str):
                    raise ValueError('Expected output text')
                texts.append(part['text'])
        if not texts:
            raise ValueError('Empty answer')
        return ''.join(texts)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ProviderError('OpenAI returned an invalid response shape. Your workspace is unchanged.') from exc


async def generate(config: ProviderConfig, question: str, evidence: list[dict], transport=None):
    if not evidence:
        raise ProviderError('No evidence available for generation')
    allowed = {row['claim']['id'] for row in evidence}
    context = [{'id': r['claim']['id'], 'quote': r['claim']['quote'], 'source': r.get('source', {})} for r in evidence]
    messages = [
        {'role':'system', 'content':EVIDENCE_POLICY + 'You draft a saved evidence answer. Answer from the supplied quotes; cite exact evidence IDs in citations. Return one JSON object with answer (string), citations (nonempty list of exact provided IDs), uncertainty (string). No em dashes.'},
        {'role':'user', 'content':json.dumps({'question':question,'evidence':context}, ensure_ascii=False)},
    ]
    if config.kind == 'openai':
        content = await openai_answer(config, messages, GeneratedAnswer, 1200, transport,
                                      allowed_citations={'citations': sorted(allowed)})
    elif config.kind == 'ollama':
        payload = {'model':config.model,'messages':messages,'stream':False,'format':'json','options':{'temperature':0,'num_predict':1200}}
        if config.model.startswith('gpt-oss'):
            payload['think'] = 'low'
        raw = await post(config, '/api/chat', payload, transport)
        content = answer_content(raw, 'ollama')
    else:
        payload = {'model':config.model,'messages':messages,'stream':False,'temperature':0,'max_tokens':1200,'response_format':{'type':'json_object'}}
        if config.model.startswith('gpt-oss'):
            payload['reasoning_effort'] = 'low'
        raw = await post(config, '/chat/completions', payload, transport)
        content = answer_content(raw, 'compatible')
    try:
        answer = GeneratedAnswer.model_validate_json(content)
    except (ValueError, TypeError) as exc:
        raise ProviderError('Model answer failed the expected JSON contract; no answer was saved') from exc
    if not set(answer.citations).issubset(allowed):
        raise ProviderError('Model cited evidence outside the retrieved set; no answer was saved')
    answer.citations = list(dict.fromkeys(answer.citations))
    answer.answer = answer.answer.replace('\u2014', '; ')
    answer.uncertainty = answer.uncertainty.replace('\u2014', '; ')
    return answer


async def embed(config: ProviderConfig, texts: list[str], transport=None):
    if config.kind == 'ollama':
        result = await post(config, '/api/embed', {'model':config.model,'input':texts,'truncate':False}, transport)
        vectors = result.get('embeddings')
    else:
        result = await post(config, '/embeddings', {'model':config.model,'input':texts}, transport)
        rows = result.get('data', [])
        if not isinstance(rows, list) or any(not isinstance(r, dict) or type(r.get('index')) is not int for r in rows) or sorted(r['index'] for r in rows) != list(range(len(texts))):
            raise ProviderError('Embedding response indices are incomplete or duplicated')
        vectors = [row.get('embedding') for row in sorted(rows, key=lambda r:r['index'])]
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise ProviderError('Embedding response count mismatch')
    size = len(vectors[0]) if vectors and isinstance(vectors[0], list) else 0
    if not 1 <= size <= 4096:
        raise ProviderError('Embedding dimension outside supported bounds')
    for vector in vectors:
        if not isinstance(vector, list) or len(vector) != size or any(type(x) not in (int, float) or not math.isfinite(x) for x in vector) or not math.isfinite(sum(x*x for x in vector)) or sum(x*x for x in vector) <= 0:
            raise ProviderError('Embedding response has invalid, zero or inconsistent vectors')
    return vectors
