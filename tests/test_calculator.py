"""Calculator arithmetic, semantic event signs and OpenAI function-call boundaries."""
import asyncio
import json

import httpx
import pytest

from backend.assistant import AssistantRequest, assist
from backend.calculator import Calculation, calculate
from backend.models import Source, SourceInput, Workspace
from backend.providers import ProviderConfig, ProviderError, generate


def arguments(operation='quantity_after_events', values=None, events=None, citations=None):
    return {'operation':operation, 'values':values or ['15'],
            'events':events if events is not None else [{'kind':'consume','amount':'3'}],
            'unit':'bagels', 'assumption':'Same batch, no other changes', 'citations':citations or []}


@pytest.mark.parametrize('kind, expected', [('consume','12'),('remove','12'),('lose','12'),('decrease','12'),
                                           ('add','18'),('receive','18'),('increase','18'),('return_to_stock','18'),('set','3')])
def test_event_direction_is_computed_by_backend(kind, expected):
    result = calculate(Calculation(**arguments(events=[{'kind':kind,'amount':'3'}])))
    assert result['result'] == expected and not result['rounded']


def test_negation_and_ordered_events():
    assert calculate(Calculation(**arguments(events=[{'kind':'unchanged','amount':'0'}])))['result'] == '15'
    events = [{'kind':'consume','amount':'3'},{'kind':'receive','amount':'4'},{'kind':'consume','amount':'2'}]
    assert calculate(Calculation(**arguments(events=events)))['result'] == '14'


@pytest.mark.parametrize('operation, values, result', [('sum',['0.1','0.2'],'0.3'),('subtract',['15','3'],'12'),
    ('multiply',['2.5','4'],'10'),('divide',['15','3'],'5'),('percentage_change',['4','8'],'100')])
def test_decimal_arithmetic(operation, values, result):
    output = calculate(Calculation(**arguments(operation, values, [])))
    assert output['result'] == result and output['equation'].endswith('= '+result)


def test_rounding_is_explicit():
    result = calculate(Calculation(**arguments('divide',['1','3'],[])))
    assert result['result'] == '0.333333333333' and result['rounded']


def test_rounding_does_not_inherit_unrelated_decimal_flags():
    from decimal import Inexact, localcontext
    with localcontext() as outer:
        outer.flags[Inexact] = True
        assert not calculate(Calculation(**arguments()))['rounded']


@pytest.mark.parametrize('data', [arguments(events=[{'kind':'consume','amount':'-3'}]),
    arguments(events=[{'kind':'consume','amount':'16'}]), arguments(events=[{'kind':'unchanged','amount':'3'}]),
    arguments('divide',['1','0'],[]), arguments('percentage_change',['0','1'],[]),
    arguments('sum',['1'],[]), arguments('multiply',['9999999999999999','9999999999999999'],[]),
    arguments(values=['NaN']), arguments(values=['__import__("os").system("bad")']),
    arguments(values=['1e999999']), arguments(events=[{'kind':'execute','amount':'1'}]),
    arguments(events=[{'kind':'consume','amount':'1'}]*17)])
def test_invalid_or_unsafe_inputs_are_rejected(data):
    with pytest.raises(ValueError):
        calculate(Calculation(**data))


def call(data, identifier='call_test', name='calculate'):
    return {'status':'completed','output':[{'type':'function_call','id':'fc_test','call_id':identifier,
                                          'name':name,'arguments':json.dumps(data)}]}


def final(citations=None, source_citations=None):
    return {'status':'completed','output':[{'type':'message','role':'assistant','content':[
        {'type':'output_text','text':json.dumps({'answer':'12 bagels remain: 15 - 3 = 12.',
           'citations':citations or [],'uncertainty':'','source_citations':source_citations or []})}]}]}


