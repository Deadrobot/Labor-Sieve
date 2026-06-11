# Release Checklist

Use this for private pilot releases before publishing to PyPI.

## Build

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
scripts/build-release.sh
```

Artifacts are written to `dist/`.
The build script uses the active dev environment with `python -m build --no-isolation`, so install `.[dev]` first.

## Verify

```bash
python -m compileall .
python -m pytest

python -m venv /tmp/labor-sieve-release-test
/tmp/labor-sieve-release-test/bin/python -m pip install dist/labor_sieve-0.1.0-py3-none-any.whl
/tmp/labor-sieve-release-test/bin/labor-sieve --version
/tmp/labor-sieve-release-test/bin/labor-sieve quickstart
/tmp/labor-sieve-release-test/bin/labor-sieve init -c /tmp/labor-sieve-config.yaml
/tmp/labor-sieve-release-test/bin/labor-sieve validate-config -c /tmp/labor-sieve-config.yaml
```

## Publish Options

GitHub install:

```bash
pipx install git+https://github.com/YOUR-USER/labor-sieve.git
```

GitHub install through the project installer:

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR-USER/labor-sieve/main/scripts/install.sh \
  | sh -s -- git+https://github.com/YOUR-USER/labor-sieve.git
```

GitHub Release or self-hosted wheel install:

```bash
pipx install https://example.com/labor-sieve/labor_sieve-0.1.0-py3-none-any.whl
```

Install script:

```bash
curl -fsSL https://example.com/labor-sieve/install.sh \
  | sh -s -- https://example.com/labor-sieve/labor_sieve-0.1.0-py3-none-any.whl
```

The installer uses `pipx` when available. Without `pipx`, it installs into a dedicated venv under `~/.local/share/labor-sieve/venv` and links `labor-sieve` into `~/.local/bin`.

## Notes

- Keep GitHub releases private or limited until pilot feedback is incorporated.
- Prefer GitHub Releases or a static host over ad hoc file sharing so checksums and rollback are clear.
- Update `CHANGELOG.md` before every release.
