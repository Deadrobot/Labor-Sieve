# LaborSieve

LaborSieve is a Linux-first command-line job search and reporting tool for laid-off operations, infrastructure, data center, SRE, logistics/process, and support-adjacent workers.

The v1 shape is intentionally small:

- One editable `config.yaml`
- One command to run
- P0/P1 matches printed in the terminal
- Full readable text report written to disk
- Optional CSV, JSON, and static HTML reports
- No dashboard, database, background service, Docker, reverse proxy, or resume parser

## Quick Start

Install from a published package or archive:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
pipx install labor-sieve
labor-sieve quickstart
```

Install from a Git URL or self-hosted archive with the installer script:

```bash
curl -fsSL https://example.com/labor-sieve/install.sh | sh -s -- https://example.com/labor-sieve-0.1.0.tar.gz
```

After this project is on GitHub, the same pattern can install directly from the repository:

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR-USER/labor-sieve/main/scripts/install.sh | sh -s -- git+https://github.com/YOUR-USER/labor-sieve.git
```

Developer install from a checkout:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"

labor-sieve init
$EDITOR config.yaml
labor-sieve validate-config
labor-sieve run
```

Reports are written under `output/` by default:

- `output/latest.txt`
- `output/latest.csv`
- `output/latest.json`
- `output/latest.html`

The terminal output only prints scan counts and P0/P1 summaries. The text report includes every job, including rejected jobs, grouped by priority bucket.

Jobs are deduplicated before scoring. Exact URL matches are merged first, then normalized company/title/location matches. Reports show the selected source and any merged source references.

## Commands

```bash
labor-sieve init
labor-sieve quickstart
labor-sieve doctor
labor-sieve validate-config
labor-sieve list-options
labor-sieve list-presets
labor-sieve update-presets --index-url https://example.com/labor-sieve/presets/index.json
labor-sieve use-preset linux-sre
labor-sieve run
```

`labor-sieve init` copies `config.example.yaml` to `config.yaml` when `config.yaml` does not already exist.

`labor-sieve quickstart` prints first-run setup instructions.

`labor-sieve doctor` checks the Python runtime, PyYAML, bundled config/presets, and `config.yaml`.

`labor-sieve validate-config` validates `config.yaml` and prints human-readable errors.

`labor-sieve list-options` prints built-in seniority levels and role families.

`labor-sieve list-presets` prints bundled presets plus downloaded remote presets.

`labor-sieve update-presets` downloads preset updates from a JSON index. Remote preset entries require `sha256` by default; pass `--allow-unverified` only for a trusted temporary source.

`labor-sieve use-preset PRESET` merges a preset into `config.yaml`, validates the result, and writes a `.bak` backup first.

`labor-sieve run` uses enabled sources from `config.yaml`. The sample source is enabled by default so scoring and reports can be tested immediately.

## Configuration

The default tuning is aimed at former production operations, infrastructure, Linux/SRE, data center, logistics/process, and implementation-support workers.

Role families are intentionally config-driven. Built-in families are listed in `labor-sieve list-options`, but `role_family_weights` accepts additional snake_case keys so future source adapters or remote preset updates can classify jobs outside the initial SRE/data center focus without a code change.

Bundled presets live in `presets/` as small YAML files. Downloaded presets live in `~/.config/labor-sieve/presets/` by default and override bundled presets with the same name.

Remote preset indexes use this shape:

```json
{
  "presets": [
    {
      "name": "linux-sre",
      "version": "2026.06.11",
      "url": "https://example.com/labor-sieve/presets/linux-sre.yaml",
      "sha256": "hex-encoded-sha256"
    }
  ]
}
```

Use a preset:

```bash
labor-sieve list-presets
labor-sieve use-preset linux-sre
labor-sieve validate-config
```

## Sources

Four sources exist now:

- `sample`: fake jobs for scoring/report smoke tests
- `local_file`: local `.csv`, `.json`, `.yaml`, or `.yml` exports
- `greenhouse`: public Greenhouse Job Board API boards
- `lever`: public Lever Postings API companies

Example local file config:

```yaml
sources:
  sample:
    enabled: false
  local_file:
    enabled: true
    paths:
      - jobs.csv
  greenhouse:
    enabled: false
    board_tokens: []
    timeout_seconds: 20
  lever:
    enabled: false
    companies: []
    timeout_seconds: 20
    base_url: https://api.lever.co/v0/postings
```

Local file records can include:

```text
title, company, location, remote, hybrid, seniority, role_family,
compensation_base_min, url, description, tags
```

Example Greenhouse config:

```yaml
sources:
  sample:
    enabled: false
  local_file:
    enabled: false
    paths: []
  greenhouse:
    enabled: true
    board_tokens:
      - example-board-token
    timeout_seconds: 20
  lever:
    enabled: false
    companies: []
    timeout_seconds: 20
    base_url: https://api.lever.co/v0/postings
```

Example Lever config:

```yaml
sources:
  sample:
    enabled: false
  local_file:
    enabled: false
    paths: []
  greenhouse:
    enabled: false
    board_tokens: []
    timeout_seconds: 20
  lever:
    enabled: true
    companies:
      - example-company
    timeout_seconds: 20
    base_url: https://api.lever.co/v0/postings
```

## Distribution Notes

The simplest remote install path for Linux users is `pipx`:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
pipx install labor-sieve
labor-sieve quickstart
```

For a self-hosted archive or Git URL:

```bash
curl -fsSL https://example.com/labor-sieve/install.sh | sh -s -- https://example.com/labor-sieve-0.1.0.tar.gz
```

The install script accepts any pip-compatible package spec, including a Git URL, wheel URL, or tarball URL. It uses `pipx` when available. If `pipx` is not installed, it creates a dedicated user venv at `~/.local/share/labor-sieve/venv` and symlinks `labor-sieve` into `~/.local/bin`.

Useful installer environment variables:

```bash
LABOR_SIEVE_INSTALL_MODE=venv     # force the dedicated venv path
LABOR_SIEVE_INSTALL_ROOT=...      # override ~/.local/share/labor-sieve
LABOR_SIEVE_BIN_DIR=...           # override ~/.local/bin
```

Self-hosting release archives from a home server is workable for a small trusted audience. A GitHub release or PyPI package is more standard when you want easier upgrades, checksums, and fewer install-support issues.

Build a release locally:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
scripts/build-release.sh
```

The build script writes artifacts to `dist/` and prints SHA-256 checksums.

## Local Testing

```bash
python -m compileall .
python -m pytest
```

If pytest is not installed:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```
