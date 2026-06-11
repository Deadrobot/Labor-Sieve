# Changelog

## Unreleased

- Hide first-run config creation commands when the target config file already exists.
- Create the default config from `labor-sieve quickstart` and write reports beside explicit config paths.

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
