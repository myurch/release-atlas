# Synthetic versioned demo validation

Validated 2026-10-18. No browser tests, model calls, network requests or saved-user-workspace writes were used.

## Corpus

Six original fictional Markdown documents cover two repositories: demo/lumenui frontend and demo/harborapi backend, each at versions 1.0, 2.0 and 3.0. Files range from about 3 KB to 4 KB, totaling 20,567 Unicode characters. They retain explicit fictional notices, original synthetic MIT attribution, fixed numeric versions and reserved example.invalid origins. The strict manifest contains SHA-256 fingerprints, not duplicated document text. LF checkout rules preserve exact hashes and quote offsets.

The existing local analysis pipeline produces 84 exact-span passages, four NMF topics and one same-version conflict pair: LumenUI 2.0 retains retry_limit while HarborAPI 2.0 removes it. LumenUI 3.0 corrects the stale guidance. Ordinary differences across 1.0, 2.0 and 3.0 are not mislabeled as same-version conflicts. These corpus checks demonstrate fixtures and conservative rules, not production accuracy or general contradiction detection.

## Import checks

All 17 demo import tests passed in temporary databases with live README fetching and httpx async sends patched to fail if called. They verify all six additions in one revision/audit event, repeat/partial duplicate skipping, preservation of existing sources, origin/session/strict-input guards, changed workspace rejection, session expiry, atomic source-capacity failure, missing/malformed/incomplete/oversized manifests, wrong hashes/origins/repos/versions and path traversal rejection. The complete bundle is validated before any database write. A real FastAPI TestClient import followed by analysis verifies all six source identities, typed configuration/API/package/endpoint extraction, topics, exact quote positions and the intended conflict.

The button now calls /api/sources/demo-documents. The old demo-readmes route and backend/demo_readmes.py loader were replaced. Public README snapshots and BSD/MIT notices remain only as fixtures for existing graph regressions. Individual live GitHub README fetching remains unchanged. Existing saved sources, including previously imported public READMEs, are not deleted; a fresh workspace provides an isolated demo corpus.

## Graph checks

The new frontend corpus check verifies exactly two document titles with three versions each and all six unique hashes. Backend/frontend, routing, security and HTTPS questions produce supported maps within the existing six-node/eight-link limits. Python usage identifies the three HarborAPI versions. Restricting graph input to the 3.0 pair yields an explicit integration relationship. Every link's Unicode quote is checked against its original source. Static React rendering verifies that 1.0, 2.0 and 3.0 appear visibly on two graph nodes each.

Initial fixture checks found a missing HTTPS statement in the frontend 2.0 guide and positive routing/integration descriptions mixed with unrelated negative caveats. The documentation was clarified into independently citable paragraphs without changing NLP rules or weakening the expected graph checks. The visible-version assertion was corrected to allow ordinary SVG attributes after its class name. Final checks passed.

## Regression results and limits

- Full Python suite: 405 passed, with one existing Starlette/httpx deprecation warning.
- Focused 17 import/analysis tests passed again after the final document paragraph edits.
- Frontend checks: 27 passed, including the original public README graph, hybrid retrieval telemetry, stream/state, citation, hosted/tutorial, security and source-draft checks.
- Typecheck, formatting, both self-contained builds and git diff checks passed.
- Existing tiny synthetic evaluation stayed at macro F1 1.0, graph recall 1.0 on four prepared queries and exact quote integrity. This is not a new accuracy evaluation of the larger corpus.
- Hash comparison confirmed backend/retrieval_graph.py, backend/source_context.py, backend/assistant.py, backend/nlp.py, backend/providers.py, frontend/retrieval.ts, frontend/Assistant.tsx, frontend/assistant-stream.ts and frontend/question-graph.ts unchanged. backend/app.py changes are restricted to the demo loader/route and import audit wording. The Evidence page implementation is untouched.

Hosted preloaded data, tutorial state and prepared answers remain separate. No browser/CI run or real generated-answer evaluation was performed for this change. Multiple versions can share capabilities without establishing cross-version compatibility; exact pairs and migration guidance must still be read. The examples are fictional and are not installable or deployable packages.
