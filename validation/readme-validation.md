# Public README fetch validation

Implemented on 2026-10-17. Sources can explicitly fetch the README of a public GitHub repository into a draft. Fetching does not save or analyze it. The separate Save source action retains the normal revision, source validation and persistence rules.

## Boundaries

- `backend/readme.py` accepts HTTPS GitHub repository root URLs only. It makes three unauthenticated requests to fixed `api.github.com` paths: public repository metadata, default-branch commit and README at that commit. It ignores returned download URLs, disables redirects and environment proxies, and sends no provider credentials.
- The overall deadline is 20 seconds, with 10-second HTTP timeouts and 250,000-byte response bounds. README content must be a regular base64-encoded UTF-8 file with a matching Git blob hash, within the existing 12,000-code-point source limit. Text, Unicode and line endings remain exact. Nothing is silently truncated.
- `POST /api/sources/readme` checks origin, session and revision, permits one fetch at a time, and checks session/revision again after network work. It returns a preview without database writes or audit events.
- `frontend/SourceForm.tsx` rejects stale results, aborts pending requests on unmount and requires an inline Replace/Keep decision when source text already exists or a draft changes during fetching. Existing title, version and permission fields are preserved. A blank permission field remains blank for the reviewer to complete. No HTML or README instructions are executed.
- Fetch controls are absent in hosted demonstrations, saved-file views and tutorials.

GitHub's [Get a repository README documentation](https://docs.github.com/en/rest/repos/contents#get-a-repository-readme) describes the public endpoint and commit reference parameter. Arbitrary websites, private repositories, individual file URLs, automatic refresh, license detection and oversized-document splitting are outside this feature.

## Error coverage

| Case | Result and guidance |
| --- | --- |
| Unsupported URL, credentials, deceptive host, port or local address | 422; enter a public GitHub repository URL |
| Repository missing or private | 404; check URL, private repositories unsupported |
| No default branch/commit or no README | 404; paste manually or choose another repository |
| Empty README | 422; paste manually or choose another repository |
| GitHub 403/429 | 503; public API access/rate limit, retry later or paste manually |
| Redirect | 422; use the current repository URL |
| Upstream 5xx/network failure | 502; retry/check server connectivity, draft unchanged |
| HTTP or overall timeout | 504; retry or paste manually, draft unchanged |
| Invalid JSON, metadata, encoding, Unicode, control characters or hash | 502; unreadable data, paste manually or retry |
| Oversized response or README | 422; paste a smaller excerpt, no truncation or save |
| Concurrent request or changed workspace | 409; wait or fetch again |
| Expired session | 401; normal sign-in guidance |
| Browser cannot reach Atlas or aborts after 25 seconds | Local actionable message, draft unchanged |

## Actual checks

- Full Python suite: **295 passed**, with one existing FastAPI/httpx deprecation warning. This includes **68 README tests** using synthetic fixtures, mocked HTTP transports and real ASGI handlers with isolated SQLite files. Tests verify exact text, fixed-host requests, absent credentials, failure messages, unchanged database snapshots, normal saving, concurrency, expired sessions and stale workspace rejection.
- Frontend checks: **14 passed**, including README validation, exact text preservation, draft merging, error messages and static server rendering of live/offline form controls. The initial browser-renderer test kept its scheduler alive after assertions; it was replaced with Node's server renderer and the full suite then exited successfully.
- TypeScript, formatting, production build, synthetic evaluation and `git diff --check`: passed.
- Real public GitHub check: **PASS**, using `tools/readme_probe.py --live` and `octocat/Hello-World`. The commit-pinned README was fetched and validated. Metadata only is recorded in `validation/readme-integration-results.json`; no source text or workspace was saved.

No browser testing was performed, as requested. Dynamic form interactions and visual layout remain for the user's manual test. No model API calls were made, no API keys were required, and saved user workspaces were not modified. Mocked failure cases do not imply that every upstream failure was induced on GitHub itself.
