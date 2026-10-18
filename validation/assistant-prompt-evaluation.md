# Atlas GPT-6 Luna prompt evaluation

## Calculator integration update

The current suite now has 49 cases. Running it twice performs 98 model tasks, with additional API requests for calculator rounds. See `calculator-validation.md` and `calculator-results.json` for the function-calling integration and current results. The clarification and earlier prompt-only sections below retain their historical counts. Browser testing for the calculator change was explicitly skipped at the user's request.

## Clarification follow-up update

The current acceptance suite has **44 cases, tested twice: 88/88 real API responses passed**. It retains all 38 original cases and adds six cases for an unlinked quantity/event, a same-batch clarification after an assistant refusal, an explicit event assumption, a premise from an earlier user turn, a withdrawn premise and a configuration-delta analogy. The production prompt now explicitly accepts user-supplied linkages as premises for conditional calculations, distinguishes changes from replacement snapshots and treats earlier assistant refusals as nonbinding. Missing links are still flagged or made conditional rather than presented as established facts.

The six simplified baseline cases already passed before this adjustment; the user's exact refusal was not reproduced. Both baseline and final outputs are retained. The change makes the intended behavior explicit rather than claiming to have reproduced that particular exchange.

The supported browser conversation returned a conditional 10 for the initial 15-bagel and 5-eaten sources, then directly returned 10 after the user confirmed the same batch and no other changes. Both source citations rendered. The separate real chat/saved-answer smoke probe passed. All 67 Python tests, nine frontend checks, typecheck, format, build, synthetic NLP evaluation and diff checks passed. Saved user workspaces were untouched.

See `assistant-clarification-results.json`, `assistant-eval-clarification-baseline.json`, `assistant-eval-clarification-final.json` and `assistant-clarification-browser.json`. The 94 metered baseline/regression requests cost an estimated $0.025786, excluding four small browser/smoke requests. These are token-rate estimates, not billing statements. Current full-suite reproduction makes 88 requests, and `--suite clarification` runs just the six new cases.

The sections below retain the original 38-case evaluation history.

## Objective and acceptance criteria

Answer supported user questions directly, follow explicit source/version selection and hypothetical assumptions, label best guesses, calculate independent quantities, and retain citation, conflict, revision and trust boundaries. A refusal is appropriate for unavailable facts, not merely because the user requested an assumption.

The final acceptance suite contains 38 original synthetic scenarios, each run twice through the production `assist` adapter and official Responses API with `gpt-6-luna`, reasoning `none`, strict structured outputs and `store=false`. Acceptance requires every case in both repetitions to pass answer-content and citation checks, plus human inspection of recorded answers. Eight holdout scenarios use different subjects, quantities, code and adversarial text. The separate production smoke probe covers chat and saved-answer generation. Browser checks use the Intel launcher and a temporary workspace, without modifying saved user work.

Final result: **76/76 real API responses passed**, covering all 38 cases twice. All recorded final answers were inspected alongside their expected outcomes. The real two-request chat/saved-answer probe and two browser requests also passed. All 66 Python tests, nine frontend tests, typecheck, formatting, build, the synthetic NLP evaluation and diff checks passed.

Across retained prompt-evaluation attempts, 139 metered requests have a conservative estimated text-token cost of $0.035127. Four additional real requests came from the browser and integration probe and were not token-metered by this harness. This is an estimate, not an API billing statement.

## Research

- [GPT-6 family prompting guidance](https://developers.openai.com/api/docs/guides/latest-model#prompting-best-practices): make the desired behavior and instruction precedence clear, encourage useful completion, and validate on the chosen workload. This family guide discusses behavior observed primarily with Astra; it is a starting point, not proof about Luna.
- [GPT-6 Luna model documentation](https://developers.openai.com/api/docs/models/gpt-6-luna): verifies the exact model, Responses support, structured outputs and supported `none` reasoning. Standard text rates used for estimates are $0.10/M input and $0.50/M output tokens. Input cache discounts are ignored in estimates.
- [Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices): define task-specific outcomes, include normal, edge and adversarial cases, compare iterations and combine automated grading with human judgment.

## Implementation

`backend/prompts.py` owns the shared evidence policy. `backend/assistant.py` adds application workflow and source-context instructions; `backend/providers.py` uses the same policy for saved model answers. Explicit source/version choices produce conditional conclusions, without requiring proof that the preferred source is objectively correct. Same-version known conflicts still require both supporting citation groups. Partial context and genuinely missing facts remain visible.

Real testing exposed incorrect copying of long citation IDs even when the answer was otherwise reasonable. OpenAI output schemas now enumerate the currently supplied citation IDs, or restrict an unavailable citation array to empty. Server membership checks, exact quote metadata, conflict checks and browser validation remain in place. There is no fuzzy citation repair or acceptance of invented IDs.

## Retained iteration evidence

- `assistant-eval-baseline.json`: original prompt, 5/6 heuristic passes. It answered the highest-version and best-guess cases correctly in this run; the user's exact refusal was not reproduced. One request failed citation validation.
- `assistant-eval-candidate-1.json`: revised prompt before citation enums, 9/12 passes, with three citation validation failures.
- `assistant-eval-citation-diagnostic.json`: a focused successful sum response, retained rather than used to hide earlier failures.
- `assistant-eval-candidate-2.json`: constrained citations eliminated citation failures in 12 responses. Two automatic failures were grader false negatives: the answers used "differ" rather than the original accepted synonyms.
- `assistant-eval-extended-1.json`: 24 broader responses, with three grader false negatives: a valid result in the second short sentence, case-sensitive UI-label checks, and a partial-coverage answer using "excerpts" rather than the initial accepted vocabulary. These answers were inspected. The grader was corrected and all earlier reports retained unchanged.
- `assistant-eval-holdout-1.json`: 8/8 held-out cases passed without a prompt change.
- `assistant-eval-final.json`: fresh whole-suite acceptance results using the corrected grader. This is the authoritative repeatability result; consult its result, counts, usage and full answers.
- `openai-results.json`: real chat and saved-answer integration probe.
- `assistant-browser-results.json`: actual browser behavior on the disposable two-source fixture.

## Scope and limits

The suite covers highest/lowest/specific/semantic/date/stable version selection, incomparable version labels, separate totals versus snapshots, differences and percentage changes, hypotheticals, follow-ups, stale chat and findings, zero and Unicode counts, selected-source bias, summaries without analysis, known conflicts, conditional conflict conclusions, general explanations, missing documents and facts, disk-access limits, partial retrieval, code reading and embedded prompt injection.

These are finite synthetic tests with heuristic outcome checks and manual review. They are not a general accuracy benchmark, an exhaustive injection defense, or a guarantee for arbitrary documents. No prompt can establish universal correctness or objectively be called the best prompt. Continue to retain human review and add real failure cases to future evaluations.

## Reproduce

With the credential configured privately in `.env`:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/assistant_eval.py --live --suite all --repeats 2 --label my-run
```

The current suite has 98 billable model tasks, with up to four API requests per task for calculator rounds. `--suite core`, `extended`, `holdout`, `clarification`, or `calculation` and repeated `--case NAME` select smaller runs. Reports contain synthetic text and model answers only. Never use private user workspace contents as fixtures without specific authorization.
