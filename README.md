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

Create the default config, review the file locations, and run a scan:

```bash
labor-sieve quickstart
# edit ~/labor-sieve/config.yaml with your preferred text editor
labor-sieve validate-config
labor-sieve run
```

`labor-sieve quickstart` creates `~/labor-sieve/config.yaml` with the default commented configuration when the file is missing. Edit that file directly; a separate example file is not needed for normal use. Default reports are written under `~/labor-sieve/output/`.

If `labor-sieve` is not found after install, add `~/.local/bin` to the shell path:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Developer install from a checkout:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"

labor-sieve quickstart -c config.yaml
# edit config.yaml with your preferred text editor
labor-sieve validate-config -c config.yaml
labor-sieve run -c config.yaml
```

Reports are written under `output/` beside the config file by default:

- `output/latest.txt`
- `output/latest.csv`
- `output/latest.json`
- `output/latest.html`

Run output prints source progress, scan counts, and P0/P1 summaries. The text report includes every job, including rejected jobs, grouped by priority bucket.

Jobs are deduplicated before scoring. Exact URL matches are merged first, then normalized company/title/location matches. Reports show the selected source and any merged source references.

## Commands

```bash
labor-sieve init
labor-sieve quickstart
labor-sieve doctor
labor-sieve validate-config
labor-sieve config-upgrade
labor-sieve list-options
labor-sieve list-presets
labor-sieve update-presets --index-url PRESET_INDEX_URL
labor-sieve use-preset linux-sre
labor-sieve run
labor-sieve uninstall-data
```

`labor-sieve init` creates the editable config file when it does not already exist. By default it uses `./config.yaml` if that file is already present, otherwise `~/labor-sieve/config.yaml`.

`labor-sieve init --force` backs up an existing config to `config.yaml.bak` and replaces it with the packaged default config.

`labor-sieve quickstart` creates `~/labor-sieve/config.yaml` when the file is missing, then prints setup instructions. Use `labor-sieve quickstart -c /path/to/config.yaml` to create or print instructions for a specific config location.

`labor-sieve quickstart --reset-config` backs up the selected config and replaces it with the packaged default config before printing setup instructions.

`labor-sieve doctor` checks the Python runtime, PyYAML, bundled config/presets, and `config.yaml`.

`labor-sieve validate-config` adds missing default settings when needed, validates `config.yaml`, and prints human-readable errors.

`labor-sieve config-upgrade` backs up `config.yaml` and adds missing default settings from the installed package without changing existing values.

`labor-sieve list-options` prints built-in seniority levels and role families.

`labor-sieve list-presets` prints bundled presets plus downloaded remote presets.

`labor-sieve update-presets` downloads preset updates from a JSON index. Remote preset entries require `sha256` by default; pass `--allow-unverified` only for a trusted temporary source.

`labor-sieve use-preset PRESET` merges a preset into `config.yaml`, validates the result, and writes a `.bak` backup first.

`labor-sieve run` adds missing default settings when needed, then uses enabled sources from the selected config file. The default config disables sample data, enables RemoteOK for broad discovery, and enables public ATS starter company lists.

`labor-sieve uninstall-data` prints user data paths. `labor-sieve uninstall-data --yes` removes the default config/report directory, downloaded presets, and run logs before uninstalling the command.

## Configuration

The default configuration prioritizes production operations, infrastructure, Linux/SRE, data center, logistics/process, and implementation-support roles around Richmond, VA. Broad public and configured ATS sources are enabled by default, so the first real run can take several minutes.

Edit these fields in `config.yaml`:

- `seniority`: minimum and maximum target seniority.
- `role_family_weights`: higher values increase priority for a role family.
- `keywords.boost`: terms that improve a match.
- `keywords.penalize`: terms that lower a match.
- `locations`: remote support, local-region notes, and accepted hybrid/on-site locations.
- `compensation.minimum_base`: base-pay floor, or `null` to disable it.
- `exclusions`: companies, URLs, or source IDs to omit from future reports.
- `output.terminal_p0_limit` and `output.terminal_p1_limit`: terminal summary limits.
- `sources`: enabled job sources.

Role families are config-driven. Built-in families are listed in `labor-sieve list-options`. `role_family_weights` also accepts custom snake_case keys, and the scorer applies those weights to matching `role_family` values from sources and presets.

Bundled presets are included with the installed package and update when the package is upgraded from PyPI. Downloaded presets live in `~/.config/labor-sieve/presets/` by default and override bundled presets with the same name.

User configs are preserved across package upgrades. When a newer LaborSieve release adds config settings, `quickstart`, `validate-config`, and `run` add missing defaults automatically and write a `.bak` backup first. Existing values are left unchanged. To run this explicitly:

```bash
labor-sieve config-upgrade
```

### Location Settings

The default config is centered on Richmond, VA with a 40-mile local-region note:

```yaml
locations:
  remote: true
  local_region:
    center: Richmond, VA
    radius_miles: 40
  accepted_locations:
    - Richmond, VA
    - Henrico, VA
    - Glen Allen, VA
  accepted_remote_locations:
    - United States
    - USA
    - North America
