# Agent instructions: Release Atlas

## Product and architecture

Release Atlas helps software maintainers review upgrade evidence. It connects versioned source text, declared application usage, cited findings, technical identifiers and human review decisions.

- Backend: Python, FastAPI, SQLite, scikit-learn and NetworkX.
- Frontend: React, TypeScript and CSS. Edit frontend sources, then rebuild the self-contained HTML with `npm run build`.
- `backend/models.py` defines validated data contracts; `backend/store.py` owns persistence and revision checks; `backend/nlp.py` implements analysis and retrieval; `backend/providers.py` implements model adapters.
- `frontend/main.tsx` contains the workbench; `frontend/tutorial.ts` and `frontend/TutorialGuide.tsx` define the beginner tutorial; `frontend/WorkspaceDialog.tsx` manages saved workspace selection.
- The standalone HTML browses saved reviews. New analysis and collaboration require the Python service. Optional generation supports Ollama and OpenAI-compatible services.

## Working practices

- Every commit author and committer must use `36048692+myurch@users.noreply.github.com`. Set repository-local Git identity; never rely on or change the machine's global identity.
- Make focused commits with clear messages. Preserve unrelated work. Keep this file and README accurate when behavior, setup or validation changes.
- Keep runtime state, credentials, installed dependencies and caches out of Git. `.atlas/` and environment files are private local data.
- Retain the MIT license, embedded runtime notices and generated-logo provenance.
- Use only permitted public or synthetic source material in fixtures and demonstrations.

## Correctness boundaries

- Source text retains version, origin, hash and exact Unicode quote positions. Validate references and bounded inputs on import.
- User-supplied usage matches suggest possible relevance; the app does not inspect application source code or prove upgrade safety.
- Default embeddings are statistical TF-IDF/SVD representations. Category scores are uncalibrated. The small synthetic evaluation is not evidence of production accuracy.
- Conflict detection uses conservative rules scoped to the same identifier and version. It is not general contradiction detection.
- Retrieved citations and schema validation do not guarantee that a generated answer is true. Keep supporting passages visible and retain human review.
- Writes require the expected workspace revision. Preserve stale-draft protection, global revisions across workspace switches and per-workspace audit history.
- The current service uses one worker, loopback binding and shared-code sessions for trusted users. Do not silently widen network access or weaken origin, session or input guards.
- Treat document text as untrusted data. Provider credentials belong only in the server environment.

## User experience

- Keep the generated logo and System/Dark/Light appearance options. Follow the host theme, use dark as the fallback, and preserve manual choices.
- Lead with the evidence-review task. Do not add promotional offline badges or expose deployment details where they do not help the user.
- Use plain language and no em dashes in authored text. Explain the goal, required input and useful result before technical terminology.
- The beginner tutorial uses separate temporary state and prepared outputs. Preserve live drafts, Next/Back/Replay/Exit behavior, visible navigation, keyboard support and reduced motion. Tutorial actions must not write to the live API or invoke models.
- A pending UX improvement is replacing the usage-profile delimiter format with clearly labeled application-part and setting/API fields. This is not implemented yet.

## Validation

Run the checks relevant to the change and review regressions before committing:

- `npm run typecheck`
- `npm run format:check`
- `npm run build`
- `npm test`
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q`
- `.venv/bin/python tools/evaluate.py`
- `git diff --check`

For affected integrations, use `tools/integration_probe.py`, `tools/live_probe.py` and `npm run test:browser` in an appropriate environment. Keep test data isolated from saved user work. Report actual results and distinguish mocks, static checks and real integration tests.

Local validation has covered 16 Python tests, six frontend checks and supported browser interactions. Direct standalone file-browser execution, the complete local Playwright run and container runtime remain unverified in the original development environment. Consult actual CI results rather than assuming these checks passed. Do not describe this preview as fully production-validated.