@pytest.mark.asyncio
async def test_real_adapter_executes_function_and_returns_result_without_mutating_workspace():
    source = Source.create(SourceInput(title='Synthetic count',version='1',text='There are 15 bagels. Bob ate 3 of them.'))
    state = Workspace(sources=[source])
    before = state.model_dump()
    requests = []
    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body['store'] is False and body['parallel_tool_calls'] is False
        assert 'previous_response_id' not in body
        if len(requests) == 1:
            tool = body['tools'][0]
            assert tool['name'] == 'calculate' and tool['strict'] is True
            context = json.loads(body['input'][1]['content'])['context']
            identifier = context['source_passages'][0]['id']
            assert tool['parameters']['properties']['citations']['items']['enum'] == [identifier]
            return httpx.Response(200,json=call(arguments(citations=[identifier])))
        output = body['input'][-1]
        assert output['type'] == 'function_call_output' and output['call_id'] == 'call_test'
        result = json.loads(output['output'])
        assert result['result'] == '12' and result['equation'] == '15 - 3 = 12'
        return httpx.Response(200,json=final(source_citations=result['citations']))
    result = await assist(ProviderConfig(key='synthetic'),state,AssistantRequest(revision=0,message='How many remain?'),httpx.MockTransport(handle))
    assert result.answer.startswith('12') and len(requests) == 2 and state.model_dump() == before


@pytest.mark.asyncio
async def test_invalid_tool_arguments_are_returned_safely_for_correction():
    turns = []
    def handle(request):
        body = json.loads(request.content)
        turns.append(body)
        if len(turns) == 1:
            return httpx.Response(200,json=call(arguments(values=['SENSITIVE_UNTRUSTED_DATA'])))
        error = json.loads(body['input'][-1]['output'])
        assert 'error' in error and 'SENSITIVE_UNTRUSTED_DATA' not in json.dumps(error)
        return httpx.Response(200,json=final())
    await assist(ProviderConfig(key='synthetic'),Workspace(),AssistantRequest(revision=0,message='Calculate'),httpx.MockTransport(handle))
    assert len(turns) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', [call(arguments(),name='run_shell'),call(arguments(citations=['missing'])),
                                 call(arguments(),identifier='')])
async def test_unsupported_calls_and_fabricated_citations_are_rejected(bad):
    with pytest.raises(ProviderError):
        await assist(ProviderConfig(key='synthetic'),Workspace(),AssistantRequest(revision=0,message='Calculate'),
                     httpx.MockTransport(lambda r:httpx.Response(200,json=bad)))


@pytest.mark.asyncio
async def test_tool_loop_has_a_hard_limit():
    count = 0
    def handle(request):
        nonlocal count
        count += 1
        return httpx.Response(200,json=call(arguments(),identifier='call_'+str(count)))
    with pytest.raises(ProviderError,match='limit'):
        await assist(ProviderConfig(key='synthetic'),Workspace(),AssistantRequest(revision=0,message='Calculate'),httpx.MockTransport(handle))
    assert count == 4


@pytest.mark.asyncio
async def test_whole_tool_exchange_has_one_timeout():
    async def handle(request):
        await asyncio.sleep(.03)
        return httpx.Response(200,json=call(arguments()))
    with pytest.raises(ProviderError,match='timed out'):
        await assist(ProviderConfig(key='synthetic',timeout=.01),Workspace(),AssistantRequest(revision=0,message='Calculate'),httpx.MockTransport(handle))


@pytest.mark.asyncio
async def test_saved_answer_generation_uses_the_same_tool_loop():
    evidence = [{'claim':{'id':'c-count','quote':'There are 15 bagels. Bob ate 3 of them.'}}]
    count = 0
    def handle(request):
        nonlocal count
        count += 1
        body = json.loads(request.content)
        if count == 1:
            return httpx.Response(200,json=call(arguments(citations=['c-count'])))
        assert json.loads(body['input'][-1]['output'])['result'] == '12'
        answer = final(citations=['c-count'])
        text = json.loads(answer['output'][0]['content'][0]['text'])
        text.pop('source_citations')
        answer['output'][0]['content'][0]['text'] = json.dumps(text)
        return httpx.Response(200,json=answer)
    answer = await generate(ProviderConfig(key='synthetic'),'How many remain?',evidence,httpx.MockTransport(handle))
    assert answer.answer.startswith('12') and answer.citations == ['c-count'] and count == 2
