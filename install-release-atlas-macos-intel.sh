#!/bin/sh
# Release Atlas installer for Intel macOS (POSIX sh; also callable from zsh 5.9).
# Usage: sh install-release-atlas-macos-intel.sh [REPO_DIRECTORY]
#        sh install-release-atlas-macos-intel.sh --fetch [DEST_DIRECTORY]
# Default: use the existing Release Atlas checkout in the current directory.
# --fetch: opt in to downloading the main-branch source archive; when no
#          destination is given, create ./release-atlas.
# Python, dependencies, and uv are installed locally, never system-wide.
# An incompatible existing .venv is PRESERVED by renaming it before replacement.

set -eu
umask 077

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

note() {
    printf '\n==> %s\n' "$*"
}

usage() {
    cat <<'USAGE'
Usage:
  sh install-release-atlas-macos-intel.sh [REPO_DIRECTORY]
  sh install-release-atlas-macos-intel.sh --fetch [DEST_DIRECTORY]

By default, install into the existing Release Atlas checkout in the current
working directory. The script will NOT download or update project source.

  --fetch      Download the main-branch source archive if the destination does
               not already exist. Default destination: ./release-atlas.
  -h, --help   Show this message.

The installer obtains any missing project-local Python/toolchain and Python
dependencies needed to create .venv. An incompatible .venv is backed up
(never deleted) before recreation. No sudo or Homebrew is used.
USAGE
}

FETCH_REPO=0
REPO_ARG=
for arg do
    case "$arg" in
        --fetch)
            [ "$FETCH_REPO" -eq 0 ] || fail 'The --fetch flag was repeated.'
            FETCH_REPO=1
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        -*) fail "Unknown option: $arg (use --help)" ;;
        *)
            [ -z "$REPO_ARG" ] || fail 'Specify at most one repository directory.'
            REPO_ARG=$arg
            ;;
    esac
done

if [ -n "$REPO_ARG" ]; then
    INSTALL_DIR=$REPO_ARG
elif [ "$FETCH_REPO" -eq 1 ]; then
    INSTALL_DIR=./release-atlas
else
    INSTALL_DIR=${RELEASE_ATLAS_HOME:-.}
fi
[ -n "$INSTALL_DIR" ] || fail 'Repository directory cannot be empty.'

[ "$(uname -s)" = Darwin ] || fail 'This installer requires macOS.'
[ "$(uname -m)" = x86_64 ] || fail 'This installer targets 64-bit Intel Macs (x86_64), not Apple Silicon.'

# The published Intel wheels of the pinned scientific dependencies target 10.15+.
OS_VERSION=$(sw_vers -productVersion) || fail 'Could not determine the macOS version.'
OS_MAJOR=$(printf '%s\n' "$OS_VERSION" | cut -d. -f1)
OS_MINOR=$(printf '%s\n' "$OS_VERSION" | cut -d. -f2)
case "$OS_MAJOR:$OS_MINOR" in
    *[!0-9:]* | :* | *:) fail "Unexpected macOS version: $OS_VERSION" ;;
esac
if [ "$OS_MAJOR" -lt 10 ] || { [ "$OS_MAJOR" -eq 10 ] && [ "$OS_MINOR" -lt 15 ]; }; then
    fail 'Release Atlas Python 3.14 wheels require macOS 10.15 or later.'
fi

for cmd in curl tar mktemp mkdir mv cp chmod shasum awk cut uname sw_vers dirname basename grep rm date; do
    command -v "$cmd" >/dev/null 2>&1 || fail "Missing standard macOS utility: $cmd"
done

