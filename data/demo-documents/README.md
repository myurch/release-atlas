# Synthetic versioned documentation

These six original fictional documents were written for Release Atlas demonstrations with AI assistance. Credit Maryana Yurchyshyna as the creator of Release Atlas. The documents use the project's MIT license. No text was copied from Pallets or another real software project.

The repositories `demo/lumenui` and `demo/harborapi`, their packages, APIs and deployment examples are fictional. Origins use the reserved `example.invalid` domain; they are provenance labels, not live websites. Examples are not installable software or production security advice.

| Fictional repository | Version | Source document |
| --- | --- | --- |
| demo/lumenui | 1.0 | [Frontend 1.0](lumenui-1.0.md) |
| demo/lumenui | 2.0 | [Frontend 2.0](lumenui-2.0.md) |
| demo/lumenui | 3.0 | [Frontend 3.0](lumenui-3.0.md) |
| demo/harborapi | 1.0 | [Backend 1.0](harborapi-1.0.md) |
| demo/harborapi | 2.0 | [Backend 2.0](harborapi-2.0.md) |
| demo/harborapi | 3.0 | [Backend 3.0](harborapi-3.0.md) |

## What the versions demonstrate

| Topic | 1.0 | 2.0 | 3.0 |
| --- | --- | --- | --- |
| Pagination | Offset, default 20 orders | Cursor, default 50 | Cursor, default 100 |
| Backend page maximum | 100 orders | 250 | 500 |
| Authentication | In-memory bearer token | HttpOnly session cookie and CSRF checks | Server-managed renewal and protected event reconnects |
| Error correlation | trace_id | request_id | request_id across events/retries |
| Retries | retry_limit: 3 retries after first attempt | Backend switches to retry_policy; frontend guide is stale | Both use max_attempts: 3 total attempts |
| Timeouts | 5 seconds | 8 seconds | 10 seconds |
| Cache lifetime | 30 seconds | 15 seconds, workspace isolation fix | 10 seconds, event invalidation |
| HTML | Autoescaping with a trusted raw_html escape hatch | raw_html removed | Safe navigation fix; no raw_html |
| Live updates | Refresh required | No event contract | Event replay, deduplication, reset on expired history |
| Writes | No automatic retry | Deliberate user retry | Idempotency-Key with 24-hour retention |

There is exactly one intended same-version documentation conflict: the LumenUI 2.0 guide says `retry_limit` remains supported; HarborAPI 2.0 says it was removed. LumenUI 3.0 explicitly corrects the stale guide. This gives human review a concrete disagreement without confusing normal differences between versions with contradictions. The existing conservative conflict detector can flag this pair; it does not establish general contradiction detection.

## Try these questions

- How do LumenUI and HarborAPI 3.0 work together?
- How do I add routing, and which endpoints changed in 2.0?
- Which documents mention security or HTTPS?
- Which documents use Python rather than TypeScript?
- Compare authentication in 1.0 and 3.0.
- Do the 2.0 guides agree about retry_limit?
- Which retry configuration should I use in 3.0?
- How many attempts does each retry setting permit?
- How much did the default page size increase between 1.0 and 3.0?
- What must the frontend do when an event cannot be replayed?

The graph can show shared routing, HTML rendering/escaping, Python usage, literal query mentions and version-scoped integration statements. Shared-capability links do not establish compatibility between arbitrary frontend/backend version combinations. Graph nodes display their versions. On Evidence, headings and short paragraphs produce citable migration, configuration, API, security and example passages with typed settings/endpoints/APIs. Topic labels are learned by the existing NLP and may vary in usefulness.

## Import and maintenance

The Sources demo button loads these six local files via `manifest.json`, validates their exact hashes and fixed metadata, then appends them in one guarded revision. Repeat imports skip identical versions/text. Existing user sources and drafts are preserved. Analyze sources afterward. Hosted/tutorial/saved-file views do not receive a live import control, and the preloaded synthetic hosted review remains separate.

Keep the explicit fictional notice in every document. After intentional source edits, update the matching SHA-256 entries in manifest.json and rerun demo import, analysis and graph tests. LF line endings are enforced for stable hashes and exact Unicode quote positions. Builds do not silently rewrite this corpus. The earlier public Pallets README snapshots remain only as licensed regression fixtures for existing graph tests.
