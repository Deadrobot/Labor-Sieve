"""Command-line entry point for LaborSieve."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date
import shlex
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import TextIO
from urllib.request import Request

from . import __version__
from .company_catalog import (
    KNOWN_SOURCE_FIELDS,
    add_catalog_entries_to_config_data,
    company_catalog_entry_is_stale,
    enable_catalog_entries_in_config,
    filter_company_catalog,
    format_company_entry,
    load_company_catalog,
)
from .completions import SOURCES as COMPLETION_SOURCES, render_completion
from .config import (
    Config,
    ConfigError,
    ConfigUpgradeResult,
    MAX_TIMEOUT_SECONDS,
    WorkdaySiteConfig,
    built_in_options_text,
    find_config_example,
    init_config,
    load_config,
    read_yaml_file,
    upgrade_config,
    validate_config_data,
    yaml,
)
from .history import annotate_run_history, history_enabled, load_history, save_history
from .update_check import maybe_print_update_notice
from .models import Job
from .dedupe import dedupe_jobs
from .exclusions import apply_exclusions
from .net import open_without_redirects
from .presets import (
    PresetError,
    apply_preset_to_config,
    default_user_preset_dir,
    list_presets,
    update_presets,
)
from .reports import render_terminal_summary, write_reports
from .schema import render_config_schema
from .scoring import score_jobs
from .sources.ashby import AshbySource
from .sources.arbeitnow import ArbeitnowSource
from .sources.base import JobSource, SourceError
from .sources.greenhouse import GreenhouseSource
from .sources.local_file import LocalFileSource
from .sources.lever import LeverSource
from .sources.remoteok import RemoteOkSource
from .sources.sample import SampleSource
from .sources.workday import WorkdaySite, WorkdaySource


RUN_SOURCE_CHOICES = tuple(COMPLETION_SOURCES)
CATALOG_STALE_DAYS = 180


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="labor-sieve", description="LaborSieve CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    config_parent = argparse.ArgumentParser(add_help=False)
    config_parent.add_argument(
        "-c",
        "--config",
        default=None,
        help="Path to config.yaml (default: ./config.yaml if present, otherwise ~/labor-sieve/config.yaml)",
    )

    init_parser = subparsers.add_parser("init", parents=[config_parent], help="Create config.yaml")
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Back up and replace an existing config.yaml with packaged defaults",
    )
    init_parser.set_defaults(func=cmd_init)

    quickstart_parser = subparsers.add_parser(
        "quickstart",
        parents=[config_parent],
        help="Create default config if missing and print setup instructions",
    )
    quickstart_parser.add_argument(
        "--reset-config",
        action="store_true",
        help="Back up and replace an existing config.yaml with packaged defaults",
    )
    quickstart_parser.set_defaults(func=cmd_quickstart)

    doctor_parser = subparsers.add_parser(
        "doctor",
        parents=[config_parent],
        help="Check installation and config health",
    )
    doctor_parser.add_argument(
        "--catalog",
        action="store_true",
        help="Also check packaged company catalog freshness",
    )
    doctor_parser.add_argument(
        "--network",
        action="store_true",
        help="Also check live network reachability for configured sources",
    )
    doctor_parser.set_defaults(func=cmd_doctor)

    validate_parser = subparsers.add_parser(
        "validate-config",
        parents=[config_parent],
        help="Validate config.yaml",
    )
    validate_parser.set_defaults(func=cmd_validate_config)

    config_upgrade_parser = subparsers.add_parser(
        "config-upgrade",
        parents=[config_parent],
        help="Back up config.yaml and add missing default settings",
    )
    config_upgrade_parser.set_defaults(func=cmd_config_upgrade)

    run_parser = subparsers.add_parser("run", parents=[config_parent], help="Run enabled sources and write reports")
    run_parser.add_argument(
        "--source",
        choices=RUN_SOURCE_CHOICES,
        action="append",
        help="Only run this source. Repeat to allow multiple sources.",
    )
    run_parser.add_argument(
        "--company",
        action="append",
        help="Only run catalog targets for this company key. Repeat to run multiple companies.",
    )
    run_parser.add_argument(
        "--no-history",
        action="store_true",
        help="Do not read or update run history for this run.",
    )
    run_parser.set_defaults(func=cmd_run)

    uninstall_data_parser = subparsers.add_parser(
        "uninstall-data",
        help="Remove LaborSieve user config, reports, presets, and run state",
    )
    uninstall_data_parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually remove user data; without this flag, only print the paths",
    )
    uninstall_data_parser.set_defaults(func=cmd_uninstall_data)

    list_parser = subparsers.add_parser("list-options", help="List supported taxonomy options")
    list_parser.set_defaults(func=cmd_list_options)

    list_companies_parser = subparsers.add_parser(
        "list-companies",
        help="List packaged company targets for ATS sources",
    )
    list_companies_parser.add_argument(
        "--source",
        choices=sorted(KNOWN_SOURCE_FIELDS),
        help="Only show companies with a target for this source",
    )
    list_companies_parser.add_argument("--tag", help="Only show companies with this tag")
    list_companies_parser.add_argument("--search", help="Search company names, IDs, tags, and target values")
    list_companies_parser.add_argument(
        "--stale",
        action="store_true",
        help=f"Only show companies not verified in the last {CATALOG_STALE_DAYS} days",
    )
    list_companies_parser.set_defaults(func=cmd_list_companies)

    enable_company_parser = subparsers.add_parser(
        "enable-company",
        parents=[config_parent],
        help="Add packaged company targets to config.yaml",
    )
    enable_company_parser.add_argument("company", nargs="*", help="Catalog company key to enable")
    enable_company_parser.add_argument("--tag", help="Enable all catalog companies with this tag")
    enable_company_parser.add_argument(
        "--source",
        choices=sorted(KNOWN_SOURCE_FIELDS),
        help="Only enable targets for this source",
    )
    enable_company_parser.set_defaults(func=cmd_enable_company)

    schema_parser = subparsers.add_parser("schema", help="Print JSON Schema for config.yaml")
    schema_parser.set_defaults(func=cmd_schema)

    completions_parser = subparsers.add_parser("completions", help="Print shell completion script")
    completions_parser.add_argument("shell", choices=["bash", "zsh", "fish"])
    completions_parser.set_defaults(func=cmd_completions)

    preset_parent = argparse.ArgumentParser(add_help=False)
    preset_parent.add_argument(
        "--preset-dir",
        default=None,
        help="Directory for downloaded presets (default: ~/.config/labor-sieve/presets)",
    )

    list_presets_parser = subparsers.add_parser(
        "list-presets",
        parents=[preset_parent],
        help="List bundled and downloaded presets",
    )
    list_presets_parser.set_defaults(func=cmd_list_presets)

    update_presets_parser = subparsers.add_parser(
        "update-presets",
        parents=[preset_parent],
        help="Download preset updates from an index.json URL",
    )
    update_presets_parser.add_argument("--index-url", required=True, help="URL to a preset index JSON file")
    update_presets_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=20,
        help="Network timeout for preset downloads",
    )
    update_presets_parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Allow index entries without sha256 checksums",
    )
    update_presets_parser.set_defaults(func=cmd_update_presets)

    use_preset_parser = subparsers.add_parser(
        "use-preset",
        parents=[config_parent, preset_parent],
        help="Apply a preset to config.yaml",
    )
    use_preset_parser.add_argument("preset", help="Preset name, for example linux-sre")
    use_preset_parser.set_defaults(func=cmd_use_preset)

    return parser


def cmd_init(args: argparse.Namespace) -> int:
    config_path = resolve_config_path(args.config)
    try:
        print(init_config(config_path, overwrite=args.force))
    except ConfigError as exc:
        print_errors(exc.errors)
        return 1
    print()
    print(quickstart_text(config_path, include_create=False))
    return 0


def cmd_quickstart(args: argparse.Namespace) -> int:
    config_path = _absolute_path(resolve_config_path(args.config))
    if args.reset_config or not config_path.exists():
        try:
            print(init_config(config_path, overwrite=args.reset_config))
        except ConfigError as exc:
            print_errors(exc.errors)
            return 1
        print()
        print(quickstart_text(config_path, include_create=False))
    else:
        if not upgrade_config_if_needed(config_path, stream=sys.stdout):
            return 1
        print(quickstart_text(config_path, include_create=True))
    maybe_check_for_updates(config_path, stream=sys.stderr)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    checks: list[tuple[str, bool, str]] = []
    config_path = resolve_config_path(args.config)
    loaded_config: Config | None = None

    checks.append(
        (
            "Python version",
            sys.version_info >= (3, 10),
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    )
    checks.append(("PyYAML import", yaml is not None, "available" if yaml is not None else "missing"))

    example_path = find_config_example()
    checks.append(
        (
            "Example config",
            example_path is not None,
            str(example_path) if example_path is not None else "not found",
        )
    )

    try:
        preset_count = len(list_presets(None))
        checks.append(("Bundled presets", preset_count > 0, f"{preset_count} found"))
    except (ConfigError, PresetError) as exc:
        checks.append(("Bundled presets", False, "; ".join(exc.errors)))

    config_ok = False
    config_data = None
    if config_path.exists():
        try:
            config_data = read_yaml_file(config_path)
            errors = validate_config_data(config_data)
        except ConfigError as exc:
            errors = exc.errors
        config_ok = not errors
        checks.append(
            (
                "Config file",
                config_ok,
                str(config_path) if config_ok else "; ".join(errors),
            )
        )
    else:
        checks.append(("Config file", False, f"{config_path} not found; run labor-sieve init"))

    if config_ok and config_data is not None:
        try:
            loaded_config = load_config(config_path)
            enabled = [source.name for source in enabled_sources(loaded_config)]
            checks.append(("Enabled sources", bool(enabled), ", ".join(enabled) if enabled else "none enabled"))
            output_dir = resolve_output_dir(loaded_config, config_path)
            parent = output_dir.parent if output_dir.parent != Path("") else Path(".")
            checks.append(("Output parent", parent.exists(), str(parent)))
        except ConfigError as exc:
            checks.append(("Parsed config", False, "; ".join(exc.errors)))

    if args.catalog:
        checks.extend(catalog_doctor_checks())
    if args.network:
        checks.extend(network_doctor_checks(loaded_config))

    print(f"LaborSieve {__version__} doctor")
    for label, passed, detail in checks:
        status = "ok" if passed else "fail"
        print(f"[{status}] {label}: {detail}")
    if loaded_config is not None:
        maybe_print_configured_update_notice(loaded_config, stream=sys.stderr)
    return 0 if all(passed for _, passed, _ in checks) else 1


def cmd_validate_config(args: argparse.Namespace) -> int:
    path = resolve_config_path(args.config)
    if not upgrade_config_if_needed(path, stream=sys.stdout):
        return 1
    try:
        data = read_yaml_file(path)
    except ConfigError as exc:
        print_errors(exc.errors)
        return 1

    errors = validate_config_data(data)
    if errors:
        print_errors(errors)
        return 1

    print(f"{path} is valid.")
    return 0


def cmd_config_upgrade(args: argparse.Namespace) -> int:
    path = resolve_config_path(args.config)
    try:
        result = upgrade_config(path)
    except ConfigError as exc:
        print_errors(exc.errors)
        return 1
    print(format_config_upgrade_result(result))
    return 0


def cmd_uninstall_data(args: argparse.Namespace) -> int:
    paths = user_data_paths()
    if not args.yes:
        print("LaborSieve user data paths:")
        for path in paths:
            status = "exists" if path.exists() else "not found"
            print(f"  {path} ({status})")
        print()
        print("To remove these files, run: labor-sieve uninstall-data --yes")
        print("Then remove the installed command with: pipx uninstall labor-sieve")
        return 0

    for path in paths:
        try:
            if path.is_dir():
                shutil.rmtree(path)
                print(f"Removed {path}")
            elif path.exists():
                path.unlink()
                print(f"Removed {path}")
            else:
                print(f"Not found: {path}")
        except OSError as exc:
            print_errors([f"{path} could not be removed: {exc}"])
            return 1
    return 0


def cmd_list_options(args: argparse.Namespace) -> int:
    del args
    print(built_in_options_text())
    return 0


def cmd_list_companies(args: argparse.Namespace) -> int:
    try:
        entries = load_company_catalog()
    except ConfigError as exc:
        print_errors(exc.errors)
        return 1

    entries = filter_company_catalog(
        entries,
        source=args.source,
        tag=args.tag,
        search=args.search,
        stale_days=CATALOG_STALE_DAYS if args.stale else None,
    )
    if not entries:
        print("No companies matched.")
        return 0

    print("Available companies:")
    for entry in entries:
        for line in format_company_entry(entry).splitlines():
            print(f"  {line}")
    return 0


def cmd_enable_company(args: argparse.Namespace) -> int:
    config_path = resolve_config_path(args.config)
    if not upgrade_config_if_needed(config_path, stream=sys.stdout):
        return 1
    try:
        entries = selected_catalog_entries(
            company_keys=args.company,
            tag=args.tag,
            source=args.source,
        )
        if not entries:
            print("No companies matched.")
            return 1
        path, backup_path, changed = enable_catalog_entries_in_config(
            entries,
            config_path,
            source=args.source,
        )
    except ConfigError as exc:
        print_errors(exc.errors)
        return 1

    if not changed:
        print(f"No config changes needed: {path}")
        return 0
    print(f"Config updated: {path}")
    if backup_path is not None:
        print(f"Backup written to {backup_path}")
    print("Enabled company targets:")
    for item in changed:
        print(f"  - {item}")
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    del args
    print(render_config_schema(), end="")
    return 0


def cmd_completions(args: argparse.Namespace) -> int:
    try:
        print(render_completion(args.shell), end="")
    except ValueError as exc:
        print_errors([str(exc)])
        return 1
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config_path = resolve_config_path(args.config)
    if not upgrade_config_if_needed(config_path, stream=sys.stderr):
        return 1
    try:
        config = load_config(config_path)
        config = filtered_run_config(config, source_filters=args.source, company_keys=args.company)
    except ConfigError as exc:
        print_errors(exc.errors)
        return 1
    maybe_print_configured_update_notice(config, stream=sys.stderr)

    jobs, source_errors = fetch_jobs(config)
    if source_errors:
        print("Source warnings:", file=sys.stderr)
        for error in source_errors:
            print(f"  - {error}", file=sys.stderr)
        if not jobs:
            return 1

    jobs, excluded_count = apply_exclusions(jobs, config)
    jobs, duplicate_count = dedupe_jobs(jobs)
    scored = score_jobs(jobs, config)
    history = None
    if history_enabled() and not args.no_history:
        previous = load_history()
        history = annotate_run_history(scored, previous)
    try:
        written = write_reports(scored, config, base_dir=_absolute_path(config_path).parent, history=history)
    except OSError as exc:
        print_errors([f"Reports could not be written: {exc}"])
        return 1
    if history_enabled() and not args.no_history:
        save_history(scored)
    print(
        render_terminal_summary(
            scored,
            written,
            config=config,
            duplicate_count=duplicate_count,
            excluded_count=excluded_count,
            history=history,
        )
    )
    return 0


def cmd_list_presets(args: argparse.Namespace) -> int:
    try:
        presets = list_presets(_optional_path(args.preset_dir))
    except (ConfigError, PresetError) as exc:
        print_errors(exc.errors)
        return 1

    if not presets:
        print("No presets found.")
        return 0

    print("Available presets:")
    for preset in presets:
        version = f" version {preset.version}" if preset.version else ""
        description = f" - {preset.description}" if preset.description else ""
        print(f"  {preset.name} [{preset.source}{version}]{description}")
    if args.preset_dir is None:
        print(f"\nDownloaded preset directory: {default_user_preset_dir()}")
    return 0


def cmd_update_presets(args: argparse.Namespace) -> int:
    if args.timeout_seconds <= 0 or args.timeout_seconds > MAX_TIMEOUT_SECONDS:
        print_errors([f"--timeout-seconds must be an integer from 1 to {MAX_TIMEOUT_SECONDS}."])
        return 1
    try:
        results = update_presets(
            args.index_url,
            preset_dir=_optional_path(args.preset_dir),
            timeout_seconds=args.timeout_seconds,
            allow_unverified=args.allow_unverified,
        )
    except PresetError as exc:
        print_errors(exc.errors)
        return 1

    updated = [result for result in results if not result.skipped]
    skipped = [result for result in results if result.skipped]
    print(f"Preset update complete: {len(updated)} updated, {len(skipped)} skipped.")
    for result in results:
        status = "skipped" if result.skipped else "updated"
        verified = "verified" if result.verified else "unverified"
        print(f"  {result.name}: {status} ({verified}) - {result.message}")
    return 1 if skipped and not updated else 0


def cmd_use_preset(args: argparse.Namespace) -> int:
    try:
        config_path, backup_path = apply_preset_to_config(
            args.preset,
            resolve_config_path(args.config),
            preset_dir=_optional_path(args.preset_dir),
        )
    except (ConfigError, PresetError) as exc:
        print_errors(exc.errors)
        return 1
    print(f"Applied preset {args.preset!r} to {config_path}.")
    print(f"Backup written to {backup_path}.")
    return 0


def fetch_jobs(config: Config) -> tuple[list[Job], list[str]]:
    jobs: list[Job] = []
    errors = []
    for source in enabled_sources(config):
        try:
            jobs.extend(fetch_source_with_status(source))
            for warning in getattr(source, "warnings", []):
                errors.append(f"{source.name}: {warning}")
        except SourceError as exc:
            errors.append(f"{source.name}: {exc}")
    return jobs, errors


def selected_catalog_entries(
    *,
    company_keys: list[str],
    tag: str | None,
    source: str | None,
) -> list:
    if not company_keys and not tag:
        raise ConfigError(["Provide at least one company key or --tag."])
    entries = load_company_catalog()
    selected = []
    by_key = {entry.key: entry for entry in entries}
    for key in company_keys:
        normalized = key.casefold()
        entry = by_key.get(normalized)
        if entry is None:
            raise ConfigError([f"Company {key!r} was not found. Run: labor-sieve list-companies --search {key}"])
        selected.append(entry)
    if tag:
        selected.extend(filter_company_catalog(entries, tag=tag))
    deduped = []
    seen = set()
    for entry in selected:
        if source and source not in entry.sources:
            continue
        if entry.key not in seen:
            seen.add(entry.key)
            deduped.append(entry)
    return deduped


def filtered_run_config(
    config: Config,
    *,
    source_filters: list[str] | None,
    company_keys: list[str] | None,
) -> Config:
    filtered = deepcopy(config)
    allowed_sources = set(source_filters or [])
    if company_keys:
        unsupported = sorted(allowed_sources - set(KNOWN_SOURCE_FIELDS))
        if unsupported:
            raise ConfigError(
                [
                    "--company can only be combined with catalog-backed sources: "
                    + ", ".join(sorted(KNOWN_SOURCE_FIELDS))
                    + f" (got {', '.join(unsupported)})."
                ]
            )
        entries = selected_catalog_entries(company_keys=company_keys, tag=None, source=None)
        filter_config_to_catalog_entries(filtered, entries, allowed_sources=allowed_sources)
        if not config_has_enabled_source(filtered):
            raise ConfigError(["No catalog targets matched the selected company/source filters."])
        return filtered
    if allowed_sources:
        disable_unselected_sources(filtered, allowed_sources)
    return filtered


def disable_unselected_sources(config: Config, allowed_sources: set[str]) -> None:
    for name in RUN_SOURCE_CHOICES:
        source_config = getattr(config.sources, name)
        source_config.enabled = name in allowed_sources


def config_has_enabled_source(config: Config) -> bool:
    return any(getattr(config.sources, name).enabled for name in RUN_SOURCE_CHOICES)


def filter_config_to_catalog_entries(config: Config, entries: list, *, allowed_sources: set[str]) -> None:
    selected_sources = set(allowed_sources)
    if not selected_sources:
        selected_sources = {source for entry in entries for source in entry.sources}
    disable_unselected_sources(config, selected_sources)
    config.sources.greenhouse.board_tokens = []
    config.sources.lever.companies = []
    config.sources.ashby.organizations = []
    config.sources.workday.sites = []

    data = {
        "sources": {
            "greenhouse": {"enabled": config.sources.greenhouse.enabled, "board_tokens": []},
            "lever": {"enabled": config.sources.lever.enabled, "companies": []},
            "ashby": {"enabled": config.sources.ashby.enabled, "organizations": []},
            "workday": {"enabled": config.sources.workday.enabled, "sites": []},
        }
    }
    add_catalog_entries_to_config_data(data, entries, source=None)
    sources = data["sources"]
    config.sources.greenhouse.board_tokens = sources["greenhouse"]["board_tokens"]
    config.sources.greenhouse.enabled = "greenhouse" in selected_sources and bool(config.sources.greenhouse.board_tokens)
    config.sources.lever.companies = sources["lever"]["companies"]
    config.sources.lever.enabled = "lever" in selected_sources and bool(config.sources.lever.companies)
    config.sources.ashby.organizations = sources["ashby"]["organizations"]
    config.sources.ashby.enabled = "ashby" in selected_sources and bool(config.sources.ashby.organizations)
    config.sources.workday.sites = [
        WorkdaySiteConfig(company=site["company"], url=site["url"]) for site in sources["workday"]["sites"]
    ]
    config.sources.workday.enabled = "workday" in selected_sources and bool(config.sources.workday.sites)


def catalog_doctor_checks() -> list[tuple[str, bool, str]]:
    try:
        entries = load_company_catalog()
    except ConfigError as exc:
        return [("Company catalog", False, "; ".join(exc.errors))]
    stale = [
        entry
        for entry in entries
        if company_catalog_entry_is_stale(entry, CATALOG_STALE_DAYS, date.today())
    ]
    source_counts = {
        source: sum(1 for entry in entries if source in entry.sources)
        for source in sorted(KNOWN_SOURCE_FIELDS)
    }
    detail = ", ".join(f"{source} {count}" for source, count in source_counts.items())
    checks = [("Company catalog", bool(entries), f"{len(entries)} companies; {detail}")]
    checks.append(
        (
            "Catalog verification freshness",
            not stale,
            "all current" if not stale else f"{len(stale)} stale entries",
        )
    )
    return checks


def network_doctor_checks(config: Config | None) -> list[tuple[str, bool, str]]:
    checks = [network_probe_url("PyPI", "https://pypi.org/pypi/labor-sieve/json")]
    if config is None:
        checks.append(("Configured source network", False, "config was not loaded"))
        return checks
    if config.sources.remoteok.enabled:
        checks.append(network_probe_url("RemoteOK", config.sources.remoteok.base_url))
    if config.sources.arbeitnow.enabled:
        checks.append(network_probe_url("Arbeitnow", config.sources.arbeitnow.base_url))
    if config.sources.greenhouse.enabled:
        for token in config.sources.greenhouse.board_tokens:
            checks.append(
                network_probe_url(
                    f"Greenhouse {token}",
                    f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=false",
                )
            )
    if config.sources.lever.enabled:
        for company in config.sources.lever.companies:
            checks.append(network_probe_url(f"Lever {company}", f"{config.sources.lever.base_url.rstrip('/')}/{company}?mode=json"))
    if config.sources.ashby.enabled:
        for organization in config.sources.ashby.organizations:
            checks.append(
                network_probe_url(
                    f"Ashby {organization}",
                    f"{config.sources.ashby.base_url.rstrip('/')}/{organization}?includeCompensation=true",
                )
            )
    if config.sources.workday.enabled:
        for site in config.sources.workday.sites:
            checks.append(network_probe_url(f"Workday {site.company}", site.url))
    return checks


def network_probe_url(label: str, url: str, timeout_seconds: int = 5) -> tuple[str, bool, str]:
    request = Request(url, headers={"User-Agent": "labor-sieve doctor"})
    try:
        with open_without_redirects(request, timeout_seconds) as response:
            status = getattr(response, "status", 200)
            return (label, 200 <= int(status) < 400, f"HTTP {status}")
    except Exception as exc:
        return (label, False, str(exc))


def enabled_sources(config: Config) -> list[JobSource]:
    sources: list[JobSource] = []
    if config.sources.sample.enabled:
        sources.append(SampleSource())
    if config.sources.local_file.enabled:
        sources.append(LocalFileSource(config.sources.local_file.paths))
    if config.sources.remoteok.enabled:
        sources.append(
            RemoteOkSource(
                timeout_seconds=config.sources.remoteok.timeout_seconds,
                max_jobs=config.sources.remoteok.max_jobs,
                base_url=config.sources.remoteok.base_url,
            )
        )
    if config.sources.arbeitnow.enabled:
        sources.append(
            ArbeitnowSource(
                timeout_seconds=config.sources.arbeitnow.timeout_seconds,
                max_pages=config.sources.arbeitnow.max_pages,
                max_jobs=config.sources.arbeitnow.max_jobs,
                base_url=config.sources.arbeitnow.base_url,
            )
        )
    if config.sources.greenhouse.enabled:
        sources.append(
            GreenhouseSource(
                config.sources.greenhouse.board_tokens,
                timeout_seconds=config.sources.greenhouse.timeout_seconds,
            )
        )
    if config.sources.lever.enabled:
        sources.append(
            LeverSource(
                config.sources.lever.companies,
                timeout_seconds=config.sources.lever.timeout_seconds,
                base_url=config.sources.lever.base_url,
            )
        )
    if config.sources.ashby.enabled:
        sources.append(
            AshbySource(
                config.sources.ashby.organizations,
                timeout_seconds=config.sources.ashby.timeout_seconds,
                base_url=config.sources.ashby.base_url,
            )
        )
    if config.sources.workday.enabled:
        sources.append(
            WorkdaySource(
                [
                    WorkdaySite(company=site.company, url=site.url)
                    for site in config.sources.workday.sites
                ],
                timeout_seconds=config.sources.workday.timeout_seconds,
                page_size=config.sources.workday.page_size,
                max_jobs_per_site=config.sources.workday.max_jobs_per_site,
            )
        )
    return sources


def fetch_source_with_status(source: JobSource) -> list[Job]:
    label = f"Fetching {source.name}"
    start = time.monotonic()
    if not sys.stderr.isatty():
        print(f"{label}...", file=sys.stderr)
        try:
            jobs = source.fetch()
        except SourceError:
            print(f"{label} failed after {format_elapsed(start)}.", file=sys.stderr)
            raise
        print(f"{label} finished in {format_elapsed(start)} ({len(jobs)} jobs).", file=sys.stderr)
        return jobs

    done = threading.Event()

    def heartbeat() -> None:
        while not done.wait(0.5):
            print(f"\r{label}... {format_elapsed(start)}", end="", file=sys.stderr, flush=True)

    thread = threading.Thread(target=heartbeat, daemon=True)
    print(f"{label}... 0s", end="", file=sys.stderr, flush=True)
    thread.start()
    try:
        jobs = source.fetch()
    except SourceError:
        done.set()
        thread.join()
        print(f"\r{label} failed after {format_elapsed(start)}.", file=sys.stderr)
        raise
    done.set()
    thread.join()
    print(f"\r{label} finished in {format_elapsed(start)} ({len(jobs)} jobs).", file=sys.stderr)
    return jobs


def format_elapsed(start: float) -> str:
    elapsed = int(time.monotonic() - start)
    minutes, seconds = divmod(elapsed, 60)
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def upgrade_config_if_needed(path: Path, *, stream: TextIO) -> bool:
    try:
        result = upgrade_config(path)
    except ConfigError as exc:
        print_errors(exc.errors)
        return False
    if result.changed:
        print(format_config_upgrade_result(result), file=stream)
    return True


def maybe_check_for_updates(config_path: Path, *, stream: TextIO) -> None:
    try:
        config = load_config(config_path)
    except ConfigError:
        return
    maybe_print_configured_update_notice(config, stream=stream)


def maybe_print_configured_update_notice(config: Config, *, stream: TextIO) -> None:
    maybe_print_update_notice(
        installed_version=__version__,
        enabled=config.update_check.enabled,
        interval_days=config.update_check.interval_days,
        stream=stream,
    )


def format_config_upgrade_result(result: ConfigUpgradeResult) -> str:
    if not result.changed:
        return f"Config is current: {result.path}"
    lines = [
        f"Config updated: {result.path}",
        f"Backup written to {result.backup_path}",
        "Added missing settings:",
    ]
    lines.extend(f"  - {path}" for path in result.added_paths)
    return "\n".join(lines)


def print_errors(errors: list[str]) -> None:
    print("Errors:", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)


def default_config_path() -> Path:
    return Path.home() / "labor-sieve" / "config.yaml"


def user_data_paths() -> list[Path]:
    return [
        Path.home() / "labor-sieve",
        Path.home() / ".config" / "labor-sieve",
        Path.home() / ".local" / "state" / "labor-sieve",
    ]


def resolve_config_path(value: str | None) -> Path:
    if value is not None:
        return Path(value).expanduser()
    local_config = Path("config.yaml")
    if local_config.exists():
        return local_config
    return default_config_path()


def resolve_output_dir(config: Config, config_path: Path) -> Path:
    output_dir = Path(config.output.directory).expanduser()
    if output_dir.is_absolute():
        return output_dir
    return _absolute_path(config_path).parent / output_dir


def _optional_path(value: str | None) -> Path | None:
    if value is None:
        return None
    return Path(value).expanduser()


def quickstart_text(config_path: Path, *, include_create: bool) -> str:
    config_path = _absolute_path(config_path)
    work_dir = config_path.parent
    config_name = config_path.name
    output_dir = work_dir / "output"
    preset_dir = default_user_preset_dir()
    uses_default_config = config_path == _absolute_path(default_config_path())
    validate_command = "labor-sieve validate-config"
    run_command = "labor-sieve run"
    preset_command = "labor-sieve use-preset linux-sre"
    if not uses_default_config:
        validate_command = f"labor-sieve validate-config -c {_quote(config_path)}"
        run_command = f"labor-sieve run -c {_quote(config_path)}"
        preset_command = f"labor-sieve use-preset linux-sre -c {_quote(config_path)}"

    lines = [
        "Recommended files:",
        f"  Working directory: {work_dir}",
        f"  Config file: {config_path}",
        f"  Default reports: {output_dir}",
        f"  Downloaded presets: {preset_dir}",
        "",
    ]

    if include_create and not config_path.exists():
        lines.extend(
            [
                "Create the config file with the default commented settings:",
                f"  mkdir -p {_quote(work_dir)}",
                f"  cd {_quote(work_dir)}",
                f"  labor-sieve init -c {_quote(config_name)}",
                "",
            ]
        )
    elif include_create and config_path.exists():
        reset_command = f"labor-sieve quickstart --reset-config -c {_quote(config_path)}"
        lines.extend(
            [
                "Existing config:",
                "  quickstart keeps existing values and adds missing default settings when needed.",
                f"  Replace all settings with packaged defaults: {reset_command}",
                "",
            ]
        )
    lines.extend(
        [
            "Next steps:",
            f"  1. Edit the config file with your preferred editor: {_quote(config_path)}",
            "  2. Set location, seniority, remote/on-site, compensation, keywords, language requirements, and sources.",
            f"  3. Validate it: {validate_command}",
            f"  4. Run a scan: {run_command}",
            f"  5. Read the text report: {_quote(str(output_dir / 'latest.txt'))}",
            "",
            "Config notes:",
            "  Public remote and configured ATS sources are enabled by default; sample data is disabled.",
            "  Missing default settings are added automatically with a .bak backup.",
            "  Local-region settings are under locations.local_region and locations.accepted_locations.",
            "  Remote-region settings are under locations.accepted_remote_locations.",
            "  Seniority settings are under seniority; remote/local preferences are under locations.",
            "  Compensation floors are under compensation.minimum_base and compensation.minimum_base_by_seniority.",
            "  Language requirement preferences are under language_requirements.",
            "  Company and posting exclusions are under exclusions.",
            "  Terminal summary limits are under output.terminal_p0_limit and output.terminal_p1_limit.",
            "  Broad source controls are under sources.remoteok and sources.arbeitnow.",
            "  Workday company examples are listed under sources.workday.sites.",
            "  Review or edit the enabled RemoteOK, Greenhouse, Lever, Ashby, and Workday source lists.",
            "  Disable any source by setting that source's enabled field to false.",
            "",
            "Useful setup commands:",
            "  labor-sieve list-presets",
            f"  {preset_command}",
            "  labor-sieve list-companies --source greenhouse",
            "  labor-sieve enable-company coreweave",
            "  labor-sieve list-options",
            "  labor-sieve schema",
            "",
            "Scheduled run example:",
            (
                f"  17 8 * * * {_quote(str(Path.home() / '.local' / 'bin' / 'labor-sieve'))} run "
                f"-c {_quote(config_path)} >> "
                f"{_quote(str(Path.home() / '.local' / 'state' / 'labor-sieve' / 'run.log'))} 2>&1"
            ),
        ]
    )
    return "\n".join(lines)


def _absolute_path(path: Path) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve(strict=False)


def _quote(value: str | Path) -> str:
    return shlex.quote(str(value))


if __name__ == "__main__":
    raise SystemExit(main())