case "$INSTALL_DIR" in
    /*) ;;
    *) INSTALL_DIR="$(pwd -P)/$INSTALL_DIR" ;;
esac

# The no-fetch path must already exist. Do not create directories, perform
# network operations, or overwrite repository content just to locate a clone.
if [ "$FETCH_REPO" -eq 0 ]; then
    [ -d "$INSTALL_DIR" ] || fail "No checkout at $INSTALL_DIR. Clone it first or use --fetch [DEST_DIRECTORY]."
fi
PARENT_DIR=$(dirname "$INSTALL_DIR")
if [ "$FETCH_REPO" -eq 1 ]; then
    mkdir -p "$PARENT_DIR" || fail "Cannot create parent directory: $PARENT_DIR"
fi
[ -d "$PARENT_DIR" ] || fail "Parent directory does not exist: $PARENT_DIR"
PARENT_DIR=$(CDPATH= cd "$PARENT_DIR" && pwd -P) || fail 'Cannot resolve repository parent.'
INSTALL_DIR="$PARENT_DIR/$(basename "$INSTALL_DIR")"
if [ -d "$INSTALL_DIR" ]; then
    INSTALL_DIR=$(CDPATH= cd "$INSTALL_DIR" && pwd -P) || fail 'Cannot resolve repository directory.'
fi

# The temporary directory is always a new, known directory under the install parent.
TMP_DIR=
cleanup() {
    if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then
        rm -rf "$TMP_DIR"
    fi
}
trap 'cleanup' 0
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# Reuse an existing checkout without overwriting code, credentials, or SQLite data.
if [ -e "$INSTALL_DIR" ]; then
    [ -f "$INSTALL_DIR/AGENTS.md" ] &&
    [ -f "$INSTALL_DIR/requirements.txt" ] &&
    [ -f "$INSTALL_DIR/backend/__main__.py" ] &&
    [ -f "$INSTALL_DIR/dist/release-atlas.html" ] ||
        fail "Directory exists but lacks the required Release Atlas application files: $INSTALL_DIR"
    note "Using existing Release Atlas checkout: $INSTALL_DIR"
else
    [ "$FETCH_REPO" -eq 1 ] || fail "No Release Atlas checkout at $INSTALL_DIR. Clone it first or use --fetch [DEST_DIRECTORY]."
    note 'Fetching Release Atlas source archive from myurch/release-atlas (main branch)'
    TMP_DIR=$(mktemp -d "$PARENT_DIR/.release-atlas-download.XXXXXX") || fail 'Could not create a download directory.'
    curl --fail --location --silent --show-error --retry 3 --connect-timeout 20 --max-time 300 \
        --proto '=https' --tlsv1.2 \
        'https://codeload.github.com/myurch/release-atlas/tar.gz/refs/heads/main' \
        --output "$TMP_DIR/release-atlas.tar.gz" || fail 'Repository download failed.'
    tar -xzf "$TMP_DIR/release-atlas.tar.gz" -C "$TMP_DIR" || fail 'Repository extraction failed.'
    SOURCE_DIR="$TMP_DIR/release-atlas-main"
    [ -f "$SOURCE_DIR/AGENTS.md" ] &&
    [ -f "$SOURCE_DIR/requirements.txt" ] &&
    [ -f "$SOURCE_DIR/backend/__main__.py" ] &&
    [ -f "$SOURCE_DIR/dist/release-atlas.html" ] ||
        fail 'Unexpected archive layout or missing Release Atlas files.'
    mv "$SOURCE_DIR" "$INSTALL_DIR" || fail "Cannot create install directory: $INSTALL_DIR"
    note "Source installed at: $INSTALL_DIR"
fi

cd "$INSTALL_DIR" || fail 'Cannot enter install directory.'

# Keep bootstrap tools out of `git status` for a normal Git clone without
# changing any tracked file or the user's global Git configuration. `.venv`
# and `.atlas` are already ignored by the upstream .gitignore.
if [ -d "$INSTALL_DIR/.git/info" ]; then
    EXCLUDE_FILE="$INSTALL_DIR/.git/info/exclude"
    if [ ! -f "$EXCLUDE_FILE" ]; then
        : > "$EXCLUDE_FILE" || fail 'Cannot create local Git exclusion file.'
    fi
    if ! grep -Fqx '/.tools/' "$EXCLUDE_FILE"; then
        printf '\n# Release Atlas project-local installer binaries and Python cache\n/.tools/\n' >> "$EXCLUDE_FILE" \
            || fail 'Cannot locally Git-ignore .tools directory.'
    fi
    if ! grep -Fqx '/.venv.backup-*/' "$EXCLUDE_FILE"; then
        printf '/.venv.backup-*/\n' >> "$EXCLUDE_FILE" \
            || fail 'Cannot locally Git-ignore virtualenv backups.'
    fi
