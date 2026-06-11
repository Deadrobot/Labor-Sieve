# Release Checklist

Use this checklist when publishing a new LaborSieve package version.

## Version

Pick the next version before building. PyPI package versions are immutable; never reuse a version after it has been uploaded.

Update both files:

- `pyproject.toml`: `[project] version`
- `labor_sieve/__init__.py`: `__version__`

Move completed entries from `CHANGELOG.md` `Unreleased` into a versioned section.

## Build

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
scripts/build-release.sh
python -m twine check dist/*
```

Artifacts are written to `dist/`.
The build script uses the active dev environment with `python -m build --no-isolation`, so install `.[dev]` first.

## Verify

```bash
python -m compileall labor_sieve tests
python -m pytest

python -m venv /tmp/labor-sieve-release-test
/tmp/labor-sieve-release-test/bin/python -m pip install dist/labor_sieve-0.1.1-py3-none-any.whl
/tmp/labor-sieve-release-test/bin/labor-sieve --version
/tmp/labor-sieve-release-test/bin/labor-sieve quickstart
/tmp/labor-sieve-release-test/bin/labor-sieve init -c /tmp/labor-sieve-config.yaml
/tmp/labor-sieve-release-test/bin/labor-sieve validate-config -c /tmp/labor-sieve-config.yaml
/tmp/labor-sieve-release-test/bin/labor-sieve run -c /tmp/labor-sieve-config.yaml
```

Replace `0.1.1` with the version being released.

## Install Paths

Public install from PyPI:

```bash
pipx install labor-sieve
```

Public upgrade from PyPI:

```bash
pipx upgrade labor-sieve
```

Local wheel install for release testing:

```bash
pipx install dist/labor_sieve-0.1.1-py3-none-any.whl
```

Local wheel install through the project installer:

```bash
scripts/install.sh dist/labor_sieve-0.1.1-py3-none-any.whl
```

The repository installer script is for accessible checkouts and local artifacts. Public install instructions should use PyPI and `pipx`.

## Preset Updates

Bundled preset changes ship through the PyPI package release.

`labor-sieve update-presets` also supports a remote preset index, but the index and preset YAML files must be hosted at public HTTPS URLs. Do not publish preset indexes that point to private repository raw URLs.

Regenerate an index only when a public preset host is available:

```bash
python scripts/build-preset-index.py --base-url https://example.com/labor-sieve/presets
```

Role families can be added in presets by adding a snake_case key under `role_family_weights`. Source adapter inference changes belong in `labor_sieve/sources/normalization.py`.

## Scheduling Smoke Test

Verify the scheduled-run command from a temporary config path:

```bash
labor-sieve quickstart -c /tmp/labor-sieve-schedule-test/config.yaml
labor-sieve validate-config -c /tmp/labor-sieve-schedule-test/config.yaml
labor-sieve run -c /tmp/labor-sieve-schedule-test/config.yaml
```

## Publish

Publish from a clean working tree after verification passes. Replace `0.1.1` with the release version.

```bash
git status --short
git add .
git commit -m "Prepare LaborSieve 0.1.1 release"
git tag v0.1.1
git push origin main
git push origin v0.1.1
python -m twine upload dist/*
```

After PyPI upload, verify the published package from a fresh environment:

```bash
python -m venv /tmp/labor-sieve-pypi-test
/tmp/labor-sieve-pypi-test/bin/python -m pip install --no-cache-dir labor-sieve==0.1.1
/tmp/labor-sieve-pypi-test/bin/labor-sieve --version
/tmp/labor-sieve-pypi-test/bin/labor-sieve quickstart
```

## Notes

- Git updates alone do not update the public package. Public users receive code changes after a new version is uploaded to PyPI.
- `pipx upgrade labor-sieve` updates an installed command to the newest PyPI release.
- If files change after building `dist/`, rerun `scripts/build-release.sh` before uploading.
