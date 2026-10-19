# Bundled demo README import validation

Historical record: the public README demo import was replaced by the original synthetic corpus. See [current synthetic demo validation](synthetic-demo-validation.md). Public README files remain only as regression fixtures.

Validated on 2026-10-18 without browser tests or model calls.

The original runtime import used 18 unauthenticated GitHub REST requests per click. A subsequent real request reproduced a GitHub denial/rate-limit response. The demo import now reads six pinned local snapshots and makes zero network requests. The separate individual README preview retains its existing live fetch behavior.

- Fourteen isolated tests exercise the real bundled files, with both the live fetch helper and httpx async network sending patched to fail if called. They cover all six imports, one revision/audit write, repeat/partial-previous-import duplicate skipping, existing-source preservation, origin/session/strict-input guards, changed workspace revisions, atomic capacity rejection, expired sessions, missing/malformed/incomplete/oversized bundles, tampered hashes/origins/repository metadata and retained license notices.
- All 82 focused demo-import and live-README tests passed. The complete Python suite passed 402 tests with one existing Starlette/httpx deprecation warning.
- All 23 frontend checks passed, including static rendering of the explicit button, disabled state, no automatic call and absence from views without the capability.
- Typecheck, formatting, both self-contained HTML builds, synthetic evaluation and git diff checks passed. The small evaluation reported macro F1 1.0 and exact quote integrity; it is not production accuracy evidence.
- Actual snapshot acquisition succeeded through unauthenticated public Git HEAD resolution and pinned HTTPS raw files, without using REST quota. Exact README text, commits, source URLs, fingerprints, upstream license URLs and complete BSD/MIT notices are retained in data/demo-readmes. The bundle is 17,081 bytes excluding its separate notices and provenance document.

The API tests use temporary databases, not saved user work. Public snapshot acquisition does not validate the visual browser experience; no browser or hosted CI suite was run locally. No model calls were made. These are pinned third-party documentation examples, separate from the original synthetic hosted demo.
