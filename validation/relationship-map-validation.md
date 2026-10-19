# Independent documentation relationship MVP

Validated 2026-10-18. No browser tests, model calls or user workspace writes were performed.

## Required cleanup checkpoint

Before implementing the new map, removed the previous `frontend/concept-map.ts` and `frontend/RetrievalGraph.tsx`, the legacy `GraphView` renderer, their exclusive graph styles and two obsolete display tests. The Graph page temporarily rendered a placeholder. At this checkpoint:

- All 402 Python tests passed, with the existing Starlette/httpx deprecation warning.
- All 21 remaining frontend checks passed.
- Typecheck, format check, self-contained builds and git diff checks passed.

Only after that checkpoint passed was the new relationship extractor/view created. Saved graph contracts and backend retrieval were retained because they remain active, including graph-assisted source selection, snapshot validation and optional Questions retrieval.

## MVP checks

Final frontend checks: 24 passed. Typecheck, formatting, builds, synthetic evaluation and git diff checks passed. The synthetic evaluation retains macro F1 1.0, graph recall 1.0 on four prepared queries and quote integrity; these tiny fixtures do not establish production accuracy. Python was not rerun after the frontend-only MVP because all protected backend files remained unchanged from the passing cleanup checkpoint.

Three new frontend checks cover:

- Actual bundled README inputs: backend/frontend question identifies Flask, Jinja, Werkzeug, Quart and MarkupSafe, excludes Click, and yields the historical Flask wrapper links plus corroborated template-rendering and HTML-escaping links. Command-line questions focus on Click without inventing a cross-project link. Unrelated astronomy questions produce no map. Results are deterministic and do not mutate sources.
- Rule boundaries: no relation from mere co-mention, fenced code, HTML attributes, URL definitions, simple negation, alternatives or ambiguous target project identities. Unicode evidence offsets and source fingerprints match the original text. A dense 30-source fixture remains within six projects/eight links.
- Static SVG/React: only existing selected source IDs contribute to a question map; modifying graph_paths or connections metadata leaves output identical. Keyboard controls, escaped question/evidence text, loading/error/empty states, no automatic callbacks and saved-view guidance are checked. Node rectangles do not overlap for one through six projects; curved connection badges avoid the central question panel.

An initial targeted run caught a lexical false positive: “line” in a command-line query matched Jinja's debugging prose and introduced a Flask/Jinja link. Removing that generic term and requiring two lexical query matches when no single-term query is present corrected the issue without weakening the CLI expectation. A help-copy assertion was updated to the replacement view's actual title. The final full frontend run passed.

The hosted browser test now expects the replacement relationship-map region and heading instead of the removed legacy selector. That browser suite was not executed locally, in accordance with the user's no-browser-testing preference. Layout bounds and static rendering are not a substitute for visual browser validation.

## Isolation and limits

SHA-256 comparison against the start of the task verified these ten files remain byte-for-byte unchanged: backend/retrieval_graph.py, backend/source_context.py, backend/assistant.py, backend/app.py, backend/nlp.py, backend/providers.py, frontend/retrieval.ts, frontend/Assistant.tsx, frontend/assistant-stream.ts and frontend/question-graph.ts.

The new extractor imports only the Source type and has no network, model or database access. It uses six English capability patterns, a handful of explicit relationship constructions and document-frequency-weighted lexical ranking; it is not general semantic relation extraction or a new embedding model. Shared capabilities are symmetric and do not prove integration; explicit statements remain claims of the cited documentation, with historical wording preserved. One relation per source pair is retained. Sparse or ambiguous text can yield roles without edges or an empty map. Project identities depend on recognizable source titles. Circular layout is static and bounded, rather than a general force simulation. Existing request/revision/user/workspace guards and navigation retention remain in the untouched question-state bridge.


## Routing and Python follow-up

The original six capability rules omitted routing and Python. Question filler also prevented the lexical fallback from matching a single substantive term. Added routing/Python capability patterns, recognized positive language tags and route decorators in inert Python/pycon/py fenced examples, and excluded question filler. “Without running a server” no longer negates a documented capability. Negative claims such as “not Python” remain excluded from focused maps, including their lexical matches. Python usage is not a claim that an entire project is written in Python.

The new bundled-data checks require all six projects for Python questions and exactly Flask, Quart and Werkzeug for routing questions, with valid exact Unicode evidence spans and hashes. Synthetic checks cover pycon examples, route decorators, negation, comments, HTML attributes and non-Python code. Routing/Python maps require direct capability support for each node; Python shared links form a sparse forest instead of a clique. Existing frontend regressions remain required. These changes are display-only and use no model/browser/network/database calls.

Follow-up validation passed all 25 frontend checks, typecheck, formatting, both self-contained builds and git diff checks. SHA-256 comparison again confirmed all ten protected Ask Atlas files unchanged. No Python rerun was needed for these browser-side-only changes. No browser tests or model calls were performed.


## General mention-query follow-up

Added a separate bounded literal mention matcher rather than protocol-specific patches. The bundled HTTPS query matches six sources with five sparse text-mention links, including URL evidence. The security query is verified to have no literal hits in the bundled data and instead shows only the corroborated Jinja/MarkupSafe escaping capabilities with an explicit fallback notice. Quoted security requests remain empty literal searches. Generic titles are accepted without requiring project-name inference.

New regression coverage exercises arbitrary retry_budget mentions, case/word boundaries, HTTPS versus HTTP, and/or scope, unsupported negative filters, escaped regex metacharacters, quoted Unicode terms, exact quote positions/hashes and the original routing/Python/backend/frontend/CLI cases. Static UI checks cover the new mention heading, dotted link class, capability/dependency disclaimer and the related-security notice. An initial check caught an unrelated Flask wrapper link being pulled into the security fallback; requiring capability support on both ends corrected it without weakening the expected Jinja/MarkupSafe result. No browser/model/network calls were made for this follow-up.
