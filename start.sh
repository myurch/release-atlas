#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/python ]; then
  echo "Create .venv and install requirements.txt first. See README.md." >&2
  exit 1
fi
exec .venv/bin/python -m backend
