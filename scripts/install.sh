#!/usr/bin/env sh
set -eu

PACKAGE_SPEC="${1:-${LABOR_SIEVE_PACKAGE_SPEC:-labor-sieve}}"
INSTALL_ROOT="${LABOR_SIEVE_INSTALL_ROOT:-$HOME/.local/share/labor-sieve}"
BIN_DIR="${LABOR_SIEVE_BIN_DIR:-$HOME/.local/bin}"
VENV_DIR="$INSTALL_ROOT/venv"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required. Install Python 3.10+ and rerun this script." >&2
  exit 1
fi

if ! python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
then
  echo "Python 3.10+ is required." >&2
  exit 1
fi

INSTALL_KIND=""
if [ "${LABOR_SIEVE_INSTALL_MODE:-auto}" != "venv" ] && python3 -m pipx --version >/dev/null 2>&1; then
  python3 -m pipx install --force "$PACKAGE_SPEC"
  INSTALL_KIND="pipx"
elif [ "${LABOR_SIEVE_INSTALL_MODE:-auto}" != "venv" ] && command -v pipx >/dev/null 2>&1; then
  pipx install --force "$PACKAGE_SPEC"
  INSTALL_KIND="pipx"
fi

if [ -z "$INSTALL_KIND" ]; then
  echo "pipx not found; installing into a dedicated user venv at $VENV_DIR."
  mkdir -p "$INSTALL_ROOT" "$BIN_DIR"
  if ! python3 -m venv "$VENV_DIR"; then
    echo "Could not create a Python venv. Install python3-venv or pipx, then rerun this script." >&2
    exit 1
  fi
  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  "$VENV_DIR/bin/python" -m pip install --upgrade "$PACKAGE_SPEC"
  ln -sf "$VENV_DIR/bin/labor-sieve" "$BIN_DIR/labor-sieve"
  INSTALL_KIND="venv"
fi

if command -v labor-sieve >/dev/null 2>&1; then
  COMMAND_HINT="labor-sieve"
else
  COMMAND_HINT="$BIN_DIR/labor-sieve"
fi

WORK_DIR="$HOME/labor-sieve"
CONFIG_FILE="$WORK_DIR/config.yaml"
OUTPUT_DIR="$WORK_DIR/output"
STATE_DIR="$HOME/.local/state/labor-sieve"

cat <<EOF

LaborSieve installed.

Recommended files:
  Working directory: $WORK_DIR
  Config file: $CONFIG_FILE
  Default reports: $OUTPUT_DIR
  Run log: $STATE_DIR/run.log

Create the config file with the default commented settings:
  mkdir -p "$WORK_DIR"
  cd "$WORK_DIR"
  $COMMAND_HINT init -c config.yaml

Then edit and run:
  ${EDITOR:-nano} config.yaml
  $COMMAND_HINT validate-config -c config.yaml
  $COMMAND_HINT run -c config.yaml

Reports:
  $OUTPUT_DIR/latest.txt
  $OUTPUT_DIR/latest.csv
  $OUTPUT_DIR/latest.json
  $OUTPUT_DIR/latest.html

For setup help:
  $COMMAND_HINT quickstart

Install mode:
  $INSTALL_KIND

If 'labor-sieve' is not found, add this to your shell profile:
  export PATH="$BIN_DIR:\$PATH"
EOF
