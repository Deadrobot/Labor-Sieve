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

VERSION="$("$PYTHON" - <<'PY'
from labor_sieve import __version__

print(__version__)
PY
)"

echo "Building LaborSieve $VERSION."

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

"$PYTHON" - "$VERSION" <<'PY'
from pathlib import Path
import hashlib
import sys

version = sys.argv[1]
expected = {
    Path(f"dist/labor_sieve-{version}-py3-none-any.whl"),
    Path(f"dist/labor_sieve-{version}.tar.gz"),
}
missing = sorted(expected - set(Path("dist").glob("*")))
if missing:
    print("Build did not create expected release artifacts:", file=sys.stderr)
    for path in missing:
        print(f"  {path}", file=sys.stderr)
    raise SystemExit(1)

for path in sorted(Path("dist").glob("*")):
    if version not in path.name:
        print(f"Unexpected artifact for version {version}: {path}", file=sys.stderr)
        raise SystemExit(1)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"{digest}  {path}")
PY
