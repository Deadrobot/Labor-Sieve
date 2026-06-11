# Security Review

Current review date: 2026-06-11
Remediation date: 2026-06-11

Scope: repository-wide review of the LaborSieve CLI, install/update scripts, config handling, source adapters, preset update flow, report writers, packaged presets, and release metadata.

## Summary

| ID | Severity | Status | Area | Finding |
| --- | --- | --- | --- | --- |
| LS-CSV-001 | Medium / P2 | Remediated | CSV reports | Generated CSV cells preserve spreadsheet formula prefixes from job data. |
| LS-DOS-001 | Medium / P2 | Remediated | Input ingestion | Remote responses and local import files are read and materialized without size or record limits. |
| LS-REDIRECT-001 | Low / P3 | Remediated | Remote sources | Greenhouse and Lever fetches follow redirects without validating the final destination. |

No critical or high-severity findings were identified in this review.

## Remediated Findings

### LS-CSV-001: CSV Formula Injection

Affected code:

- `labor_sieve/reports.py:125-172`
- `labor_sieve/sources/normalization.py:35-52`
- `labor_sieve/sources/local_file.py:38-53`
- `labor_sieve/sources/greenhouse.py:54-63`
- `labor_sieve/sources/lever.py:59-72`

Job data from local imports and remote source adapters can reach `write_csv_report()` and be written to `output/latest.csv` with leading spreadsheet formula characters intact. Values beginning with `=`, `+`, `-`, `@`, tab, or carriage return can be interpreted as formulas when the CSV is opened in spreadsheet software.

Fix applied:

- Added `csv_safe_cell()` in `labor_sieve/reports.py`.
- Applied the sanitizer to every string field written to CSV, including joined tags, score reasons, descriptions, source IDs, and merged source names.
- Preserved text, JSON, and HTML report behavior.
- Added a regression test that writes formula-leading values and verifies the generated CSV stores them as text.

Why:

- CSV escaping and quoting do not prevent spreadsheet formula interpretation.
- Prefixing dangerous cells at the CSV boundary keeps the protection specific to spreadsheet output without mutating normalized job data or other report formats.

### LS-DOS-001: Unbounded Input Reads

Affected code:

- `labor_sieve/presets.py:301-320`
- `labor_sieve/sources/greenhouse.py:37-38`
- `labor_sieve/sources/lever.py:43-44`
- `labor_sieve/sources/local_file.py:38-53`
- `labor_sieve/cli.py:318-326`
- `labor_sieve/scoring.py:24-26`
- `labor_sieve/reports.py:18-238`

Preset updates, remote job APIs, and local imports read entire responses or files into memory, then normalize, score, sort, deduplicate, and render full report bodies. A large remote response or third-party export can exhaust local CPU, memory, or disk during a CLI run.

Fix applied:

- Added `labor_sieve/net.py` with shared byte and record limits.
- Limited preset index and preset downloads to 1 MiB.
- Limited Greenhouse and Lever response bodies to 10 MiB.
- Limited local import files to 10 MiB.
- Limited source records to 5,000 per source.
- Rejected oversized `Content-Length` values before reading when present.
- Used capped response reads for responses without `Content-Length`.
- Streamed CSV imports until the record cap is reached instead of blindly materializing the whole file.
- Added regression tests for oversized remote responses, oversized preset downloads, oversized local files, and excessive CSV records.

Why:

- This keeps the CLI simple and avoids adding new config keys for release prep.
- Fixed default caps prevent untrusted remote responses and third-party exports from consuming unbounded local resources.
- File-size and response-size checks bound memory use before parsing, while record caps bound downstream scoring and report generation.

### LS-REDIRECT-001: Redirects To Arbitrary Final Destinations

Affected code:

- `labor_sieve/sources/greenhouse.py:33-38`
- `labor_sieve/sources/lever.py:39-44`

The remote source adapters use Python's default `urllib.request.urlopen()` redirect behavior. If an upstream endpoint returns a redirect, the final HTTP(S) or FTP destination is not checked before the local CLI follows it.

Fix applied:

- Added `open_without_redirects()` in `labor_sieve/net.py`.
- Greenhouse and Lever now use the no-redirect opener instead of default `urlopen()` redirect behavior.
- Redirect responses are rejected before the local client follows the redirected URL.
- Added a regression test that simulates a redirect to a loopback URL and verifies the source raises `SourceError`.

Why:

- Blocking redirects at the request boundary is simpler and safer than following a redirect and validating the destination afterward.
- The source adapters only need the expected job API response, so redirects are unnecessary for normal operation.

## Reviewed And Rejected

| ID | Status | Area | Notes |
| --- | --- | --- | --- |
| LS-PRESET-001 | Rejected | Remote presets | `file://` preset URLs are accepted, but accepted content is constrained by checksum checks, `yaml.safe_load`, preset name validation, fixed destination paths, config-fragment filtering, and merged-config validation. No code execution, exfiltration, or path traversal survived review. The unbounded-read aspect is covered by LS-DOS-001. |
| LS-INSTALL-001 | Release hardening | Install docs | Mutable GitHub branch install commands and unpinned Git package specs are a publication-readiness concern, not a product vulnerability in the current repository. Prefer versioned package installation, immutable tags, or checksum-verified release artifacts for public release instructions. |
| Config YAML parsing | No issue found | Config loading | Config files use `yaml.safe_load` and schema validation. No unsafe YAML object construction or command execution hook was identified. |
| HTML reports | No issue found | Static HTML output | HTML report fields are escaped, and generated links are limited to safe `http` and `https` URLs with network locations. |
| Package data | No issue found | Build metadata | Package data inclusion is explicit. No broad secret or build-artifact inclusion was identified. |
| Maintainer scripts | No issue found | Release scripts | Release script behavior is maintainer-controlled and scoped to expected local build artifacts. |

## Verification Commands

Latest remediation verification passed on 2026-06-11:

```bash
python3 -m compileall labor_sieve tests
.venv/bin/python -m pytest tests/test_reports.py tests/test_sources.py tests/test_presets.py
.venv/bin/python -m pytest
sh -n scripts/install.sh
sh -n scripts/build-release.sh
scripts/build-release.sh
```

The focused tests cover CSV formula neutralization, oversized preset downloads, oversized remote source responses, excessive source records, oversized local imports, and redirect blocking for both Greenhouse and Lever.

## Review Notes

The review found no daemon, database, credential store, background service, reverse proxy, shell-evaluation path, unsafe YAML loader, unsafe HTML rendering path, or arbitrary filesystem write through presets.

Publication hardening update on 2026-06-11:

- Public install and upgrade documentation now uses the PyPI package through `pipx`.
- Private GitHub raw URLs were removed from public install instructions, package metadata, and the tracked remote preset index.
- Remote preset index generation now requires an explicit public HTTPS base URL.

Keep this file current when findings are fixed or when new source adapters, report formats, install paths, or preset update behavior are added.
