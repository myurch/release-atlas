"""Load private repository configuration as data, never as shell code."""
from __future__ import annotations

import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path | None = None):
    """Read single-line KEY=value settings; existing environment values win."""
    path = ROOT / '.env' if path is None else path
    try:
        content = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return
    for number, line in enumerate(content.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        name, separator, value = line.partition('=')
        name, value = name.strip(), value.strip()
        if not separator or not re.fullmatch(r'(?:ATLAS_[A-Z0-9_]+|OPENAI_API_KEY)', name):
            raise ValueError(f'Invalid .env setting on line {number}; use ATLAS_* or OPENAI_API_KEY assignments.')
        if value.startswith(('"', "'")):
            quote = value[0]
            end = value.find(quote, 1)
            if end < 0 or (value[end + 1:].strip() and not value[end + 1:].strip().startswith('#')):
                raise ValueError(f'Invalid .env quoting on line {number}. Use a single-line value.')
            value = value[1:end]
        else:
            value = re.split(r'\s+#', value, maxsplit=1)[0].rstrip()
        # No interpolation, command substitution or escape interpretation.
        os.environ.setdefault(name, value)


if __name__ == '__main__':
    try:
        load_env()
    except (OSError, UnicodeError, ValueError):
        sys.exit('Cannot load .env. Check file permissions and single-line ATLAS_* or OPENAI_API_KEY assignments.')
    # Re-enter the Intel launcher with configuration available before its defaults.
    os.environ['RELEASE_ATLAS_ENV_LOADED'] = '1'
    os.execvpe(sys.argv[1], sys.argv[1:], os.environ)
