# HarborAPI

Version: 3.0. Repository: demo/harborapi. Backend documentation.

This is original fictional documentation for Release Atlas demonstrations. The project, repository and examples are synthetic, not installable software.

## Overview and asynchronous service

HarborAPI is an async Python web application framework for order APIs and live updates.

HarborAPI integrates with LumenUI through JSON endpoints and an authenticated event stream. Both projects share `workspace_id`, `order_id`, `request_id` and `last_event_id`.

AsyncIO support allows waiting for an upstream service without blocking unrelated order requests.

## Routing and page limits

The routing system exposes GET /api/v3/orders, POST /api/v3/orders and GET /api/v3/events. Keep version 2.0 read paths available for one migration window, but require new writes to use the current path. Do not treat a browser route as an authorization boundary.

The `page_size` default is 100 orders and the maximum is 500. Both values increased from the 2.0 defaults of 50 and 250. Continue using `cursor` and `next_cursor`; the `offset` parameter is no longer supported. Reject a cursor when its workspace or filter fingerprint does not match the request.

## Authentication and security

Authentication continues to use an HttpOnly `session_cookie`, with `X-CSRF-Token` required on mutations. Sessions are renewed by the server after a successful authenticated request. Clear the session on sign-out and reject reconnects from an expired session before sending event history.

For security, require HTTPS for order APIs and event streams. HTML templates for operator pages use autoescaping to prevent XSS.

The `raw_html` setting is no longer supported. Validate forwarded host headers against the configured `allowed_hosts` list before constructing redirect links; this fixes an open-redirect issue in older deployments.

## Retry policy and duplicate-write protection

Use `retry_policy` with `max_attempts: 3` and `backoff_ms: 200`. The `retry_limit` setting is no longer supported. Retry safe GET requests on 429 and 503, honor `Retry-After`, and preserve `request_id` in the diagnostic chain. The `timeout_secs` default is 10 seconds.

POST /api/v3/orders supports an `Idempotency-Key` header. Store the first result for 24 hours and return it when the same key and payload are submitted again. A reused key with a different payload returns 409. This makes a deliberate write retry safer; it does not authorize a client to retry every failed mutation blindly.

## Event delivery and cache consistency

GET /api/v3/events emits server-sent events named `order.updated`. Each event contains `workspace_id`, `order_id` and `event_id`. Accept `last_event_id` on reconnect and replay up to 100 retained events. If the requested event has expired, send a reset notice so LumenUI can reload the list.

The `cache_ttl` default is 10 seconds. Commit the order before publishing its event, invalidate that workspace's list cache, and never broadcast another workspace's event. Event delivery is at least once, so a browser must deduplicate `event_id` rather than counting every delivery as another order change.

```python
from harborapi import HarborApp

app = HarborApp(retry_policy={"max_attempts": 3, "backoff_ms": 200})

@app.route('/api/v3/orders')
async def orders(request):
    return await list_orders(workspace_id=request.workspace_id, page_size=100)
```

## Acceptance checks

Pair HarborAPI 3.0 with LumenUI 3.0. Verify CSRF failures, duplicate idempotency keys, expired event history and cross-workspace event isolation. Compare defaults with older guides before copying configuration. A documented fix or a successful synthetic test is not proof that a real deployment is secure.