fi

# uv is a standalone executable. Pin and SHA-256 verify its Intel-macOS release.
# Source: https://github.com/astral-sh/uv/releases/tag/0.12.20
UV_VERSION=0.12.20
UV_SHA256=ac54283d211fd77cdc152b67606dbaf6406ff4ab03f3af4ae99468fa8e887141
UV_DIR="$INSTALL_DIR/.tools/uv"
UV_BIN="$UV_DIR/uv"
mkdir -p "$UV_DIR" "$INSTALL_DIR/.tools/python" "$INSTALL_DIR/.tools/uv-cache"

# A previously installed uv is reused; avoid TLS downloads when possible.
# A pinned host uv can also be copied into .tools (no global changes).
if [ ! -x "$UV_BIN" ]; then
    if command -v uv >/dev/null 2>&1; then
        HOST_UV=$(command -v uv)
        case "$("$HOST_UV" --version 2>/dev/null || :)" in
            "uv $UV_VERSION" | "uv $UV_VERSION "*)
                note "Copying existing uv $UV_VERSION into this checkout (no download)"
                cp "$HOST_UV" "$UV_DIR/uv.new" || fail 'Could not copy the existing uv binary.'
                chmod 755 "$UV_DIR/uv.new"
                mv "$UV_DIR/uv.new" "$UV_BIN"
                ;;
        esac
    fi
fi

if [ ! -x "$UV_BIN" ]; then
    note "Downloading project-local uv $UV_VERSION for Intel macOS"
    [ -n "$TMP_DIR" ] || TMP_DIR=$(mktemp -d "$PARENT_DIR/.release-atlas-download.XXXXXX") || fail 'Cannot create download directory.'
    # Try the official uv release CDN first, then the canonical GitHub assets.
    # Downloads are checksum-verified before anything is executed.
    UV_ARCHIVE=uv-x86_64-apple-darwin.tar.gz
    DOWNLOAD_OK=0
    for UV_URL in \
        "https://releases.astral.sh/github/uv/releases/download/$UV_VERSION/$UV_ARCHIVE" \
        "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/$UV_ARCHIVE"
    do
        if curl --fail --location --silent --show-error --retry 2 --retry-delay 2 \
            --connect-timeout 15 --max-time 180 --proto '=https' --tlsv1.2 \
            "$UV_URL" --output "$TMP_DIR/uv.tar.gz"; then
            DOWNLOAD_OK=1
            break
        fi
        printf 'Download endpoint timed out or failed; trying alternative.\n' >&2
    done
    [ "$DOWNLOAD_OK" -eq 1 ] || fail 'Could not download uv from either official endpoint. Check VPN, proxy, TLS inspection, or network connectivity; existing .venv and source were not changed.'
    ACTUAL_SHA256=$(shasum -a 256 "$TMP_DIR/uv.tar.gz" | awk '{print $1}')
    [ "$ACTUAL_SHA256" = "$UV_SHA256" ] || fail 'uv SHA-256 mismatch: refusing to execute the download.'
    tar -xzf "$TMP_DIR/uv.tar.gz" -C "$TMP_DIR" || fail 'Could not extract verified uv archive.'
    [ -f "$TMP_DIR/uv-x86_64-apple-darwin/uv" ] || fail 'uv executable not found in downloaded archive.'
    cp "$TMP_DIR/uv-x86_64-apple-darwin/uv" "$UV_DIR/uv.new" || fail 'Could not copy uv executable.'
    chmod 755 "$UV_DIR/uv.new"
    mv "$UV_DIR/uv.new" "$UV_BIN"
fi

case "$("$UV_BIN" --version)" in
    "uv $UV_VERSION" | "uv $UV_VERSION "*) ;;
    *) fail "Unexpected uv version; expected $UV_VERSION in $UV_BIN" ;;
esac