```

`local_region.center` and `radius_miles` describe the intended search area. LaborSieve does not geocode locations; it matches job-posting location text against `accepted_locations`. To use another city, change the center/radius note and replace `accepted_locations` with nearby city, county, or metro strings that should count as local.

Hybrid and on-site roles outside `accepted_locations` are capped below P1. Remote roles are accepted when their location is generic remote or matches `accepted_remote_locations`; remote roles restricted to other geographies are also capped below P1.

### Exclusions

Use `exclusions` to remove companies or specific postings from future reports:

```yaml
exclusions:
  companies:
    - Example Company
  urls:
    - https://example.invalid/jobs/job-to-hide
  source_ids:
    - ashby:abc123
```

Company names are matched case-insensitively. URLs are normalized before matching. Source IDs can be copied from the text report; use either the raw source ID or `source:source_id`.

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
labor-sieve use-preset linux-sre -c ~/labor-sieve/config.yaml
labor-sieve validate-config -c ~/labor-sieve/config.yaml
```

## Sources

Available sources:

- `sample`: synthetic jobs for scoring/report smoke tests
- `local_file`: local `.csv`, `.json`, `.yaml`, or `.yml` exports
- `remoteok`: broad public RemoteOK API listings across many companies
- `arbeitnow`: broad public Arbeitnow API listings, disabled by default because it is noisier for a US-centered search
- `greenhouse`: public Greenhouse Job Board API boards
- `lever`: public Lever Postings API companies
- `ashby`: public Ashby job board organizations
- `workday`: public Workday candidate experience sites

The default config disables sample data, enables RemoteOK, disables Arbeitnow, and enables starter lists for Greenhouse, Lever, Ashby, and Workday. `local_file` remains disabled until file paths are added.

Example local file config:

```yaml
sources:
  sample:
    enabled: false
  local_file:
    enabled: true
    paths:
      - jobs.csv
  remoteok:
    enabled: false
    timeout_seconds: 20
    max_jobs: 250
    base_url: https://remoteok.com/api
  arbeitnow:
    enabled: false
    timeout_seconds: 20
    max_pages: 1
    max_jobs: 100
    base_url: https://www.arbeitnow.com/api/job-board-api
  greenhouse:
    enabled: false
    board_tokens: []
    timeout_seconds: 20
  lever:
    enabled: false
    companies: []
    timeout_seconds: 20
    base_url: https://api.lever.co/v0/postings
  ashby:
    enabled: false
    organizations: []
    timeout_seconds: 30
    base_url: https://api.ashbyhq.com/posting-api/job-board
  workday:
    enabled: false
    sites: []
    timeout_seconds: 20
    page_size: 20
    max_jobs_per_site: 100
```

Local file records can include:

```text
title, company, location, remote, hybrid, seniority, role_family,
compensation_base_min, url, description, tags
```

