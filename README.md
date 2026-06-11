# LaborSieve

LaborSieve is a Linux-first command-line job search and reporting tool for operations, infrastructure, data center, SRE, logistics/process, and support-adjacent roles.

Current scope:

- One editable `config.yaml`
- One command to run
- P0/P1 matches printed in the terminal
- Full readable text report written to disk
- Optional CSV, JSON, and static HTML reports
- No dashboard, database, background service, Docker, reverse proxy, or resume parser

## Quick Start

Install the published command on a Linux machine:

```bash
pipx install labor-sieve
```

If `pipx` is not installed:

```bash
# Debian/Ubuntu
sudo apt install pipx

# Fedora
sudo dnf install pipx

# Arch
sudo pacman -S python-pipx

pipx ensurepath
```

Create a working directory, configure preferences, and run a scan:

```bash
mkdir -p ~/labor-sieve
cd ~/labor-sieve
labor-sieve init
nano config.yaml
labor-sieve validate-config
labor-sieve run
```

`labor-sieve init` creates `~/labor-sieve/config.yaml` with the default commented configuration. Edit that file directly; a separate example file is not needed for normal use.

If `labor-sieve` is not found after install, add `~/.local/bin` to the shell path:

```bash
export PATH="$HOME/.local/bin:$PATH"
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

Terminal output prints scan counts and P0/P1 summaries. The text report includes every job, including rejected jobs, grouped by priority bucket.

Jobs are deduplicated before scoring. Exact URL matches are merged first, then normalized company/title/location matches. Reports show the selected source and any merged source references.

## Commands

```bash
labor-sieve init
labor-sieve quickstart
labor-sieve doctor
labor-sieve validate-config
labor-sieve list-options
labor-sieve list-presets
labor-sieve update-presets --index-url PRESET_INDEX_URL
labor-sieve use-preset linux-sre
labor-sieve run
```

`labor-sieve init` creates the editable `config.yaml` file when it does not already exist. The created file contains the default commented settings.

`labor-sieve quickstart` prints first-run setup instructions. Use `labor-sieve quickstart -c /path/to/config.yaml` to print instructions for a specific config location.

`labor-sieve doctor` checks the Python runtime, PyYAML, bundled config/presets, and `config.yaml`.

`labor-sieve validate-config` validates `config.yaml` and prints human-readable errors.

`labor-sieve list-options` prints built-in seniority levels and role families.

`labor-sieve list-presets` prints bundled presets plus downloaded remote presets.

`labor-sieve update-presets` downloads preset updates from a JSON index. Remote preset entries require `sha256` by default; pass `--allow-unverified` only for a trusted temporary source.

`labor-sieve use-preset PRESET` merges a preset into `config.yaml`, validates the result, and writes a `.bak` backup first.

`labor-sieve run` uses enabled sources from `config.yaml`. The sample source is enabled by default so scoring and reports can be tested immediately.

## Configuration

The default configuration prioritizes production operations, infrastructure, Linux/SRE, data center, logistics/process, and implementation-support roles.

Edit these fields in `config.yaml`:

- `seniority`: minimum and maximum target seniority.
- `role_family_weights`: higher values increase priority for a role family.
- `keywords.boost`: terms that improve a match.
- `keywords.penalize`: terms that lower a match.
- `locations`: remote support and acceptable hybrid locations.
- `compensation.minimum_base`: base-pay floor, or `null` to disable it.
- `sources`: enabled job sources.

Role families are config-driven. Built-in families are listed in `labor-sieve list-options`. `role_family_weights` also accepts custom snake_case keys, and the scorer applies those weights to matching `role_family` values from sources and presets.

Bundled presets are included with the installed package and update when the package is upgraded from PyPI. Downloaded presets live in `~/.config/labor-sieve/presets/` by default and override bundled presets with the same name.

Download remote presets from a hosted preset index:

```bash
labor-sieve update-presets --index-url https://example.com/labor-sieve/presets/index.json
```

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

Apply a preset:

```bash
labor-sieve list-presets
labor-sieve use-preset linux-sre
labor-sieve validate-config
```

## Sources

Available sources:

- `sample`: synthetic jobs for scoring/report smoke tests
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

## Manual Runs

Use a working directory that contains `config.yaml` and `output/`:

```bash
mkdir -p ~/labor-sieve
cd ~/labor-sieve
labor-sieve init
nano config.yaml
labor-sieve validate-config
labor-sieve run
less output/latest.txt
```

The config file for this setup is `~/labor-sieve/config.yaml`. Default reports are written under `~/labor-sieve/output/`.

Subsequent runs from the same directory:

```bash
cd ~/labor-sieve
labor-sieve run
```

Update the installed command from PyPI:

```bash
pipx upgrade labor-sieve
```

## Scheduled Runs

LaborSieve can run on a schedule with cron or a systemd user timer. Use one working directory so `config.yaml` and `output/` stay together.

Cron example, every morning at 8:17:

```bash
mkdir -p ~/labor-sieve ~/.local/state/labor-sieve
cd ~/labor-sieve
labor-sieve init
crontab -e
```

Add this crontab entry, changing paths as needed:

```cron
17 8 * * * cd "$HOME/labor-sieve" && "$HOME/.local/bin/labor-sieve" run >> "$HOME/.local/state/labor-sieve/run.log" 2>&1
```

systemd user timer example:

```bash
mkdir -p ~/.config/systemd/user ~/labor-sieve ~/.local/state/labor-sieve
```

Create `~/.config/systemd/user/labor-sieve.service`:

```ini
[Unit]
Description=Run LaborSieve

