# Database input hardening

## Boundary and implementation

All application SQL in `backend/store.py` was reviewed. Statements are fixed strings and values use SQLite parameter binding. No HTTP or model tool accepts executable SQL, database paths or database handles. Code examples are preserved as exact data rather than stripped of punctuation or SQL keywords, retaining source hashes and Unicode quote offsets.

Additional controls:

- Runtime SQLite authorizer permits the required reads/inserts/updates on `workspace` and `saved_workspaces`, transaction control, and `json_extract`, `json_array_length` and `count`. Other capabilities are denied, including schema changes, table-level deletion, attachment, unexpected functions and trigger/view-origin operations. Source deletion still updates validated workspace JSON through the permitted store operation.
- Fixed startup migrations use a private bootstrap connection. Schema-origin execution is denied there as well. Existing migration and workspace-switch regression tests pass.
- Defensive mode is enabled. Trusted schema and extension loading are disabled. Attachments are limited to zero, SQL statements to 10,000 bytes, values/rows to 2,000,000 bytes and bound variables to 16. Source text can exceed the SQL statement length because it is bound data.
- Shared strict models reject invalid Unicode, NUL, C0 controls other than tab/CR/LF, and DEL. Valid Unicode, apostrophes, code, tabs and line endings remain unchanged. Frontend saved imports mirror the control-character rule. Previously accepted data containing these unsupported controls is rejected rather than silently changing stored source identities.
- HTTP input and source-tool arguments use `backend/input_validation.py`. JSON must be an unambiguous UTF-8 object: duplicate keys, NaN/infinities, malformed JSON and nesting beyond 64 levels are rejected without echoing supplied content. The existing streamed two-megabyte request limit runs first.
- Revision values must be actual integers in the signed-64-bit persistence range. Boolean/string/float revisions and overflows are rejected. Store entry points independently validate expected revisions and workspace selectors. Full workspaces are revalidated before database writes, within transactions.
- The existing exact-source preview, human confirmation, session, origin, revision, expiry and replay protections for chat actions remain in place.

## Automated evidence

`tests/test_database_security.py` adds 64 security tests using isolated temporary SQLite databases and synthetic inputs. Checks cover:

- Stacked SQL, tautology/deletion attempts, writable-schema and revision-overwrite strings, extension-loading syntax and HTML stored verbatim in source fields.
- Malicious names, notes, usage components, questions, workspace titles and imports stored as data while normal writes remain usable.
- A confirmed chat source containing SQL, Python file-writing syntax and HTML creates no marker file or schema changes. The model is mocked; the API and SQLite persistence path are real.
- A complete 12,000-code-point Unicode source preserves exact text, tabs, CR/LF and SHA-256 while exceeding the SQL statement-length limit as bound data.
- Injected workspace/source/token selectors, unknown fields, wrong types, oversized sources, invalid revisions, malformed Unicode and unsafe controls are rejected. Database schema and rows remain identical after rejected writes.
- Duplicate-key, non-finite, deeply nested, oversized-integer and malformed UTF-8 JSON is rejected atomically, including source-tool arguments.
- Direct runtime attempts to drop/alter/create tables or triggers, delete table rows, change PRAGMAs, attach databases, load extensions or allocate an oversized random blob are denied. Later legitimate saves still work.
- Injected triggers in a synthetic altered database cannot execute during runtime updates or startup inserts. A failed multi-statement save rolls back prior row changes.
- Independent SQLite connections run `PRAGMA integrity_check` and inspect schema/rows after attacks.

Final results: 197 Python tests and eleven frontend checks passed. Type checking, formatting, both HTML builds, the synthetic retrieval evaluation and `git diff --check` passed. One existing FastAPI/httpx deprecation warning remains. Local runtime: Python 3.14 and SQLite 3.50.4.

No browser tests, paid model calls or changes to saved user workspaces were performed for this hardening task. These are focused regression tests, not an independent penetration test or a guarantee against every possible attack. The trusted local-user access model and permitted human editing capabilities are unchanged.

References: [Python parameter binding](https://docs.python.org/3/library/sqlite3.html#sqlite3-placeholders), [SQLite defensive guidance](https://www.sqlite.org/security.html).
