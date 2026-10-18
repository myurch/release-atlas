# Documentation NLP pipeline validation

Implemented on 2026-10-17. Analyze sources now produces structured documentation passages and inspectable NLP outputs rather than one card per non-heading line. The internal `claims` identifier remains for compatible persistence, citations, review routes and graph connections.

## Implementation

- `backend/document_parser.py`: bounded structural Markdown/reStructuredText parser. It preserves heading paths, wrapped prose, continued list items, fenced/indented/directive code and tables. Prose over 1,800 code points is split near sentence/space boundaries. Code and tables remain intact within the source limit. Headings and link definitions are not represented as claims. This is a purpose-built heuristic parser, not a complete CommonMark or Docutils implementation.
- `backend/document_classifier.py`: TF-IDF unigram/bigram features, normalized 48-dimensional truncated-SVD/LSA embeddings and logistic regression over nine documentation purposes. It uses 72 original synthetic training examples, with weak/unknown inputs assigned other. Return the top three competing scores and up to two nearby training examples. Scores are uncalibrated. Similar examples show vector proximity, not causal explanations. No pretrained neural embedding model or generation provider is used.
- `backend/nlp.py`: orchestrates stages, preserves separate release-label/conflict rules and graph/retrieval behavior, and runs NMF over varied prose with URLs removed and code excluded. Topic counts adapt to usable prose, up to four; tiny/repetitive corpora produce no topics. Terms retain relative weights, representatives and source coverage. Code/unassigned passages have topic 0 and zero topic strength. Topic membership is a normalized factor weight, not a probability.
- `backend/technical_entities.py`: typed syntax candidates for API calls/imported symbols/decorators, configuration keys, commands, HTTP endpoints, imported packages, protocols/formats and other identifiers. Retain original spelling, exact Unicode spans, normalized matching keys and rule names. Up to 60 typed mentions and 30 graph identifiers per passage. Document code is never executed.
- Optional `Claim.document`, `Analysis.pipeline` and extended topic fields preserve legacy snapshot loading. Backend and frontend validate exact mention spans and topic representatives. Exact passage identities retain existing reviews; changed grouping can create new identities. No migrations or automatic reanalysis modify saved user workspaces.
- `frontend/PipelineExplorer.tsx`: four numbered stages, document map, purpose distribution, weighted topics/representatives, searchable typed inventory, classification/mention inspection and benchmark limits. `frontend/pipeline.ts` combines source, section, purpose, entity and topic filters. A topic selection uses membership, correcting the previous first-keyword search behavior. Main passage cards retain source/version, exact quotes and human review.
- Overview highlights the NLP pipeline before review counts. File/hosted/tutorial modes inspect prepared outputs, with no new live API/model calls. Existing origin/session/revision/input guards and assistant capabilities remain unchanged.

## Reference inspection

Read the user-provided public [myurch/werkzeug repository](https://github.com/myurch/werkzeug/tree/8393ee88aaacf7bcd3a0b1d604511f70c222df25), commit `8393ee88aaacf7bcd3a0b1d604511f70c222df25`, through the bounded unauthenticated README fetcher. Its reStructuredText layout drove support for underlined headings, wrapped bullet continuations and `code-block` directives.

The exact fetched text was held in a temporary file for inspection, not shipped as a fixture or saved to a workspace. SHA-256: `4781ca3cfaac44845bec454a6d9491b675aac596375ac337381283623f0583fd`.

The local pipeline produced:

- 22 passages, 316 regex-counted words, four section paths and two intact code blocks.
- Installation, example, API-reference, overview and resources purpose labels. Manual inspection confirmed the pip command as installation and the complete application code block as an example.
- Three prose topics, with terms about WSGI applications, request objects/files/cookies, and request testing. These are learned patterns, not manually assigned semantic titles.
- Twelve unique typed entities, with 20 mentions. All passage quotes and entity mentions reproduce exact Unicode source spans.

This is an integration/example inspection, not a labeled real-world accuracy benchmark. Metadata and topic terms, without README text, are recorded in `documentation-evaluation.json`.

## Evaluation

`data/document-training.json` contains 72 original synthetic examples. `data/document-evaluation.json` contains 27 separate synthetic examples across nine purposes. There is no identical text overlap, but author and domain are shared; this is not repository-held-out evaluation.

- Purpose macro-F1: **0.8800**.
- Fixed keyword baseline macro-F1: **0.8457**.
- One security example abstained to other: the public interactive-console warning. This failure is retained in the report. Macro-F1 includes the predicted other class with no positive evaluation examples; its contribution is zero.
- Per-label precision/recall/F1, model/evaluation hashes and every predicted/expected label are in `documentation-evaluation.json`.
- These metrics are recorded with an analysis and shown under Methods and limits. They do not measure any user's current documentation or establish production accuracy.
- The separate preexisting release-label evaluation still passes with macro-F1 1.0, equal to its keyword baseline, graph recall at 6 of 1.0 on four synthetic queries, and exact quote integrity.

Reproduce the purpose evaluation with `.venv/bin/python tools/evaluate_documentation.py`. An optional `--reference-file /path/to/permitted/README` also inspects a local reference without network/model calls, saved source text or workspace writes.

## Automated checks

- **314 Python tests passed**, including 19 new documentation-pipeline cases. Checks cover Markdown/RST structures, Unicode/CRLF spans, code/table integrity, purpose predictions/abstention, typed extraction, sparse topic fallback, representative membership, malformed imported metadata, legacy snapshots, review retention, SQLite round-trip, retrieval and actual ASGI analysis/export/revision/origin behavior on isolated databases.
- **17 frontend checks passed**, including combined filters, true topic membership independent of keyword text, inventory grouping, Unicode mention offsets, malformed metadata rejection, legacy snapshots and static React rendering of all four stage controls and method details. Source metadata is escaped. No interaction callback fires while rendering.
- TypeScript, formatting, production build, both evaluations and `git diff --check` passed.
- Two old line-based assumptions were updated intentionally: topic count is adaptive instead of always four, and the passage limit counts structural blocks instead of wrapped lines. An old Unicode fixture was updated to carry matching new entity metadata and to discard unrelated copied topic representatives.

No browser testing was performed, as requested. Static server rendering does not verify interactive layout, scrolling, keyboard interaction or visual appearance. The existing hosted browser suite was not run here; Docker, Safari and Firefox remain unverified. No paid model API calls, secret reads or writes to saved user workspaces were performed. Existing unrelated working-tree changes were preserved.
