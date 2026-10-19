# LumenUI

Version: 3.0. Repository: demo/lumenui. Frontend documentation.

This is original fictional documentation for Release Atlas demonstrations. The project, repository and examples are synthetic, not installable software.

## Overview and integration

LumenUI renders HTML templates for a live order dashboard. The TypeScript frontend uses HarborAPI for order data and event delivery. Both projects share `workspace_id`, `order_id`, `request_id` and `last_event_id`. The interface supports partial updates without reloading the whole workspace.

## Routing and large order lists

The routing system preserves `/workspaces/:workspace_id/orders/:order_id`. Order lists use GET /api/v3/orders and cursor pagination. The `page_size` default is 100 orders, up from 50 in version 2.0 and 20 in version 1.0. The backend accepts a maximum of 500; the default and the maximum are different limits.

Keep `cursor` opaque. Reset it when the workspace, filter or sort order changes. Reuse `order_id` as the stable rendering key so newly received events do not recreate every row or move keyboard focus unexpectedly.

## Authentication and security

Authentication continues to use an HttpOnly `session_cookie`. Send `X-CSRF-Token` on mutations and clear the UI when HarborAPI reports an expired session. A session refresh is server-managed; do not copy access tokens into local storage to avoid a sign-in prompt.

HTML templates use autoescaping to prevent XSS.

The `raw_html` setting is no longer supported. The `escape_html()` helper remains available for text fragments. A security fix now validates external navigation targets before opening them; allow HTTPS links and reject executable URL schemes.

## Retry policy and migration correction

The `retry_limit` setting is no longer supported. Use `retry_policy` with `max_attempts: 3`, which means one original attempt and at most two retries. The older value `retry_limit: 3` meant three retries after the original attempt, so blindly copying the number changes the request budget.

The 2.0 frontend guide incorrectly described `retry_limit` as supported by the shared configuration. HarborAPI 2.0 had already removed it. This 3.0 guide corrects that stale migration instruction. The `timeout_secs` default is 10 seconds; a timed-out request does not prove that a write failed on the server.

## Live updates and cache consistency

Subscribe to GET /api/v3/events for server-sent order updates. An `order.updated` event includes `order_id` and a monotonically increasing `event_id`. Save `last_event_id` and send it when reconnecting. If replay is unavailable, reload the list instead of assuming the cache is current.

The `cache_ttl` default is 10 seconds. Apply events only to the active workspace and ignore duplicate event identifiers. When offline, keep the last rendered list visible with a stale-data notice; disable mutations until authentication and connectivity recover.

```typescript
const retry_policy = { max_attempts: 3, backoff_ms: 200 };
client.subscribeOrders({
  workspace_id: "demo-team",
  last_event_id: "event-120",
  onUpdate: updateVisibleOrder,
});
```

## Acceptance checks

Pair LumenUI 3.0 with HarborAPI 3.0. Test expired sessions, duplicate events, a disconnected browser and keyboard focus during a row update. Compare the three frontend versions to distinguish new features, removed options and corrected documentation, rather than treating every textual difference as a breaking change.
