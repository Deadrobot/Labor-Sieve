"""Command-line entry point for LaborSieve."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import (
    Config,
    ConfigError,
    built_in_options_text,
    find_config_example,
    init_config,
    load_config,
    read_yaml_file,
    validate_config_data,
    yaml,
)
from .models import Job
from .dedupe import dedupe_jobs
from .presets import (
    PresetError,
    apply_preset_to_config,
    default_user_preset_dir,
    list_presets,
    update_presets,
)
from .reports import render_terminal_summary, write_reports
from .scoring import score_jobs
from .sources.base import JobSource, SourceError
from .sources.greenhouse import GreenhouseSource
from .sources.local_file import LocalFileSource
from .sources.lever import LeverSource
from .sources.sample import SampleSource


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
    config_parent.add_argument("-c", "--config", default="config.yaml", help="Path to config.yaml")

    init_parser = subparsers.add_parser("init", parents=[config_parent], help="Create config.yaml")
    init_parser.set_defaults(func=cmd_init)

    quickstart_parser = subparsers.add_parser("quickstart", help="Print first-run setup instructions")
    quickstart_parser.set_defaults(func=cmd_quickstart)

    doctor_parser = subparsers.add_parser(
        "doctor",
        parents=[config_parent],
        help="Check installation and config health",
    )
    doctor_parser.set_defaults(func=cmd_doctor)

    validate_parser = subparsers.add_parser(
        "validate-config",
        parents=[config_parent],
        help="Validate config.yaml",
    )
    validate_parser.set_defaults(func=cmd_validate_config)

    run_parser = subparsers.add_parser("run", parents=[config_parent], help="Run sample scan and write reports")
    run_parser.set_defaults(func=cmd_run)

    list_parser = subparsers.add_parser("list-options", help="List supported taxonomy options")
    list_parser.set_defaults(func=cmd_list_options)

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
    try:
        print(init_config(Path(args.config)))
    except ConfigError as exc:
        print_errors(exc.errors)
        return 1
    print()
    print(quickstart_text(Path(args.config)))
    return 0


def cmd_quickstart(args: argparse.Namespace) -> int:
    del args
    print(quickstart_text(Path("config.yaml")))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    checks: list[tuple[str, bool, str]] = []
    config_path = Path(args.config)

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
            config = load_config(config_path)
            enabled = [source.name for source in enabled_sources(config)]
            checks.append(("Enabled sources", bool(enabled), ", ".join(enabled) if enabled else "none enabled"))
            output_dir = Path(config.output.directory)
            parent = output_dir.parent if output_dir.parent != Path("") else Path(".")
            checks.append(("Output parent", parent.exists(), str(parent)))
        except ConfigError as exc:
            checks.append(("Parsed config", False, "; ".join(exc.errors)))

    print(f"LaborSieve {__version__} doctor")
    for label, passed, detail in checks:
        status = "ok" if passed else "fail"
        print(f"[{status}] {label}: {detail}")
    return 0 if all(passed for _, passed, _ in checks) else 1


def cmd_validate_config(args: argparse.Namespace) -> int:
    path = Path(args.config)
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


def cmd_list_options(args: argparse.Namespace) -> int:
    del args
    print(built_in_options_text())
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    try:
        config = load_config(Path(args.config))
    except ConfigError as exc:
        print_errors(exc.errors)
        return 1

    jobs, source_errors = fetch_jobs(config)
    if source_errors:
        print("Source warnings:", file=sys.stderr)
        for error in source_errors:
            print(f"  - {error}", file=sys.stderr)
        if not jobs:
            return 1

    jobs, duplicate_count = dedupe_jobs(jobs)
    scored = score_jobs(jobs, config)
    try:
        written = write_reports(scored, config)
    except OSError as exc:
        print_errors([f"Reports could not be written: {exc}"])
        return 1
    print(render_terminal_summary(scored, written, duplicate_count=duplicate_count))
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
    if args.timeout_seconds <= 0:
        print_errors(["--timeout-seconds must be a positive integer."])
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
            Path(args.config),
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
            jobs.extend(source.fetch())
        except SourceError as exc:
            errors.append(f"{source.name}: {exc}")
    return jobs, errors


def enabled_sources(config: Config) -> list[JobSource]:
    sources: list[JobSource] = []
    if config.sources.sample.enabled:
        sources.append(SampleSource())
    if config.sources.local_file.enabled:
        sources.append(LocalFileSource(config.sources.local_file.paths))
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
    return sources


def print_errors(errors: list[str]) -> None:
    print("Errors:", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)


def _optional_path(value: str | None) -> Path | None:
    if value is None:
        return None
    return Path(value).expanduser()


def quickstart_text(config_path: Path) -> str:
    return "\n".join(
        [
            "Next steps:",
            f"  1. Edit {config_path} for your role families, keywords, locations, compensation, and sources.",
            f"  2. Validate it: labor-sieve validate-config -c {config_path}",
            f"  3. Run a scan: labor-sieve run -c {config_path}",
            "  4. Read the full report: output/latest.txt",
            "",
            "Useful setup commands:",
            "  labor-sieve list-presets",
            f"  labor-sieve use-preset linux-sre -c {config_path}",
            "  labor-sieve list-options",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
