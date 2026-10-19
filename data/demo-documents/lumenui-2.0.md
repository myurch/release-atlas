# LumenUI

Version: 2.0. Repository: demo/lumenui. Frontend documentation.

This is original fictional documentation for Release Atlas demonstrations. The project, repository and examples are synthetic, not installable software.

## Overview and integration

LumenUI renders HTML templates for a workspace-scoped order dashboard. The TypeScript frontend uses HarborAPI for JSON order data. Both projects share `workspace_id`, `order_id` and `session_cookie` conventions. Workspace navigation keeps one organization's orders separate from another organization's orders.

## Routing and cursor pagination

The routing system now maps `/workspaces/:workspace_id/orders/:order_id` to order details. Fetch the order list with GET /api/v2/orders and send `workspace_id` as a query parameter. A bookmarked order from another workspace must show an access message rather than silently changing the current workspace.

The `page_size` default is 50 orders. The `offset` parameter was removed. Read `next_cursor` from the response and send it as `cursor` for the next page. Reset the cursor after changing the workspace or sort order. The response still contains `items`, but no longer promises a `total` count for every query.

## Authentication and security

Authentication now uses the HttpOnly `session_cookie` supplied by HarborAPI. Browser code cannot read that cookie directly. Send credentials with same-origin requests and send `X-CSRF-Token` on POST, PATCH and DELETE requests. A missing `csrf_token` produces a 403 response. Clear cached workspace data after sign-out.

Use HTTPS for session-bearing requests outside local tests. The browser should not log cookie values or the CSRF token when reporting a failed action.

The `raw_html` setting was removed. HTML templates must use autoescaping to prevent XSS from untrusted descriptions. Render administrator banners through `escape_html()` as well. The security migration is mandatory even when the rest of the interface looks unchanged.

## Timeouts and client retries

The `timeout_secs` default increases from 5 to 8 seconds to accommodate workspace authorization checks. GET requests may be retried, but writes still require a deliberate user action unless duplicate-write protection has been configured.

The `retry_limit` setting remains supported in version 2.0 of the shared client configuration. Keep the existing value of 3 while migrating the order list. This frontend migration guidance should be checked against the backend configuration reference before enabling retries in a shared deployment.

## Error handling and cache isolation

The `trace_id` field was removed from error responses. Display the new `request_id` so support can correlate a failed browser action with a backend log. If a request is forbidden, keep the existing page and explain the denied action; do not erase the entire dashboard.

The `cache_ttl` default is 15 seconds. Cache keys must include `workspace_id` and the active filters. This fixes a bug where switching workspaces could briefly display the previous workspace's order list. Invalidate both list and detail caches after a successful mutation.

```typescript
const page = await client.listOrders({
  workspace_id: "demo-team",
  page_size: 50,
  cursor: previousPage.next_cursor,
});
renderOrders(page.items);
```

## Migration checks

Pair LumenUI 2.0 with HarborAPI 2.0. Check cursor navigation, cookie sign-out, CSRF failures and the visible `request_id`. Review the retry-setting guidance across both repositories rather than assuming the two guides agree. Version 3.0 adds live order events and resolves the retry configuration terminology.