# Keep uv-managed Python and its cache in this project; no global executables.
export UV_PYTHON_INSTALL_DIR="$INSTALL_DIR/.tools/python"
export UV_CACHE_DIR="$INSTALL_DIR/.tools/uv-cache"
export UV_PYTHON_INSTALL_BIN=0
export UV_PYTHON_PREFERENCE=only-managed
export UV_NO_CONFIG=1
export UV_LINK_MODE=copy
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV 2>/dev/null || :

note 'Installing isolated CPython 3.14.4 (without modifying system Python)'
"$UV_BIN" python install --no-bin 3.14.4 || fail 'Could not obtain managed Python 3.14.4.'

VENV="$INSTALL_DIR/.venv"
PYTHON="$VENV/bin/python"
# A checkout often already has a venv created by an IDE or a different Python.
# An incompatible venv is not a fatal condition and NEVER gets deleted. Rename
# it first; preserve everything (even a broken environment) for inspection.
VENV_READY=0
if [ -x "$PYTHON" ]; then
    if "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info[:3] == (3, 14, 4) and sys.prefix != sys.base_prefix else 1)' \
        >/dev/null 2>&1; then
        VENV_READY=1
    fi
fi
if [ "$VENV_READY" -eq 1 ]; then
    note 'Reusing existing isolated Python 3.14.4 virtual environment'
else
    if [ -e "$VENV" ] || [ -L "$VENV" ]; then
        note 'Existing .venv is missing, broken, not isolated, or not Python 3.14.4'
        if [ -x "$PYTHON" ]; then
            "$PYTHON" -c 'import sys; print("  Existing Python:", sys.version.split()[0]); print("  Virtual environment:", sys.prefix != sys.base_prefix)' 2>/dev/null || :
        fi
        BACKUP="$INSTALL_DIR/.venv.backup-$(date +%Y%m%d-%H%M%S)-$$"
        BACKUP_N=0
        while [ -e "$BACKUP" ] || [ -L "$BACKUP" ]; do
            BACKUP_N=$((BACKUP_N + 1))
            BACKUP="$INSTALL_DIR/.venv.backup-$(date +%Y%m%d-%H%M%S)-$$-$BACKUP_N"
        done
        mv "$VENV" "$BACKUP" || fail 'Could not back up the existing .venv; no files were deleted.'
        printf '  Preserved old environment at: %s\n' "$BACKUP"
    fi
    note 'Creating a fresh project-local Python 3.14.4 .venv'
    # UV_PYTHON_PREFERENCE=only-managed already requires a uv-managed Python.
    # Do NOT also pass --managed-python: uv rejects the duplicate selection.
    "$UV_BIN" venv --python 3.14.4 "$VENV" \
        || fail 'Virtual environment creation failed; any previous environment is preserved under .venv.backup-*.'
fi
[ -x "$PYTHON" ] || fail 'New .venv has no executable Python.'
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info[:3] == (3, 14, 4) and sys.prefix != sys.base_prefix else 1)' \
    || fail 'New .venv failed Python version/isolation validation.'

note 'Installing exactly the project-pinned Python dependencies into .venv'
"$UV_BIN" pip install --python "$PYTHON" --no-build -r "$INSTALL_DIR/requirements.txt" \
    || fail 'Dependency install failed (prebuilt wheel unavailable or network problem).'
"$UV_BIN" pip check --python "$PYTHON" || fail 'Installed Python dependencies failed verification.'

note 'Checking native packages and backend imports'
"$PYTHON" -c 'import fastapi, networkx, numpy, scipy, sklearn, uvicorn; import backend; print("Dependency imports OK; Python virtualenv OK")' \
    || fail 'Backend import check failed.'

printf '\nInstallation complete.\n'
printf '  Application: %s\n' "$INSTALL_DIR"
printf '  Python:      %s\n' "$PYTHON"
printf '  Local state: %s/.atlas/ (created on first run)\n' "$INSTALL_DIR"
printf '\nTo launch from this repository:\n  cd "%s"\n  sh /path/to/run-release-atlas-macos-intel.sh\n' "$INSTALL_DIR"
printf 'Alternatively, pass this repository path to the launcher.\n'
printf 'No Node.js, Homebrew, sudo, or global Python packages were installed.\n'