[Service]
Type=oneshot
WorkingDirectory=%h/labor-sieve
ExecStart=%h/.local/bin/labor-sieve run
StandardOutput=append:%h/.local/state/labor-sieve/run.log
StandardError=append:%h/.local/state/labor-sieve/run.log
```

Create `~/.config/systemd/user/labor-sieve.timer`:

```ini
[Unit]
Description=Run LaborSieve daily

[Timer]
OnCalendar=*-*-* 08:17:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and check it:

```bash
systemctl --user daemon-reload
systemctl --user enable --now labor-sieve.timer
systemctl --user list-timers labor-sieve.timer
systemctl --user start labor-sieve.service
```

Enable lingering for scheduled user timers on systems that support it:

```bash
loginctl enable-linger "$USER"
```

## Distribution

Public installs use the PyPI package through `pipx`. On Debian and Ubuntu systems, plain `pip install --user labor-sieve` can be blocked by the system Python package policy; `pipx` creates an isolated application environment and exposes the `labor-sieve` command.

Install from PyPI:

```bash
pipx install labor-sieve
```

Upgrade from PyPI:

```bash
pipx upgrade labor-sieve
```

The local installer script is for maintainer testing from an accessible checkout or local wheel:

```bash
scripts/install.sh dist/labor_sieve-0.1.0-py3-none-any.whl
```

Installer environment variables:

```bash
LABOR_SIEVE_INSTALL_MODE=venv     # force the dedicated venv path
LABOR_SIEVE_INSTALL_ROOT=...      # override ~/.local/share/labor-sieve
LABOR_SIEVE_BIN_DIR=...           # override ~/.local/bin
```

Build release artifacts:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
scripts/build-release.sh
python -m twine check dist/*
```

The build script writes artifacts to `dist/` and prints SHA-256 checksums.

## Maintainer Notes

Add or tune role families in config and presets first. `role_family_weights` accepts custom snake_case keys, and presets can ship those weights without a code change.

Source inference changes belong in `labor_sieve/sources/normalization.py`. Add tests when changing inferred `seniority`, `role_family`, compensation parsing, URL normalization, or source-specific field mapping.

Bundled preset changes ship in the PyPI package. A remote preset index requires a public HTTPS file host for the preset YAML files:

```bash
python3 scripts/build-preset-index.py --base-url https://example.com/labor-sieve/presets
```

## Local Testing

```bash
python -m compileall .
python -m pytest
```

Install dev dependencies:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```
