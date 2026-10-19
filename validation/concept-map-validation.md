# Independent selected-source concept map

Historical record: this display was superseded by the relationship-map MVP. See [current relationship map validation](relationship-map-validation.md). The old keyword renderer and mining code have been removed; these results describe the earlier implementation.

The current Graph visualization uses `frontend/concept-map.ts`, a separate browser-side function. Its inputs are the current question and the full saved bodies of the source IDs already selected for Ask Atlas. It does not inspect or reuse retrieval paths, backend connection metadata, GraphRAG rules, embeddings, model adapters or the model prompt. No additional HTTP/model calls or database writes occur.

## Display behavior

- Mine words and adjacent bigrams, with simple English word-form grouping. Mask URLs without moving source offsets, remove common boilerplate, repeated-word phrases and basic verb fragments, and shortlist up to 320 candidates per source.
- Favor explicit question matches, terms shared across sources and repeated technical/phrase signals. Cap repetition effects and penalize redundant labels. This is heuristic text scoring, not semantic inference or calibrated confidence.
- Render at most eight concepts and 24 source/concept links across at most eight selected sources. Prefer stronger candidates; if fewer than five distinct strong concepts remain after deduplication, fill from actual lighter keywords. Do not manufacture keywords to meet a fixed count.
- Show lighter associations with dashed lines. Each concept expands to source text, with exact Unicode quote positions and source hashes retained internally. The map can use text outside the excerpts provided to the LLM; the original supplied passages remain separately inspectable.
- Keep each source node once, keyboard source navigation, existing page-navigation retention, stale workspace/revision guards and Show saved analysis. Unselected source bodies do not enter the map.

## Actual validation

- All 23 frontend checks passed, including independent mining, dense/sparse caps, shared concepts, question sensitivity, word-form deduplication, late keywords after stopword-heavy text, URL-only/empty cases, phrase-fragment filtering, exact Unicode/hash support and deterministic outputs without mutating source data.
- Static React rendering verifies escaped source text, keyboard node controls, empty states and that removing GraphRAG connection metadata does not change the map. Adding an unselected source also leaves the map unchanged.
- Typecheck, formatting, self-contained hosted/live builds and `git diff --check` passed.
- SHA-256 comparisons against the start of this change confirm these files are byte-identical: `backend/retrieval_graph.py`, `backend/source_context.py`, `backend/assistant.py`, `backend/app.py`, `backend/providers.py` and `frontend/retrieval.ts`. Existing retrieval logic, adapters, prompt context and metadata validation were not edited.
- No browser test, paid model call or user workspace access occurred. The Python suite was not rerun for this frontend-only change; its prior 388-test result remains historical validation.

The map deliberately shows approximate textual concepts rather than GraphRAG internals. English stemming and phrase rules can still produce imperfect labels or miss semantic synonyms. Dashed links mean lighter keyword associations, not verified technical dependencies. Rendering was checked statically, not by visual browser inspection.
