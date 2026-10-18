#!/bin/sh
# Optional local semantic encoder. Main Python and saved workspaces are untouched.
set -eu
umask 077
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
[ -x .tools/uv/uv ] || { printf '%s\n' 'Run the Intel Mac installer first to obtain project-local uv.' >&2; exit 1; }
mkdir -p .tools/semantic
export UV_PYTHON_BIN_DIR="$ROOT/.tools/semantic/bin"
export UV_PYTHON_INSTALL_DIR="$ROOT/.tools/semantic/python"
export UV_CACHE_DIR="${TMPDIR:-/tmp}/release-atlas-semantic-uv"
.tools/uv/uv python install 3.11
[ -x .tools/semantic/venv/bin/python ] || .tools/uv/uv venv --python 3.11 .tools/semantic/venv
.tools/uv/uv pip install --python .tools/semantic/venv/bin/python -r requirements-semantic.txt
.venv/bin/python tools/setup_semantic.py
printf '%s\n' 'Semantic encoder installed. Restart Release Atlas. No source text was sent to a remote service.'
