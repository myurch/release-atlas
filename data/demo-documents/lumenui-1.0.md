# LumenUI

Version: 1.0. Repository: demo/lumenui. Frontend documentation.

This is original fictional documentation for Release Atlas demonstrations. The project, repository and examples are synthetic, not installable software.

## Overview and integration

LumenUI renders HTML templates for an order-management dashboard. The browser application uses TypeScript to display order lists, order details and sign-in status. LumenUI uses HarborAPI for order data. Both projects share the `order_id` field and a versioned JSON response contract.

## Routing and order data

The routing system maps `/orders` to the order list and `/orders/:order_id` to a detail view.

Keep navigation in the browser; fetching data does not change the visible route. The frontend calls GET /api/orders for a list and GET /api/orders/42 for one order. The `api_base_url` setting points at https://api.example.invalid in this fictional deployment.

The `page_size` default is 20 orders. Send the `offset` parameter to read another page. HarborAPI 1.0 returns an `items` array, a `total` count and an `offset` value. An empty array means no orders matched; it does not mean authentication failed.

## Authentication and security

Authentication uses an Authorization bearer token obtained during sign-in. Keep `access_token` in browser memory and discard it on sign-out. A reload requires signing in again. A 401 response opens the sign-in view; a 403 response displays a permissions message without repeatedly asking for credentials.

HTML templates use autoescaping to prevent XSS from untrusted order descriptions.

The `raw_html` setting remains supported for explicitly trusted administrator-authored banners. Never pass customer-supplied text to that escape hatch. Security review should check that HTTPS is used outside local development.

## Failures and retries

The `timeout_secs` default is 5 seconds. The `retry_limit` default is 3 retries for failed GET requests, in addition to the original attempt. Do not retry POST /api/orders automatically because version 1.0 has no duplicate-write protection. Show a retry button so the user controls a failed order submission.

Support staff use the `trace_id` field from an error response to locate a request. Keep that identifier in the error details, but avoid showing stack traces or access tokens in the browser.

## Caching and rendering

The `cache_ttl` default is 30 seconds for the order list. Saving an order invalidates the list and detail caches. A cached list is not a guarantee that an order still exists; handle a subsequent 404 by returning to the list with a short notice.

```typescript
const client = createOrderClient({
  api_base_url: "https://api.example.invalid",
  page_size: 20,
  timeout_secs: 5,
  retry_limit: 3,
  cache_ttl: 30,
});
client.openOrder("42");
```

## Compatibility and review checklist

Pair LumenUI 1.0 with HarborAPI 1.0. Version 2.0 changes pagination, authentication and error identifiers. Before upgrading, record the current bearer-token flow, the `raw_html` callers and the code that reads `trace_id`. The examples use an empty synthetic order store; no real customer records are included.
