#!/bin/sh
# Release Atlas launcher for Intel macOS (POSIX sh; also callable from zsh 5.9).
# Usage: sh run-release-atlas-macos-intel.sh [REPO_DIRECTORY]
# Default: existing Release Atlas checkout in the current directory.
# Optional: RELEASE_ATLAS_NO_BROWSER=1 prevents automatic browser opening.
# Optional: ATLAS_PORT=8766 changes the port (the host remains loopback-only).

set -eu

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

if [ "${1:-}" = '-h' ] || [ "${1:-}" = '--help' ]; then
    printf 'Usage: sh run-release-atlas-macos-intel.sh [REPO_DIRECTORY]\n'
    printf 'Default: run from the existing Release Atlas checkout in the current directory.\n'
    exit 0
fi
[ "$#" -le 1 ] || fail 'Usage: sh run-release-atlas-macos-intel.sh [REPO_DIRECTORY]'
[ "$(uname -s)" = Darwin ] || fail 'This launcher requires macOS.'
[ "$(uname -m)" = x86_64 ] || fail 'This launcher targets Intel Macs (x86_64).'

if [ "$#" -eq 1 ]; then
    INSTALL_DIR=$1
else
    INSTALL_DIR=${RELEASE_ATLAS_HOME:-.}
fi
[ -d "$INSTALL_DIR" ] || fail "Release Atlas is not installed at: $INSTALL_DIR. Run the installer first."
INSTALL_DIR=$(CDPATH= cd "$INSTALL_DIR" && pwd -P) || fail 'Cannot resolve installation path.'
[ -f "$INSTALL_DIR/backend/__main__.py" ] || fail 'Not a Release Atlas installation.'
[ -f "$INSTALL_DIR/dist/release-atlas.html" ] || fail 'Bundled frontend HTML is missing.'
PYTHON="$INSTALL_DIR/.venv/bin/python"
[ -x "$PYTHON" ] || fail 'Virtual environment missing. Run the installer first.'

export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV 2>/dev/null || :
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) and sys.prefix != sys.base_prefix else 1)' \
    || fail 'The .venv interpreter is not an isolated Python 3.14 environment. Rerun the installer; it will back up and replace the incompatible environment.'

# Parse private configuration without sourcing shell code or printing credentials.
cd "$INSTALL_DIR"
if [ "${RELEASE_ATLAS_ENV_LOADED:-0}" != 1 ]; then
    exec "$PYTHON" -m backend.config sh "$INSTALL_DIR/run-release-atlas-macos-intel.sh" "$INSTALL_DIR"
fi
unset RELEASE_ATLAS_ENV_LOADED

# Keep the service on the loopback interface per the repository's security guidance.
ATLAS_HOST=127.0.0.1
ATLAS_PORT=${ATLAS_PORT:-8765}
case "$ATLAS_PORT" in
    '' | *[!0-9]*) fail 'ATLAS_PORT must be a number from 1 to 65535.' ;;
esac
[ "$ATLAS_PORT" -ge 1 ] && [ "$ATLAS_PORT" -le 65535 ] || fail 'ATLAS_PORT must be between 1 and 65535.'
ATLAS_ORIGINS="http://127.0.0.1:$ATLAS_PORT,http://localhost:$ATLAS_PORT"
export ATLAS_HOST ATLAS_PORT ATLAS_ORIGINS

# Any Python subprocesses inherit the venv's executable search path.
PATH="$INSTALL_DIR/.venv/bin:$PATH"
export PATH
cd "$INSTALL_DIR"

URL="http://127.0.0.1:$ATLAS_PORT"
printf '\nRelease Atlas starting at %s\n' "$URL"
if [ "${ATLAS_AUTH_ENABLED:-0}" = 1 ]; then
    if [ -n "${ATLAS_ACCESS_CODE:-}" ]; then
        printf 'Sign in with a display name and the configured ATLAS_ACCESS_CODE.\n'
    else
        printf 'Local access code: %s/access-code\n' "${ATLAS_DATA_DIR:-$INSTALL_DIR/.atlas}"
        printf 'After startup, read that file in another Terminal to sign in.\n'
    fi
else
    printf 'Sign-in is disabled. The workspace opens directly.\n'
    printf 'Set ATLAS_AUTH_ENABLED=1 and restart to require sign-in.\n'
fi
printf 'Press Ctrl+C to stop the server; workspace data is retained.\n\n'

# Open a browser only once HTTP responds, without backgrounding the server.
# This helper is optional and never affects the server's lifetime or exit status.
if [ "${RELEASE_ATLAS_NO_BROWSER:-0}" != 1 ] && command -v open >/dev/null 2>&1 && command -v curl >/dev/null 2>&1; then
    (
        ATTEMPT=0
        while [ "$ATTEMPT" -lt 30 ]; do
            if curl --fail --silent --max-time 2 --output /dev/null "$URL/"; then
                open "$URL" || :
                exit 0
            fi
            ATTEMPT=$((ATTEMPT + 1))
            sleep 1
        done
    ) >/dev/null 2>&1 &
fi

ATLAS_LLM_KIND=${ATLAS_LLM_KIND:-openai}
case "$ATLAS_LLM_KIND" in
    openai)
        ATLAS_LLM_BASE=${ATLAS_LLM_BASE:-https://api.openai.com/v1}
        ATLAS_LLM_MODEL=${ATLAS_LLM_MODEL:-gpt-6-luna}
        if [ -z "${ATLAS_LLM_KEY:-${OPENAI_API_KEY:-}}" ] && [ -t 0 ]; then
            printf 'OpenAI API key (hidden; used only for this run): '
            trap 'stty echo' 0
            trap 'exit 130' INT
            trap 'exit 143' HUP TERM
            stty -echo
            IFS= read -r OPENAI_API_KEY || OPENAI_API_KEY=
            stty echo
            trap - 0 INT HUP TERM
            printf '\n'
            export OPENAI_API_KEY
        fi
        ;;
    ollama|compatible)
        if [ "$ATLAS_LLM_KIND" = ollama ]; then
            ATLAS_LLM_BASE=${ATLAS_LLM_BASE:-http://127.0.0.1:11434}
        else
            ATLAS_LLM_BASE=${ATLAS_LLM_BASE:-http://127.0.0.1:11434/v1}
        fi
        ATLAS_LLM_MODEL=${ATLAS_LLM_MODEL:-gemma4:12b}
        ;;
    *) fail 'ATLAS_LLM_KIND must be openai, ollama or compatible.' ;;
esac

export ATLAS_LLM_KIND ATLAS_LLM_BASE ATLAS_LLM_MODEL

exec "$PYTHON" -m backend
