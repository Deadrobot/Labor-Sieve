# Changelog

## Unreleased

## 0.1.6

- Add explicit config reset and user-data removal commands.
- Add safe config upgrades that back up user configs and merge missing default settings.

## 0.1.5

- Release packaging update.

## 0.1.3

- Make quickstart and install messages editor-neutral.
- Clarify that `run` uses enabled sources from config.
- Add Ashby as a public job board source.
- Show source fetch progress with elapsed time during runs.
- Add Workday as a public candidate experience source.
- Include Workday starter company examples in the default config and quickstart guidance.
- Center default local-region settings and sample jobs on Richmond, VA.
- Make quickstart guidance call out the main config fields to edit before running.
- Disable sample mode by default and enable verified public remote source starter lists.

## 0.1.2

- Hide first-run config creation commands when the target config file already exists.
- Create the default config from `labor-sieve quickstart` and write reports beside explicit config paths.
- Add a release version helper and build-time artifact version check.

## 0.1.1

- Clarify first-run and post-install setup messages with explicit working directory, config path, report path, and config creation command.
- Document PyPI plus pipx as the public install and upgrade path.
- Remove private GitHub raw URLs from public install, preset update, package metadata, and release instructions.
- Require an explicit public HTTPS base URL when generating a remote preset index.

## 0.1.0

- CLI commands: init, quickstart, doctor, validate-config, list-options, presets, and run.
- Sources: sample, local file, Greenhouse, and Lever.
- Reports: terminal P0/P1 summary plus txt/csv/json/html output files.
- Scoring and deduplication for normalized job records.
- Remote preset update and preset apply flow.
- Install script with pipx support and a dedicated user-venv fallback.
- Preset index generation for remotely hosted preset updates.
- Manual and scheduled run setup documentation for Linux users.
- Release build script.
