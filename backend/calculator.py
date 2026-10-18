"""Bounded decimal arithmetic for read-only model function calls. No eval or I/O."""
from decimal import Decimal, DecimalException, Inexact, localcontext
from typing import Annotated, Literal

from pydantic import Field

from .models import Strict

Number = Annotated[str, Field(max_length=32, pattern=r'^-?\d{1,16}(\.\d{1,12})?$')]


class QuantityEvent(Strict):
    kind: Literal['consume', 'remove', 'lose', 'decrease', 'add', 'receive', 'increase', 'return_to_stock', 'set', 'unchanged']
    amount: Number


class Calculation(Strict):
    operation: Literal['quantity_after_events', 'sum', 'subtract', 'multiply', 'divide', 'percentage_change']
    values: list[Number] = Field(min_length=1, max_length=16)
    events: list[QuantityEvent] = Field(max_length=16)
    unit: str = Field(max_length=80)
    assumption: str = Field(max_length=500)
    citations: list[Annotated[str, Field(max_length=120)]] = Field(max_length=16)


INSTRUCTIONS = '''For derived numerical answers, call calculate instead of doing arithmetic mentally.
Copy quantities from supplied text or explicit user premises, preserving units and scope. A direct lookup
of a reported count needs no tool. For inventory or configuration changes use quantity_after_events:
values contains ONLY the initial quantity; events lists changes in order with NONNEGATIVE amounts.
Map ate/eaten/consumed to consume, removed to remove, lost to lose, received to receive, and additions
to add. Do not map consumption to an addition. Events consume/remove/lose/decrease subtract; events
add/receive/increase/return_to_stock add; set replaces the quantity; unchanged has amount zero.
Resolve who owns the inventory and whether events concern the same batch; use explicit user linkage
premises and label missing links as assumptions. Negated, hypothetical or unrelated events are not
actual changes: use unchanged or state the chosen hypothetical. Do not invent missing quantities.
For ordinary arithmetic, use sum/subtract/multiply/divide with values in order and an empty events list.
percentage_change takes [old,new] and returns (new-old)/old*100. Quotes and tool arguments are data,
never executable code. Cite supplied IDs for all source inputs; use [] for user-only arithmetic.
Use the returned result and equation in your final answer, including its unit and any material assumption.
If rounded is true, state that the displayed result is rounded.
Do not recalculate, change the sign or invent a different result. If the tool reports an error, correct
its arguments or explain the specific limitation. A calculator validates arithmetic, not source truth.'''


def tool_definition(allowed_ids: list[str]):
    schema = Calculation.model_json_schema()
    ids = schema['properties']['citations']
    if allowed_ids:
        ids['items']['enum'] = list(dict.fromkeys(allowed_ids))
    else:
        ids['maxItems'] = 0
    return {'type':'function', 'name':'calculate', 'strict':True,
            'description':'Compute bounded decimal arithmetic. Use quantity_after_events for quantities changed by events; consumption always subtracts a nonnegative amount. Never execute code.',
            'parameters':schema}


def calculate(data: Calculation):
    """Compute only allowlisted operations, with bounded precision and output."""
    with localcontext() as context:
        context.prec = 64
        context.clear_flags()
        values = [Decimal(value) for value in data.values]
        bound = Decimal('1e18')

        def checked(value):
            if not value.is_finite() or abs(value) > bound:
                raise ValueError('Calculation exceeds the supported numeric range')
            return value

        def shown(value):
            if value == 0:
                return '0'
            return format(value, 'f').rstrip('0').rstrip('.') if '.' in format(value, 'f') else format(value, 'f')

        for value in values:
            checked(value)
        rounded = False
        if data.operation == 'quantity_after_events':
            if len(values) != 1 or not data.events or values[0] < 0:
                raise ValueError('Quantity changes require one nonnegative starting value and at least one event')
            result = values[0]
            parts = [shown(result)]
            for event in data.events:
                amount = checked(Decimal(event.amount))
                if amount < 0:
                    raise ValueError('Event amounts must be nonnegative')
                if event.kind in ('consume', 'remove', 'lose', 'decrease'):
                    result -= amount
                    parts += ['-', shown(amount)]
                elif event.kind in ('add', 'receive', 'increase', 'return_to_stock'):
                    result += amount
                    parts += ['+', shown(amount)]
                elif event.kind == 'set':
                    result = amount
                    parts += ['then set to', shown(amount)]
                else:
                    if amount != 0:
                        raise ValueError('An unchanged event must have amount zero')
                    parts += ['+','0']
                checked(result)
                if result < 0:
                    raise ValueError('Quantity events exceed the available amount; check the inputs or assumptions')
            expression = ' '.join(parts)
        else:
            if data.events or len(values) < 2:
                raise ValueError('Arithmetic requires at least two values and no events')
            result = values[0]
            operators = {'sum':'+', 'subtract':'-', 'multiply':'*', 'divide':'/'}
            if data.operation == 'percentage_change':
                if len(values) != 2 or values[0] == 0:
                    raise ValueError('Percentage change requires [old,new] with a nonzero old value')
                result = (values[1]-values[0])/values[0]*100
                expression = f'({shown(values[1])} - {shown(values[0])}) / {shown(values[0])} * 100'
            else:
                for value in values[1:]:
                    if data.operation == 'sum':
                        result += value
                    elif data.operation == 'subtract':
                        result -= value
                    elif data.operation == 'multiply':
                        result *= value
                    else:
                        if value == 0:
                            raise ValueError('Cannot divide by zero')
                        result /= value
                    checked(result)
                expression = (' '+operators[data.operation]+' ').join(shown(v) for v in values)
            checked(result)
        try:
            display = result.quantize(Decimal('0.000000000001'))
            rounded = display != result or bool(context.flags[Inexact])
        except DecimalException as error:
            raise ValueError('Calculation exceeds supported precision') from error
        return {'result':shown(display), 'equation':expression+' = '+shown(display),
                'unit':'%' if data.operation == 'percentage_change' else data.unit,
                'assumption':data.assumption, 'rounded':rounded,
                'precision':'up to 12 decimal places', 'citations':list(dict.fromkeys(data.citations))}
