# Release Checklist

Use this checklist to build and verify release artifacts.

## Build

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
python scripts/build-preset-index.py
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

## Install Paths

GitHub install:

```bash
pipx install git+https://github.com/Deadrobot/Labor-Sieve.git
```

GitHub install through the project installer:

```bash
curl -fsSL https://raw.githubusercontent.com/Deadrobot/Labor-Sieve/main/scripts/install.sh \
  | sh -s -- git+https://github.com/Deadrobot/Labor-Sieve.git
```

Local wheel install:

```bash
pipx install dist/labor_sieve-0.1.0-py3-none-any.whl
```

Local wheel install through the project installer:

```bash
scripts/install.sh dist/labor_sieve-0.1.0-py3-none-any.whl
```

The installer uses `pipx` if pipx is installed. Otherwise, it installs into a dedicated venv under `~/.local/share/labor-sieve/venv` and links `labor-sieve` into `~/.local/bin`.

## Preset Updates

Remote preset updates use bundled preset files plus `presets/index.json`. Regenerate the index after files under `presets/*.yaml` change:

```bash
python scripts/build-preset-index.py
```

Users can update downloaded presets from GitHub:

```bash
labor-sieve update-presets --index-url https://raw.githubusercontent.com/Deadrobot/Labor-Sieve/main/presets/index.json
```

Role families can be added in presets by adding a snake_case key under `role_family_weights`. Source adapter inference changes belong in `labor_sieve/sources/normalization.py`.

## Scheduling Smoke Test

Verify the scheduled-run working directory command from a temporary directory:

```bash
mkdir -p /tmp/labor-sieve-schedule-test
cd /tmp/labor-sieve-schedule-test
labor-sieve init
labor-sieve validate-config
labor-sieve run
```

## Notes

- Regenerate `presets/index.json` when bundled presets change.
- Update `CHANGELOG.md` for each release artifact set.