The focused examples below omit `remoteok` and `arbeitnow` for brevity. Leave, disable, or edit those sections independently.

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
  ashby:
    enabled: false
    organizations: []
    timeout_seconds: 30
    base_url: https://api.ashbyhq.com/posting-api/job-board
  workday:
    enabled: false
    sites: []
    timeout_seconds: 20
    page_size: 20
    max_jobs_per_site: 100
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
  ashby:
    enabled: false
    organizations: []
    timeout_seconds: 30
    base_url: https://api.ashbyhq.com/posting-api/job-board
  workday:
    enabled: false
    sites: []
    timeout_seconds: 20
    page_size: 20
    max_jobs_per_site: 100
```

Example Ashby config:

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
    enabled: false
    companies: []
    timeout_seconds: 20
    base_url: https://api.lever.co/v0/postings
  ashby:
    enabled: true
    organizations:
      - example-organization
    timeout_seconds: 30
    base_url: https://api.ashbyhq.com/posting-api/job-board
  workday:
    enabled: false
    sites: []
    timeout_seconds: 20
    page_size: 20
    max_jobs_per_site: 100
```

Example Workday config:

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
    enabled: false
    companies: []
    timeout_seconds: 20
    base_url: https://api.lever.co/v0/postings
  ashby:
    enabled: false
    organizations: []
    timeout_seconds: 30
    base_url: https://api.ashbyhq.com/posting-api/job-board
  workday:
    enabled: true
    sites:
      - company: NVIDIA
        url: https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite
      - company: Equinix
        url: https://equinix.wd1.myworkdayjobs.com/External
      - company: Micron
        url: https://micron.wd1.myworkdayjobs.com/External
    timeout_seconds: 20
    page_size: 20
    max_jobs_per_site: 100
```

## Manual Runs

Create the default config and run from any directory:

```bash
labor-sieve quickstart
# edit ~/labor-sieve/config.yaml with your preferred text editor
labor-sieve validate-config
labor-sieve run
less ~/labor-sieve/output/latest.txt
```

The config file for this setup is `~/labor-sieve/config.yaml`. Default reports are written under `~/labor-sieve/output/`.

Review the enabled source lists before scheduled use. Broad sources are under `sources.remoteok` and `sources.arbeitnow`. Workday entries are under `sources.workday.sites`; Greenhouse, Lever, and Ashby entries are under their matching source sections.

Subsequent runs:

```bash
labor-sieve run
```

`labor-sieve run` uses `./config.yaml` if one exists, otherwise `~/labor-sieve/config.yaml`. While sources are fetching, it prints simple progress with elapsed time.

Update the installed command from PyPI:

```bash
pipx upgrade labor-sieve
```

## Uninstall

`pipx uninstall labor-sieve` removes the installed command, but it does not remove `~/labor-sieve/config.yaml` or generated reports.

To remove user data and then uninstall:

```bash
labor-sieve uninstall-data --yes
pipx uninstall labor-sieve
```

## Scheduled Runs

LaborSieve can run on a schedule with cron or a systemd user timer. Use the same config path each time so reports stay beside that config.

Cron example, every morning at 8:17:

```bash
mkdir -p ~/.local/state/labor-sieve
labor-sieve quickstart
crontab -e
```

Add this crontab entry, changing paths as needed:

```cron
17 8 * * * "$HOME/.local/bin/labor-sieve" run -c "$HOME/labor-sieve/config.yaml" >> "$HOME/.local/state/labor-sieve/run.log" 2>&1
```

systemd user timer example:

```bash
mkdir -p ~/.config/systemd/user ~/.local/state/labor-sieve
labor-sieve quickstart
```

Create `~/.config/systemd/user/labor-sieve.service`:

```ini
[Unit]
Description=Run LaborSieve

[Service]
Type=oneshot
ExecStart=%h/.local/bin/labor-sieve run -c %h/labor-sieve/config.yaml
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
