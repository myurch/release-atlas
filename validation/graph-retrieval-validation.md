# Ask Atlas graph expansion validation

## Behavior

The existing lexical, embedding, entity, terminology, NMF and purpose ranking remains the first stage. `backend/retrieval_graph.py` adds a cached NetworkX graph alongside that index, independent of saved findings and the separate Graph page. No database migration, generation tool, network fetch or additional dependency is introduced.

Graph edges connect an exact technology reference to a uniquely identified source, or passages sharing a rare exact technical identifier. Project identities come from distinctive leading source names with documentation suffixes or owner/repository README titles. Ambiguous identities, generic names, protocols, command strings and identifiers shared by more than three sources are excluded. Ordinary shared topic words do not create graph edges. Explicit references are labeled references, including negative statements; they are not asserted integration/dependency facts.

Traversal starts at up to three hybrid candidates and follows one entity bridge, adding at most two previously unrepresented sources after the first four hybrid candidates. References need question relevance or corroborating seed context; shared identifiers require both. Existing source/version restrictions, no-match behavior, overview coverage, overlap deduplication, atomic conflict packing, exact quotes and eight-passage/16,000-character budgets remain authoritative. An expansion is skipped if its seed was not packed. No recursive expansion occurs.

Server-created graph paths contain selected passage IDs, a bounded connecting name and the relationship type. The existing Retrieved context panel validates exact passages and path support and shows the originating source and bridge. No new chatbot controls are added. Provider input receives compact path metadata alongside its existing source excerpts; the model output schema and citation permissions are unchanged.

## Checks

- Full Python suite: 370 passed, with one existing FastAPI/httpx deprecation warning.
- Frontend: 19 checks passed, including graph path identity/bridge validation, malformed path rejection, backwards-compatible reports and escaped graph explanations.
- Typecheck, formatting, self-contained live/hosted builds and `git diff --check` passed.
- Existing `tools/evaluate.py`: release macro-F1 1.0, baseline 1.0, graph recall@6 1.0 on four synthetic questions, quote integrity true. This does not measure the new graph expansion's general accuracy.
- `tools/graph_retrieval_probe.py --local-model`: the same synthetic backend/frontend question retrieves only Flask in the full hybrid budget before expansion, and includes a relevant Jinja passage afterward. The first four passages are preserved, the unrelated garden source is excluded and budgets/exact quotes pass. Both the real installed MiniLM worker and statistical fallback pass.
- All 12 existing retrieval fixtures return the same passages and order with expansion enabled and disabled, separately in neural and statistical modes. These are regression comparisons, not evidence of general production accuracy.
- Eighteen new Python cases cover source/version restrictions, no-match and overview preservation, cache invalidation and workspace isolation, ambiguous titles, unsupported target bodies, negative references, independent-of-findings assistant context, exact name boundaries, rare identifiers, no recursion, repository titles, inert commands, two-source limits and generic-word punctuation.

## Failed attempts and limits

The first targeted tests exposed a sentence-final period being treated as an identifier continuation, and repeated Flask sections depressing statistical similarity. Boundary handling now distinguishes punctuation from qualified names. An exact technology reference can also be corroborated by two substantive shared terms, excluding generic words and the bridge itself.

The retained `graph-retrieval-initial-results.json` records an overly broad source-title rule that treated Session recovery as a technology source and changed five statistical and two neural fixture results. Distinctive-title suffix rules and generic-name exclusions corrected that behavior. Final results are in `graph-retrieval-results.json`. The grading criterion was not weakened.

All examples are original synthetic text. No saved user workspaces or provider credentials were accessed. No browser testing, paid generation calls or generated-answer evaluation occurred. Title resolution, relevance thresholds and ranking weights are heuristics. Arbitrary titles, multiple versions claiming one identity and unrecognized aliases can prevent expansion. A supported graph connection does not establish that the returned passage answers the question or that an LLM answer is correct.
