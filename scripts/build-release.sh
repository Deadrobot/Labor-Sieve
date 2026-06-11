#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."

if [ -z "${PYTHON:-}" ]; then
  if [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
  else
    PYTHON="python3"
  fi
fi

rm -rf build dist *.egg-info
find . -type d -name __pycache__ -prune -exec rm -rf {} +

"$PYTHON" -m compileall labor_sieve tests

if "$PYTHON" -m pytest --version >/dev/null 2>&1; then
  "$PYTHON" -m pytest
else
  echo "pytest is not installed; skipping tests. Install dev extras with: python -m pip install -e \".[dev]\"" >&2
fi

if ! "$PYTHON" -m build --version >/dev/null 2>&1; then
  echo "build is not installed. Install dev extras with: python -m pip install -e \".[dev]\"" >&2
  exit 1
fi

"$PYTHON" -m build --no-isolation

"$PYTHON" - <<'PY'
from pathlib import Path
import hashlib

for path in sorted(Path("dist").glob("*")):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"{digest}  {path}")
PY
