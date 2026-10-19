# HarborAPI

Version: 1.0. Repository: demo/harborapi. Backend documentation.

This is original fictional documentation for Release Atlas demonstrations. The project, repository and examples are synthetic, not installable software.

## Overview and frontend contract

HarborAPI is a Python web application framework for a small order service. HarborAPI integrates with LumenUI through an HTTP JSON contract. Both projects use `order_id` to identify an order. The backend owns validation, storage and authorization; browser-side checks only improve feedback and cannot grant access.

## Routing and pagination

The routing system exposes GET /api/orders, GET /api/orders/42 and POST /api/orders. Return 404 for an unknown `order_id`, 400 for malformed input and 401 when the bearer token is missing or expired. Do not return an empty success response for every failure.

The `page_size` default is 20 orders and the maximum is 100. The `offset` parameter starts at zero. Responses include `items`, `total` and `offset`; a stable creation-time sort keeps repeated pages predictable while the dataset is unchanged.

## Authentication and security

Authentication requires an Authorization bearer token on each order request. Validate it before reading an order. This release does not use `session_cookie` authentication and does not require a browser CSRF token, because credentials are explicitly attached to the request rather than automatically supplied as a session cookie.

For security, require HTTPS at the edge and keep access tokens out of logs. Render HTML templates for operator error pages with autoescaping to prevent XSS.

The `raw_html` setting remains supported only for trusted administrator-authored diagnostics; never include an untrusted order description in raw output.

## Retry configuration and failures

The `retry_limit` setting remains supported. Its default is 3 retries after the original request, and it applies only to safe GET operations performed by internal clients. Do not automatically repeat POST /api/orders because a timed-out response may hide a completed write.

The `timeout_secs` default is 5 seconds for an upstream request. Error JSON includes `trace_id`, `code` and `message`. Return a useful message to LumenUI while keeping stack traces in server logs. A diagnostic identifier is not an authorization token.

## Caching and Python example

The `cache_ttl` default is 30 seconds for list responses. Clear cached lists after a new order is committed. Version 1.0 has one workspace and does not support live event replay; clients must refresh to observe another user's change.

```python
from harborapi import HarborApp

app = HarborApp()

@app.route('/api/orders')
def orders(request):
    return list_orders(page_size=20, offset=0)
```

## Upgrade preparation

Before moving to version 2.0, inventory `offset`, `trace_id`, `raw_html` and `retry_limit` consumers. Match the frontend and backend major versions. A supported setting in this 1.0 guide is not evidence that the same setting survives a later release.
