# LaborSieve

LaborSieve is a Linux-first command-line job search and reporting tool for operations, infrastructure, data center, SRE, logistics/process, and support-adjacent roles.

It is intentionally small:

- One editable `config.yaml`
- One command to run after setup
- Terminal summary for P0/P1 matches
- Full reports written to disk
- Text report first, with optional CSV, JSON, and static HTML
- No dashboard, database, background service, Docker, reverse proxy, or resume parser

## Install And First Run

LaborSieve requires Linux or another Unix-like shell, Python 3.10 or newer, and `pipx`.

Check Python:

```bash
python3 --version
```

If Python or `pipx` is missing, install them with your system package manager. Common Linux examples:

```bash
# Debian/Ubuntu
sudo apt update
sudo apt install python3 python3-venv pipx

# Fedora
sudo dnf install python3 pipx

# Arch
sudo pacman -S python python-pipx

pipx ensurepath
```

Open a new terminal if `pipx ensurepath` says the shell path changed.

References:

- [Python on Unix platforms](https://docs.python.org/3/using/unix.html)
- [pipx installation guide](https://pipx.pypa.io/stable/installation/)
- [LaborSieve on PyPI](https://pypi.org/project/labor-sieve/)

Install LaborSieve:

```bash
pipx install labor-sieve
```

Create the default config, review the file locations, and run:

```bash
labor-sieve quickstart
# open ~/labor-sieve/config.yaml in your preferred text editor
labor-sieve validate-config
labor-sieve run
```

`labor-sieve quickstart` creates `~/labor-sieve/config.yaml` when the file is missing. That file contains the default commented configuration; a separate example file is not needed for normal use.

Default reports are written under `~/labor-sieve/output/`:

- `latest.txt`
- `latest.csv`
- `latest.json`
- `latest.html`

If `labor-sieve` is not found after install:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## What To Edit First

Open `~/labor-sieve/config.yaml` and review:

- `locations`: remote support, Richmond-area defaults, accepted hybrid/on-site locations, and accepted remote regions.
- `seniority`: minimum and maximum seniority.
- `compensation`: fallback and seniority-specific compensation floors.
- `keywords.boost` and `keywords.penalize`: terms that raise or lower a posting's score.
- `language_requirements`: language requirements to accept, boost, or penalize.
- `role_family_weights`: how strongly each role family should rank.
- `exclusions`: companies, URLs, or source IDs to hide from future reports.
- `sources`: enabled job sources and configured ATS company lists.

The default config is centered on Richmond, VA with a 40-mile local-region note. LaborSieve does not geocode. Local matching is controlled by the strings in `locations.accepted_locations`, so update that list when using a different city or metro area.

## Running

Run from any directory:

```bash
labor-sieve run
```

`labor-sieve run` uses `./config.yaml` if one exists, otherwise `~/labor-sieve/config.yaml`.

While sources are fetching, LaborSieve prints source progress and elapsed time. A live run can take several minutes, especially when Workday sites are enabled.

Read the primary text report:

```bash
less ~/labor-sieve/output/latest.txt
```

Open the static HTML report in a browser. On desktop Linux, if `xdg-open` is available:

```bash
xdg-open ~/labor-sieve/output/latest.html
```

The HTML report is local-only. It has collapsible priority buckets and job entries, plus browser-local tracking buttons for interested, applied, rejected, and hidden postings.

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

`labor-sieve quickstart` creates `~/labor-sieve/config.yaml` when the file is missing, then prints setup instructions. Use `labor-sieve quickstart -c /path/to/config.yaml` for a specific config location.

`labor-sieve quickstart --reset-config` backs up the selected config and replaces it with the packaged default config.

`labor-sieve validate-config` adds missing default settings when needed, validates `config.yaml`, and prints human-readable errors.

`labor-sieve config-upgrade` backs up `config.yaml` and adds missing default settings from the installed package without changing existing values.

`labor-sieve doctor` checks the Python runtime, PyYAML, bundled config/presets, and selected config file.

`labor-sieve list-options` prints built-in seniority levels and role families.

`labor-sieve list-presets` prints bundled presets plus downloaded remote presets.

`labor-sieve update-presets` downloads preset updates from a JSON index. Remote preset entries require `sha256` by default; pass `--allow-unverified` only for a trusted temporary source.

`labor-sieve use-preset PRESET` merges a preset into `config.yaml`, validates the result, and writes a `.bak` backup first.

`labor-sieve run` adds missing default settings when needed, then uses enabled sources from the selected config file.

`labor-sieve uninstall-data` prints user data paths. `labor-sieve uninstall-data --yes` removes the default config/report directory, downloaded presets, and run logs.

## Configuration Notes

User configs are preserved across package upgrades. When a newer LaborSieve release adds config settings, `quickstart`, `validate-config`, and `run` add missing defaults automatically and write a `.bak` backup first. Existing values are left unchanged.

To upgrade config settings explicitly:

```bash
labor-sieve config-upgrade
```

To replace the current config with packaged defaults:

```bash
labor-sieve quickstart --reset-config
```

### Location

Default location settings:

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

Hybrid and on-site roles outside `accepted_locations` are capped below P1. Remote roles are accepted when their location is generic remote or matches `accepted_remote_locations`; remote roles restricted to other geographies are also capped below P1. If a posting is marked both remote and hybrid, LaborSieve treats it as hybrid so local-region rules apply.

### Compensation

`compensation.minimum_base` is the fallback base-pay floor. `compensation.minimum_base_by_seniority` can set broader floors for each seniority level. Set a value to `null` to disable compensation scoring for that level.

```yaml
compensation:
  minimum_base: 85000
  minimum_base_by_seniority:
    entry: 85000
    junior: 85000
    mid: 95000
    senior: 105000
    staff: 115000
```

### Language Requirements

The default config accepts English and penalizes explicit bilingual or non-accepted language requirements. ASL and American Sign Language are treated neutrally by default. Add other languages or language phrases under `accepted` when those requirements should not lower a posting. Add terms under `boost` when those requirements should improve a posting.

```yaml
language_requirements:
  accepted:
    - english
  boost: []
  penalty: 8
  boost_points: 6
```

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

## Sources

Available sources:

- `remoteok`: broad public RemoteOK API listings across many companies.
- `arbeitnow`: broad public Arbeitnow API listings. Disabled by default because it is noisier for a US-centered search.
- `greenhouse`: configured Greenhouse Job Board API boards.
- `lever`: configured Lever Postings API companies.
- `ashby`: configured Ashby job board organizations.
- `workday`: configured Workday candidate experience sites.
- `local_file`: local `.csv`, `.json`, `.yaml`, or `.yml` exports.
- `sample`: synthetic jobs for scoring/report smoke tests. Disabled by default.

The default config disables sample data, enables RemoteOK, disables Arbeitnow, and enables starter lists for Greenhouse, Lever, Ashby, and Workday.

RemoteOK and Arbeitnow are broad sources. Greenhouse, Lever, Ashby, and Workday only scan the boards, companies, organizations, or sites listed in `config.yaml`.

Example source entries:

```yaml
sources:
  remoteok:
    enabled: true
    timeout_seconds: 20
    max_jobs: 250
    base_url: https://remoteok.com/api

  greenhouse:
    enabled: true
    board_tokens:
      - coreweave
      - nebius
    timeout_seconds: 20

  lever:
    enabled: true
    companies:
      - waabi
    timeout_seconds: 20
    base_url: https://api.lever.co/v0/postings

  ashby:
    enabled: true
    organizations:
      - Lambda
      - Crusoe
    timeout_seconds: 30
    base_url: https://api.ashbyhq.com/posting-api/job-board

  workday:
    enabled: true
    sites:
      - company: NVIDIA
        url: https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite
    timeout_seconds: 20
    page_size: 20
    max_jobs_per_site: 100
```

Local file records can include:

```text
title, company, location, remote, hybrid, seniority, role_family,
compensation_base_min, url, description, tags
```

## Presets

Bundled presets are included with the installed package and update when the package is upgraded from PyPI. Downloaded presets live in `~/.config/labor-sieve/presets/` by default and override bundled presets with the same name.

Apply a bundled preset:

```bash
labor-sieve list-presets
labor-sieve use-preset linux-sre
labor-sieve validate-config
```

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

On systems that support lingering, this allows user timers to run while the user is logged out:

```bash
loginctl enable-linger "$USER"
```

## Upgrade And Uninstall

Upgrade from PyPI:

```bash
pipx upgrade labor-sieve
```

Remove generated user data and then uninstall:

```bash
labor-sieve uninstall-data --yes
pipx uninstall labor-sieve
```

`pipx uninstall labor-sieve` removes the installed command. It does not remove `~/labor-sieve/config.yaml` or generated reports unless `labor-sieve uninstall-data --yes` is run first.

## Developer Install

From a checkout:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"

labor-sieve quickstart -c config.yaml
labor-sieve validate-config -c config.yaml
labor-sieve run -c config.yaml
```

Run tests:

```bash
python -m compileall labor_sieve tests
python -m pytest
```

Build release artifacts:

```bash
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
