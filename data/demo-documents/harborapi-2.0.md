# HarborAPI

Version: 2.0. Repository: demo/harborapi. Backend documentation.

This is original fictional documentation for Release Atlas demonstrations. The project, repository and examples are synthetic, not installable software.

## Overview and workspace isolation

HarborAPI is a Python web application framework for workspace-scoped order APIs. HarborAPI integrates with LumenUI through JSON endpoints and an HttpOnly `session_cookie`. Both projects share `workspace_id`, `order_id` and `request_id`. Authorization must verify workspace membership for every request, including cached reads.

## Routing and cursor pagination

The routing system exposes GET /api/v2/orders and POST /api/v2/orders. Require `workspace_id` on list requests. Version 1.0 paths redirect only for GET requests during migration; clients must explicitly update mutation paths to avoid replaying a write unexpectedly.

The `offset` parameter was removed. Use the opaque `cursor` parameter, and return `next_cursor` when more records are available. The `page_size` default is 50 orders and the maximum is 250. A cursor is tied to the active workspace and sort order; reject a cursor created for another workspace.

## Authentication and security

Authentication uses a signed, HttpOnly `session_cookie`. Require `X-CSRF-Token` on POST, PATCH and DELETE requests. Compare the `csrf_token` with the server session before writing data. Return 403 for a missing or invalid token. This guard is required even if a frontend validation check succeeded.

The `raw_html` setting was removed. HTML templates for operator pages always use autoescaping to prevent XSS from untrusted values. HTTPS is required outside local tests. The security fix also prevents an order identifier from another workspace from bypassing membership checks.

## Breaking retry configuration change

The `retry_limit` setting was removed in version 2.0. Replace it with `retry_policy`. A `max_attempts` value of 3 means the original request plus at most two retries. Reject unknown retry configuration fields at startup instead of silently falling back to a default.

Use `backoff_ms: 100` and retry only GET requests receiving 429 or 503. Honor the `Retry-After` header. The `timeout_secs` default increases to 8 seconds. The frontend 2.0 migration guide must be checked against this reference because it retained an older retry-setting instruction.

## Error contract and cache isolation

The `trace_id` field was removed. Error responses include `request_id`, `code` and `message`; return the same identifier in `X-Request-ID`. LumenUI should display `request_id` so a reviewer can correlate its screenshot with one server log record.

The `cache_ttl` default is 15 seconds. Cache keys include `workspace_id` and filters, and writes invalidate only that workspace's entries. This fixes a cross-workspace cache leak. A cache hit must still pass authorization.

```python
from harborapi import HarborApp

app = HarborApp(retry_policy={"max_attempts": 3, "backoff_ms": 100})

@app.route('/api/v2/orders')
def orders(request):
    return list_orders(workspace_id=request.workspace_id, page_size=50)
```

## Migration verification

Pair HarborAPI 2.0 with LumenUI 2.0, then verify cursor pagination, CSRF rejection, cache isolation and error identifiers. Resolve the contradictory `retry_limit` instructions before deploying the pair. Live events arrive in version 3.0; they are not part of this release's API contract.
