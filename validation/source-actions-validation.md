# Restricted chat source actions

Implemented `manage_source` with exactly `add_source` and `delete_source`. There is no SQL interface, database connection, arbitrary update, review-decision, workspace-switch, file or network tool. The existing calculator remains read-only. Questions generation receives only the calculator.

`backend/source_actions.py` validates strict tool arguments, resolves omitted metadata and prepares one action on a copy. Missing titles use the next currently saved `Source N`, version defaults to `1`, URL is empty, permission notice is `User supplied; verify redistribution rights`, and absent text becomes `No source text supplied for <title>.`. Title-specific placeholders allow successive empty sources without bypassing ordinary duplicate-content checks. Supplied text is preserved verbatim. Defaults do not establish a real version or grant redistribution rights.

The source tool is exposed only when the current request uses an add/create/save/store/import/delete/remove verb and refers to sources, snapshots, a current source title/ID or the selected source. This is a conservative capability gate, not a general natural-language authorization proof. The human preview remains authoritative. Ambiguous repeated titles require an explicit version, ID, current selection or requested version-order rule. The answer-policy default of preferring newer snapshots never authorizes deleting a newer version.

After model-answer, citation, session and revision validation, `backend/app.py` retains a bounded proposal and returns an opaque token to the browser. Tokens are not sent to the model, expire after ten minutes and bind the proposal to its exact session and global revision. The confirmation endpoint accepts only token/revision, rechecks guards, applies the shared source helper through audited `Store.save`, and consumes the token. Existing source routes use the same helpers. Delete retains dependent-finding/answer cleanup, graph/topic invalidation and unrelated reviews. Concurrent workspace changes reject old proposals.

`frontend/Assistant.tsx` displays metadata, source text and deletion consequences, with explicit Add source / Delete source and Cancel controls. Confirmed writes refresh the workspace. Source proposals cannot be applied from hosted, saved-file or tutorial views. Source preview validation is in `frontend/source-actions.ts`.

## Validation performed

- 133 Python tests passed, with one existing FastAPI/httpx deprecation warning. New tests exercise wire contracts, real isolated SQLite persistence through mocked model responses, confirmation, defaults, consecutive empty sources, duplicate/size limits, deletion cleanup, session/origin guards, token expiry/replay, workspace changes/switches, unsupported operations and source-tool exclusion from Questions generation.
- Ten frontend checks passed, including rejection of unsupported source operations, stale previews and altered deletion targets.
- Type checking, formatting, both HTML builds, synthetic retrieval evaluation and `git diff --check` passed.
- Eight final real GPT-6 Luna tasks passed: omitted metadata/text, verbatim text, explicit metadata, specific deletion, ambiguous deletion, unsupported edits, source-document injection and calculator subtraction. They used 15 API requests and synthetic in-memory workspaces only. See `source-action-model-probe-final.json`. They did not write to saved user databases.
- All 49 existing answer scenarios ran twice: 98/98 passed, 144 API requests, estimated uncached text-token cost $0.051677. Three independent shards cover every case exactly twice. No read-only case received a source tool. Five tasks encountered rejected calculator arguments and recovered within the existing limits; their tool errors remain in the report. See `assistant-eval-source-actions-final.json` and its named shard reports.
- No browser testing was performed, following the user's request. UI interaction remains for the user to verify after restarting Atlas.

## Retained attempts and limits

The initial source-action probe passed 7/8: Luna chose the newer of two identically titled sources for an ambiguous delete. Confirmation prevented any write. The second probe passed 6/8: the new selector guard rejected a version followed by sentence punctuation, and Luna proposed an unrelated source addition for an unsupported usage-profile edit. Both were corrected by the version-boundary check and server capability gate. The third probe passed 8/8 before title-specific empty-text placeholders were added. The final probe reran all eight and passed. Reports `source-action-model-probe-initial.json`, `source-action-model-probe-attempt-2.json` and `source-action-model-probe-attempt-3.json` retain these outcomes. No failed answers were removed.

An earlier regression run was interrupted after nine completed scenarios when the source-action probe revealed issues. Its report is explicitly marked incomplete in `assistant-eval-source-actions-interrupted.json`; it is not acceptance evidence. The complete corrected run is separate.

These are finite synthetic tests, not a guarantee of arbitrary-language intent or model correctness. Inspect the exact preview before confirming. The fixed backend operations, strict validation and human confirmation provide the permission boundary regardless of model wording.

Function-calling implementation reference: [official OpenAI documentation](https://developers.openai.com/api/docs/guides/function-calling).
