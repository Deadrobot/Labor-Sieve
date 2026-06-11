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

Install from GitHub on a Linux machine:

```bash
curl -fsSL https://raw.githubusercontent.com/Deadrobot/Labor-Sieve/main/scripts/install.sh \
  | sh -s -- git+https://github.com/Deadrobot/Labor-Sieve.git
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
labor-sieve update-presets --index-url https://raw.githubusercontent.com/Deadrobot/Labor-Sieve/main/presets/index.json
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

Bundled presets live in `presets/`. Downloaded presets live in `~/.config/labor-sieve/presets/` by default and override bundled presets with the same name.

Update presets from this repository:

```bash
labor-sieve update-presets --index-url https://raw.githubusercontent.com/Deadrobot/Labor-Sieve/main/presets/index.json
```

Remote preset indexes use this shape:

```json
{
  "presets": [
    {
      "name": "linux-sre",
      "version": "2026.06.11",
      "url": "https://raw.githubusercontent.com/Deadrobot/Labor-Sieve/main/presets/linux-sre.yaml",
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

Subsequent runs from the same directory:

```bash
cd ~/labor-sieve
labor-sieve run
```

Update the installed command from GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/Deadrobot/Labor-Sieve/main/scripts/install.sh \
  | sh -s -- git+https://github.com/Deadrobot/Labor-Sieve.git
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

The installer accepts any pip-compatible package spec, including a Git URL, wheel path, wheel URL, or source archive URL. It uses `pipx` if pipx is installed. Otherwise, it creates a dedicated user venv at `~/.local/share/labor-sieve/venv` and symlinks `labor-sieve` into `~/.local/bin`.

Install from GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/Deadrobot/Labor-Sieve/main/scripts/install.sh \
  | sh -s -- git+https://github.com/Deadrobot/Labor-Sieve.git
```

Install from a local wheel:

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
python3 scripts/build-preset-index.py
scripts/build-release.sh
```

The build script writes artifacts to `dist/` and prints SHA-256 checksums.

## Maintainer Notes

Add or tune role families in config and presets first. `role_family_weights` accepts custom snake_case keys, and presets can ship those weights without a code change.

Source inference changes belong in `labor_sieve/sources/normalization.py`. Add tests when changing inferred `seniority`, `role_family`, compensation parsing, URL normalization, or source-specific field mapping.

Regenerate the remote preset index when bundled presets change:

```bash
python3 scripts/build-preset-index.py
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
