"""Fail-closed entrypoint for the Python service behind the GPT Site gateway."""
from __future__ import annotations

import os
import re
import runpy
from pathlib import Path
from urllib.parse import urlsplit


def https_origin(value: str) -> str:
    parts = urlsplit(value)
    if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path not in ('', '/')
            or parts.port not in (None, 443)):
        raise ValueError('Hosted origins must be HTTPS origins without paths or credentials')
    return f'https://{parts.netloc}'


def configure() -> None:
    """Require explicit secrets and durable storage; never print their values."""
    gateway = os.getenv('ATLAS_GATEWAY_TOKEN', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,200}', gateway):
        raise ValueError('Set a strong ATLAS_GATEWAY_TOKEN before starting the hosted service')
    access_code = os.getenv('ATLAS_ACCESS_CODE', '')
    if len(access_code) < 32 or len(access_code) > 200 or not access_code.isascii():
        raise ValueError('Set an ATLAS_ACCESS_CODE of 32 to 200 ASCII characters')
    if not (os.getenv('ATLAS_LLM_KEY') or os.getenv('OPENAI_API_KEY', '')).strip():
        raise ValueError('Configure the OpenAI runtime secret before starting the hosted service')
    site = https_origin(os.getenv('ATLAS_SITE_ORIGIN', ''))
    backend = https_origin(os.getenv('ATLAS_BACKEND_ORIGIN') or os.getenv('RENDER_EXTERNAL_URL', ''))
    data_path = Path(os.getenv('ATLAS_DATA_DIR', ''))
    if not data_path.is_absolute() or data_path == Path('/'):
        raise ValueError('ATLAS_DATA_DIR must name an absolute directory on a persistent disk')
    port = os.getenv('PORT', '8765')
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError('PORT must be between 1 and 65535')
    os.environ.update({
        'ATLAS_AUTH_ENABLED': '1',
        'ATLAS_COOKIE_SECURE': '1',
        'ATLAS_HOST': '0.0.0.0',
        'ATLAS_PORT': port,
        'ATLAS_ORIGINS': ','.join(dict.fromkeys([site, backend, f'http://127.0.0.1:{port}'])),
        'ATLAS_LLM_KIND': 'openai',
        'ATLAS_LLM_BASE': 'https://api.openai.com/v1',
    })


if __name__ == '__main__':
    try:
        configure()
    except (ValueError, OSError):
        raise SystemExit('Hosted configuration is incomplete. Check runtime secrets, HTTPS origins, PORT and persistent data directory.') from None
    runpy.run_module('backend', run_name='__main__')
