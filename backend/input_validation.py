"""Unambiguous, bounded JSON objects at HTTP and source-tool input boundaries."""
from __future__ import annotations

import json


def json_object(body: str | bytes | bytearray):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON field')
            result[key] = value
        return result

    def reject_constant(_):
        raise ValueError('Non-finite JSON number')

    try:
        text = body if isinstance(body, str) else body.decode('utf-8')
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)
        if not isinstance(value, dict):
            raise ValueError('Expected JSON object')
        stack = [(value, 1)]
        while stack:
            item, depth = stack.pop()
            if depth > 64:
                raise ValueError('JSON nesting limit exceeded')
            if isinstance(item, dict):
                stack.extend((child, depth+1) for child in item.values())
            elif isinstance(item, list):
                stack.extend((child, depth+1) for child in item)
        return value
    except (ValueError, RecursionError) as exc:
        # Never include supplied content or decoder diagnostics in API errors.
        raise ValueError('Invalid or ambiguous JSON input') from exc
