# Read-only calculator integration

Final result: **98/98 model tasks passed**, covering all 49 scenarios twice, with 142 actual API requests. The five-case tool smoke run passed, as did two additional user-only/saved-answer integration tasks. All 104 Python tests, nine frontend tests, typecheck, formatting, build, synthetic NLP evaluation and diff checks passed. Browser testing was skipped. Three invalid calculator requests were safely rejected during the full run; the model recovered and completed those tasks. These errors remain recorded in `calculator-results.json`.

## Behavior

OpenAI Model chat and saved model answers now expose a strict `calculate` function. Luna selects structured inputs, Atlas validates and computes them with Python Decimal, and the function result is returned through `function_call_output` for the final cited answer. The current question, source context and existing citation/conflict/revision checks remain in place. No arbitrary code, shell, file or network operation is available through the calculator.

`backend/calculator.py` defines decimal sum, subtraction, multiplication, division, percentage change and an ordered quantity-event ledger. Consumed, removed, lost and decreased amounts are subtracted; added, received and returned-to-stock amounts are added. Event amounts must be nonnegative. Negated events use an unchanged zero event. Set events replace the current quantity. Impossible negative inventory, zero division, unsupported numeric representations and out-of-range values are rejected. Results use at most 12 fractional decimal places and explicitly report rounding.

`backend/providers.py` advertises the function to the official Responses API, validates names and arguments, restricts citation IDs to the supplied context, executes only the local calculator and returns matching call results. Model output items accompany the results in subsequent requests, including any reasoning items. `store=false` is retained, with no previous-response reference or persistent model conversation. The entire exchange has one provider deadline, at most three calculator calls and four model requests. Unknown functions and malformed protocol data are rejected; invalid arithmetic returns a bounded error rather than executing an expression or exposing validation input.

The explicit Ollama/compatible adapters are unchanged and do not expose this tool.

## Validation

- `tests/test_calculator.py` covers semantic event signs, ordered events, negation, exact decimals, division/rounding, invalid amounts, excessive inputs, code-shaped strings, fabricated citations, unsupported functions, tool result exchange, retry limits, overall deadlines, read-only state and saved-answer generation.
- The complete Python suite has 104 tests. Frontend typecheck, formatting, build, nine frontend tests and the existing synthetic NLP evaluation are also run.
- `assistant-eval-calculation-smoke.json` contains five real API tasks with actual backend tool results: consuming 3 from 15 yields 12; receiving 3 yields 18; not eating leaves 15; ordered events yield 14; decimal subtraction yields 0.2. All five passed.
- `calculator-integration.json` records actual user-only rounded division and saved-answer generation using the calculator. Both passed, with two real tool calls and four model requests.
- `assistant-eval-calculation-final.json` is the complete 49-case regression suite, repeated twice, including all prior 44 cases. New calculation cases require the expected backend tool result as well as the expected answer and citations. Tool rounds may add model requests, so model-task counts and API-request counts are distinct.
- `calculator-results.json` summarizes the completed run and its actual counts.

Browser testing was explicitly skipped at the user's request. No browser was opened or test server launched for this change. All real API inputs were original synthetic text; saved user workspaces were not accessed or modified.

## Limits

A calculator makes arithmetic deterministic for validated inputs. The model still interprets text, selects quantities, units, premises and event types, and composes the final answer. Incorrect interpretation remains possible. Strict schemas and citations do not establish truth. These finite synthetic evaluations are regression evidence, not a guarantee of general mathematical or semantic accuracy.

The function-call flow follows [official OpenAI guidance](https://developers.openai.com/api/docs/guides/function-calling), with GPT-6 Luna capabilities checked against its [model documentation](https://developers.openai.com/api/docs/models/gpt-6-luna).

## Reproduce

Configure the key privately in `.env`, then run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/assistant_eval.py --live --suite calculation --label my-calculator-smoke
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/assistant_eval.py --live --suite all --repeats 2 --label my-calculator-regression
```

These are opt-in billable API runs. The full suite has 98 model tasks and can make up to four requests per task. Reports include actual request counts, token usage and estimated text-token costs.
