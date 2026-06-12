"""Config loading and validation."""

from __future__ import annotations

import re
import shutil
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .taxonomy import ROLE_FAMILIES, SENIORITY_LEVELS, seniority_index

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only in missing dependency installs.
    yaml = None


DEFAULT_CONFIG_EXAMPLE = """# LaborSieve configuration.
# Created by labor-sieve quickstart or labor-sieve init.

# Ordered seniority values:
# entry, junior, mid, senior, staff, principal, executive
seniority:
  min: mid
  max: staff
  allow_principal: false
  allow_executive: false

# Built-in role family values:
# sre_infra_ops, data_center_ops, fleet_reliability, platform_ops,
# implementation_support, logistics_process, customer_operations,
# software_engineering, architect, management, unknown
#
# Custom snake_case role families are valid. The scorer uses the configured
# weight for matching role_family values emitted by sources or presets.
role_family_weights:
  sre_infra_ops: 1.00
  data_center_ops: 0.95
  fleet_reliability: 0.90
  platform_ops: 0.88
  implementation_support: 0.45
  logistics_process: 0.75
  customer_operations: 0.50
  architect: 0.35
  management: 0.15
  software_engineering: 0.10
  unknown: 0.05

keywords:
  boost:
    - linux
    - production operations
    - incident response
    - sre
    - reliability
    - automation
    - capacity planning
    - data center
    - fleet
    - hardware
    - logistics
    - process improvement
    - implementation
    - customer support
    - troubleshooting
  penalize:
    - frontend
    - full-stack
    - mobile app
    - software engineer
    - sales engineer
    - applied scientist
    - data scientist
    - research scientist
    - leetcode
    - product engineering
    - manager
    - director
    - vp
    - head of
    - people management

locations:
  remote: true
  # Local region is documentation for the search area. LaborSieve does not
  # geocode; edit accepted_locations to control which local postings match.
  local_region:
    center: Richmond, VA
    radius_miles: 40
  accepted_locations:
    - Richmond, VA
    - Henrico, VA
    - Glen Allen, VA
    - Short Pump, VA
    - Mechanicsville, VA
    - Ashland, VA
    - Midlothian, VA
    - Chesterfield, VA
    - Chester, VA
    - Colonial Heights, VA
    - Petersburg, VA
    - Hopewell, VA
    - Powhatan, VA
    - Goochland, VA
    - Sandston, VA
    - Highland Springs, VA
    - Bon Air, VA
    - Tuckahoe, VA
  # Remote jobs are accepted when the location is generic remote or matches
  # one of these strings. Remote jobs restricted to other geographies are capped.
  accepted_remote_locations:
    - United States
    - United States of America
    - USA
    - U.S.
    - US
    - North America

compensation:
  minimum_base: 115000

output:
  directory: output
  txt: true
  csv: true
  json: true
  html: true
  terminal_p0_limit: 10
  terminal_p1_limit: 15

sources:
  sample:
    enabled: false
  local_file:
    enabled: false
    paths: []
  # Broad public source for remote roles across many companies.
  remoteok:
    enabled: true
    timeout_seconds: 20
    max_jobs: 250
    base_url: https://remoteok.com/api
  # Broad public source with international roles. Disabled by default because
  # it is much noisier for a US-centered search.
  arbeitnow:
    enabled: false
    timeout_seconds: 20
    max_pages: 1
    max_jobs: 100
    base_url: https://www.arbeitnow.com/api/job-board-api
  greenhouse:
    enabled: true
    board_tokens:
      - cloudflare
      - canonical
      - coreweave
      - samsara
    timeout_seconds: 20
  lever:
    enabled: true
    companies:
      - palantir
    timeout_seconds: 20
    base_url: https://api.lever.co/v0/postings
  ashby:
    enabled: true
    organizations:
      - Lambda
      - Crusoe
      - Modal
      - openai
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
"""


class ConfigError(Exception):
    """Raised when config loading or validation fails."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass(slots=True)
class SeniorityConfig:
    min: str
    max: str
    allow_principal: bool
    allow_executive: bool


@dataclass(slots=True)
class KeywordConfig:
    boost: list[str]
    penalize: list[str]


@dataclass(slots=True)
class LocalRegionConfig:
    center: str
    radius_miles: int


@dataclass(slots=True)
class LocationConfig:
    remote: bool
    local_region: LocalRegionConfig
    accepted_locations: list[str]
    accepted_remote_locations: list[str]


@dataclass(slots=True)
class CompensationConfig:
    minimum_base: int | None


@dataclass(slots=True)
class OutputConfig:
    directory: str
    txt: bool
    csv: bool
    json: bool
    html: bool
    terminal_p0_limit: int
    terminal_p1_limit: int


@dataclass(slots=True)
class SampleSourceConfig:
    enabled: bool


@dataclass(slots=True)
class LocalFileSourceConfig:
    enabled: bool
    paths: list[str]


@dataclass(slots=True)
class RemoteOkSourceConfig:
    enabled: bool
    timeout_seconds: int
    max_jobs: int
    base_url: str


@dataclass(slots=True)
class ArbeitnowSourceConfig:
    enabled: bool
    timeout_seconds: int
    max_pages: int
    max_jobs: int
    base_url: str


@dataclass(slots=True)
class GreenhouseSourceConfig:
    enabled: bool
    board_tokens: list[str]
    timeout_seconds: int


@dataclass(slots=True)
class LeverSourceConfig:
    enabled: bool
    companies: list[str]
    timeout_seconds: int
    base_url: str


@dataclass(slots=True)
class AshbySourceConfig:
    enabled: bool
    organizations: list[str]
    timeout_seconds: int
    base_url: str


@dataclass(slots=True)
class WorkdaySiteConfig:
    company: str
    url: str


@dataclass(slots=True)
class WorkdaySourceConfig:
    enabled: bool
    sites: list[WorkdaySiteConfig]
    timeout_seconds: int
    page_size: int
    max_jobs_per_site: int


@dataclass(slots=True)
class SourceConfig:
    sample: SampleSourceConfig
    local_file: LocalFileSourceConfig
    remoteok: RemoteOkSourceConfig
    arbeitnow: ArbeitnowSourceConfig
    greenhouse: GreenhouseSourceConfig
    lever: LeverSourceConfig
    ashby: AshbySourceConfig
    workday: WorkdaySourceConfig


@dataclass(slots=True)
class Config:
    seniority: SeniorityConfig
    role_family_weights: dict[str, float]
    keywords: KeywordConfig
    locations: LocationConfig
    compensation: CompensationConfig
    output: OutputConfig
    sources: SourceConfig


@dataclass(slots=True)
class ConfigUpgradeResult:
    path: Path
    changed: bool
    backup_path: Path | None
    added_paths: list[str]


ROLE_FAMILY_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def init_config(destination: Path = Path("config.yaml"), *, overwrite: bool = False) -> str:
    """Create a config file from the example when one does not already exist."""
    destination = destination.expanduser()
    display_path = destination.resolve(strict=False)
    if destination.exists() and not overwrite:
        return f"{display_path} already exists; leaving it unchanged."

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        backup_path = None
        if destination.exists():
            backup_path = next_backup_path(destination)
            shutil.copy2(destination, backup_path)
        source = find_config_example()
        if source is not None and source.resolve(strict=False) != display_path:
            shutil.copyfile(source, destination)
        else:
            destination.write_text(DEFAULT_CONFIG_EXAMPLE, encoding="utf-8")
    except OSError as exc:
        raise ConfigError([f"{display_path} could not be created: {exc}"]) from exc
    if backup_path is not None:
        return f"Replaced {display_path} with default commented settings. Backup written to {backup_path}."
    return f"Created {display_path} with default commented settings."


def next_backup_path(path: Path) -> Path:
    backup_path = path.with_name(path.name + ".bak")
    index = 1
    while backup_path.exists():
        backup_path = path.with_name(f"{path.name}.bak.{index}")
        index += 1
    return backup_path


def upgrade_config(path: Path = Path("config.yaml")) -> ConfigUpgradeResult:
    """Add missing default config settings without changing existing values."""
    path = path.expanduser()
    display_path = path.resolve(strict=False)
    data = read_yaml_file(path)
    default_data = read_default_config_data()
    added_paths = missing_default_paths(data, default_data)
    if not added_paths:
        return ConfigUpgradeResult(display_path, changed=False, backup_path=None, added_paths=[])

    merged = merge_missing_defaults(data, default_data)
    try:
        current_text = path.read_text(encoding="utf-8")
        upgraded_text = render_upgraded_config_text(current_text, merged, added_paths)
        backup_path = next_backup_path(path)
        shutil.copy2(path, backup_path)
        path.write_text(upgraded_text, encoding="utf-8")
    except OSError as exc:
        raise ConfigError([f"{display_path} could not be upgraded: {exc}"]) from exc
    return ConfigUpgradeResult(
        display_path,
        changed=True,
        backup_path=backup_path.resolve(strict=False),
        added_paths=added_paths,
    )


def read_default_config_data() -> dict[str, Any]:
    if yaml is None:
        raise ConfigError(["PyYAML is required. Install with: python -m pip install PyYAML"])
    source = find_config_example()
    try:
        if source is not None:
            loaded = yaml.safe_load(source.read_text(encoding="utf-8"))
        else:
            loaded = yaml.safe_load(DEFAULT_CONFIG_EXAMPLE)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError([f"Default config could not be read: {exc}"]) from exc
    if not isinstance(loaded, dict):
        raise ConfigError(["Default config must contain a YAML mapping at the top level."])
    return loaded


def missing_default_paths(data: dict[str, Any], defaults: dict[str, Any]) -> list[str]:
    missing: list[str] = []

    def visit(current: Any, default: Any, prefix: list[str]) -> None:
        if not isinstance(default, dict):
            return
        if not isinstance(current, dict):
            return
        for key, default_value in default.items():
            path = [*prefix, str(key)]
            if key not in current:
                missing.append(".".join(path))
            elif isinstance(default_value, dict):
                visit(current[key], default_value, path)

    visit(data, defaults, [])
    return missing


def merge_missing_defaults(data: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(data)

    def merge(current: dict[str, Any], default: dict[str, Any]) -> None:
        for key, default_value in default.items():
            if key not in current:
                current[key] = deepcopy(default_value)
            elif isinstance(current[key], dict) and isinstance(default_value, dict):
                merge(current[key], default_value)

    merge(merged, defaults)
    return merged


def render_upgraded_config_text(
    current_text: str,
    merged: dict[str, Any],
    added_paths: list[str],
) -> str:
    default_text = default_config_text()
    upgraded_text = current_text
    for path in added_paths:
        snippet = extract_default_block(default_text, path.split("."))
        if snippet is None:
            return yaml.safe_dump(merged, sort_keys=False)
        upgraded_text = insert_config_block(upgraded_text, path.split("."), snippet)
        if upgraded_text is None:
            return yaml.safe_dump(merged, sort_keys=False)
    try:
        loaded = yaml.safe_load(upgraded_text)
    except yaml.YAMLError:
        return yaml.safe_dump(merged, sort_keys=False)
    if not isinstance(loaded, dict) or missing_default_paths(loaded, merged):
        return yaml.safe_dump(merged, sort_keys=False)
    if not upgraded_text.endswith("\n"):
        upgraded_text += "\n"
    return upgraded_text


def default_config_text() -> str:
    source = find_config_example()
    if source is not None:
        try:
            return source.read_text(encoding="utf-8")
        except OSError:
            return DEFAULT_CONFIG_EXAMPLE
    return DEFAULT_CONFIG_EXAMPLE


def extract_default_block(default_text: str, path: list[str]) -> str | None:
    lines = default_text.splitlines()
    located = find_key_line(lines, path)
    if located is None:
        return None
    key_line, _ = located
    indent = 2 * (len(path) - 1)
    start = key_line
    while start > 0 and is_associated_comment(lines[start - 1], indent):
        start -= 1
    end = key_line + 1
    while end < len(lines):
        stripped = lines[end].strip()
        if stripped and line_indent(lines[end]) <= indent:
            break
        end += 1
    snippet = "\n".join(lines[start:end]).strip("\n")
    if not snippet:
        return None
    return snippet + "\n"


def insert_config_block(text: str, path: list[str], snippet: str) -> str | None:
    lines = text.splitlines()
    if len(path) == 1:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(snippet.rstrip("\n").splitlines())
        return "\n".join(lines) + "\n"

    parent = path[:-1]
    located = find_key_line(lines, parent)
    if located is None:
        return None
    _, parent_end = located
    insert_lines = snippet.rstrip("\n").splitlines()
    before = lines[:parent_end]
    after = lines[parent_end:]
    if before and before[-1].strip():
        before.append("")
    return "\n".join([*before, *insert_lines, *after]) + "\n"


def find_key_line(lines: list[str], path: list[str]) -> tuple[int, int] | None:
    start = 0
    end = len(lines)
    key_line = None
    for depth, key in enumerate(path):
        indent = 2 * depth
        key_line = None
        for index in range(start, end):
            if is_key_line(lines[index], key, indent):
                key_line = index
                break
        if key_line is None:
            return None
        start = key_line + 1
        end = find_block_end(lines, key_line, indent)
    return key_line, end


def find_block_end(lines: list[str], key_line: int, indent: int) -> int:
    index = key_line + 1
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped and line_indent(lines[index]) <= indent:
            break
        index += 1
    return index


def is_key_line(line: str, key: str, indent: int) -> bool:
    prefix = " " * indent + key + ":"
    return line.startswith(prefix)


def is_associated_comment(line: str, indent: int) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    return line_indent(line) == indent and stripped.startswith("#")


def line_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def find_config_example() -> Path | None:
    """Find config.example.yaml in source or installed package data locations."""
    candidates = [
        Path(__file__).resolve().parents[1] / "config.example.yaml",
        Path(sys.prefix) / "share" / "labor-sieve" / "config.example.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_config(path: Path = Path("config.yaml")) -> Config:
    """Load and validate config.yaml."""
    data = read_yaml_file(path)
    errors = validate_config_data(data)
    if errors:
        raise ConfigError(errors)
    return config_from_data(data)


def read_yaml_file(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise ConfigError(["PyYAML is required. Install with: python -m pip install PyYAML"])
    if not path.exists():
        raise ConfigError([f"{path} not found. Run: labor-sieve init"])
    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
    except OSError as exc:
        raise ConfigError([f"{path} could not be read: {exc}"]) from exc
    except yaml.YAMLError as exc:
        raise ConfigError([f"{path} is not valid YAML: {exc}"]) from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigError([f"{path} must contain a YAML mapping at the top level."])
    return loaded


def validate_config_data(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Config must be a YAML mapping."]

    seniority = _require_mapping(data, "seniority", errors)
    if seniority is not None:
        min_value = seniority.get("min")
        max_value = seniority.get("max")
        if not _is_string(min_value):
            errors.append("seniority.min must be one of: " + ", ".join(SENIORITY_LEVELS))
        elif min_value not in SENIORITY_LEVELS:
            errors.append(f"seniority.min has unsupported value {min_value!r}.")
        if not _is_string(max_value):
            errors.append("seniority.max must be one of: " + ", ".join(SENIORITY_LEVELS))
        elif max_value not in SENIORITY_LEVELS:
            errors.append(f"seniority.max has unsupported value {max_value!r}.")
        if min_value in SENIORITY_LEVELS and max_value in SENIORITY_LEVELS:
            if seniority_index(min_value) > seniority_index(max_value):
                errors.append("seniority.min must not be higher than seniority.max.")
        _require_bool(seniority, "allow_principal", "seniority.allow_principal", errors)
        _require_bool(seniority, "allow_executive", "seniority.allow_executive", errors)

    weights = _require_mapping(data, "role_family_weights", errors)
    if weights is not None:
        if not weights:
            errors.append("role_family_weights must contain at least one role family.")
        for role_family, weight in weights.items():
            if not isinstance(role_family, str) or not ROLE_FAMILY_NAME_RE.fullmatch(role_family):
                errors.append(
                    "role_family_weights keys must be snake_case strings "
                    f"(got {role_family!r})."
                )
            if not isinstance(weight, int | float) or isinstance(weight, bool):
                errors.append(f"role_family_weights.{role_family} must be a number from 0.0 to 1.0.")
            elif not 0 <= float(weight) <= 1:
                errors.append(f"role_family_weights.{role_family} must be between 0.0 and 1.0.")
        if "unknown" not in weights:
            errors.append("role_family_weights should include unknown as a fallback weight.")

    keywords = _require_mapping(data, "keywords", errors)
    if keywords is not None:
        _require_string_list(keywords, "boost", "keywords.boost", errors)
        _require_string_list(keywords, "penalize", "keywords.penalize", errors)

    locations = _require_mapping(data, "locations", errors)
    if locations is not None:
        _require_bool(locations, "remote", "locations.remote", errors)
        local_region = _optional_mapping(locations, "local_region", errors, label="locations.local_region")
        if local_region is not None:
            if not _is_string(local_region.get("center")):
                errors.append("locations.local_region.center must be a non-empty string.")
            radius = local_region.get("radius_miles")
            if not isinstance(radius, int) or isinstance(radius, bool) or radius <= 0:
                errors.append("locations.local_region.radius_miles must be a positive integer.")
        if "accepted_locations" in locations:
            _require_string_list(
                locations,
                "accepted_locations",
                "locations.accepted_locations",
                errors,
            )
        if "hybrid_locations" in locations:
            _require_string_list(
                locations,
                "hybrid_locations",
                "locations.hybrid_locations",
                errors,
            )
        if "accepted_locations" not in locations and "hybrid_locations" not in locations:
            errors.append("locations.accepted_locations must be a list of strings.")
        if "accepted_remote_locations" in locations:
            _require_string_list(
                locations,
                "accepted_remote_locations",
                "locations.accepted_remote_locations",
                errors,
            )

    compensation = _require_mapping(data, "compensation", errors)
    if compensation is not None:
        minimum = compensation.get("minimum_base")
        if minimum is not None:
            if not isinstance(minimum, int | float) or isinstance(minimum, bool):
                errors.append("compensation.minimum_base must be a non-negative number or null.")
            elif minimum < 0:
                errors.append("compensation.minimum_base must be a non-negative number or null.")

    output = _require_mapping(data, "output", errors)
    if output is not None:
        if not _is_string(output.get("directory")):
            errors.append("output.directory must be a path string.")
        for key in ("txt", "csv", "json", "html"):
            _require_bool(output, key, f"output.{key}", errors)
        for key in ("terminal_p0_limit", "terminal_p1_limit"):
            value = output.get(key)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                errors.append(f"output.{key} must be a non-negative integer.")

    sources = _require_mapping(data, "sources", errors)
    if sources is not None:
        sample = _require_mapping(sources, "sample", errors, label="sources.sample")
        if sample is not None:
            _require_bool(sample, "enabled", "sources.sample.enabled", errors)
        local_file = _optional_mapping(sources, "local_file", errors, label="sources.local_file")
        if local_file is not None:
            _require_bool(local_file, "enabled", "sources.local_file.enabled", errors)
            _require_string_list(local_file, "paths", "sources.local_file.paths", errors)
        remoteok = _optional_mapping(sources, "remoteok", errors, label="sources.remoteok")
        if remoteok is not None:
            _require_bool(remoteok, "enabled", "sources.remoteok.enabled", errors)
            _require_positive_int(remoteok, "timeout_seconds", "sources.remoteok.timeout_seconds", errors)
            _require_int_range(remoteok, "max_jobs", "sources.remoteok.max_jobs", 1, 5000, errors)
            _require_https_url(remoteok, "base_url", "sources.remoteok.base_url", errors)
        arbeitnow = _optional_mapping(sources, "arbeitnow", errors, label="sources.arbeitnow")
        if arbeitnow is not None:
            _require_bool(arbeitnow, "enabled", "sources.arbeitnow.enabled", errors)
            _require_positive_int(arbeitnow, "timeout_seconds", "sources.arbeitnow.timeout_seconds", errors)
            _require_int_range(arbeitnow, "max_pages", "sources.arbeitnow.max_pages", 1, 20, errors)
            _require_int_range(arbeitnow, "max_jobs", "sources.arbeitnow.max_jobs", 1, 5000, errors)
            _require_https_url(arbeitnow, "base_url", "sources.arbeitnow.base_url", errors)
        greenhouse = _optional_mapping(sources, "greenhouse", errors, label="sources.greenhouse")
        if greenhouse is not None:
            _require_bool(greenhouse, "enabled", "sources.greenhouse.enabled", errors)
            _require_string_list(
                greenhouse,
                "board_tokens",
                "sources.greenhouse.board_tokens",
                errors,
            )
            _require_positive_int(greenhouse, "timeout_seconds", "sources.greenhouse.timeout_seconds", errors)
        lever = _optional_mapping(sources, "lever", errors, label="sources.lever")
        if lever is not None:
            _require_bool(lever, "enabled", "sources.lever.enabled", errors)
            _require_string_list(lever, "companies", "sources.lever.companies", errors)
            _require_positive_int(lever, "timeout_seconds", "sources.lever.timeout_seconds", errors)
            _require_https_url(lever, "base_url", "sources.lever.base_url", errors)
        ashby = _optional_mapping(sources, "ashby", errors, label="sources.ashby")
        if ashby is not None:
            _require_bool(ashby, "enabled", "sources.ashby.enabled", errors)
            _require_string_list(ashby, "organizations", "sources.ashby.organizations", errors)
            _require_positive_int(ashby, "timeout_seconds", "sources.ashby.timeout_seconds", errors)
            _require_https_url(ashby, "base_url", "sources.ashby.base_url", errors)
        workday = _optional_mapping(sources, "workday", errors, label="sources.workday")
        if workday is not None:
            _require_bool(workday, "enabled", "sources.workday.enabled", errors)
            _require_workday_sites(workday, errors)
            _require_positive_int(workday, "timeout_seconds", "sources.workday.timeout_seconds", errors)
            _require_int_range(workday, "page_size", "sources.workday.page_size", 1, 100, errors)
            _require_int_range(
                workday,
                "max_jobs_per_site",
                "sources.workday.max_jobs_per_site",
                1,
                5000,
                errors,
            )

    return errors


def config_from_data(data: dict[str, Any]) -> Config:
    seniority = data["seniority"]
    keywords = data["keywords"]
    locations = data["locations"]
    compensation = data["compensation"]
    output = data["output"]
    sources = data["sources"]
    sample = sources["sample"]
    local_file = sources.get("local_file", {})
    remoteok = sources.get("remoteok", {})
    arbeitnow = sources.get("arbeitnow", {})
    greenhouse = sources.get("greenhouse", {})
    lever = sources.get("lever", {})
    ashby = sources.get("ashby", {})
    workday = sources.get("workday", {})
    return Config(
        seniority=SeniorityConfig(
            min=seniority["min"],
            max=seniority["max"],
            allow_principal=bool(seniority["allow_principal"]),
            allow_executive=bool(seniority["allow_executive"]),
        ),
        role_family_weights={key: float(value) for key, value in data["role_family_weights"].items()},
        keywords=KeywordConfig(
            boost=[str(value) for value in keywords["boost"]],
            penalize=[str(value) for value in keywords["penalize"]],
        ),
        locations=LocationConfig(
            remote=bool(locations["remote"]),
            local_region=LocalRegionConfig(
                center=str(locations.get("local_region", {}).get("center", "Richmond, VA")),
                radius_miles=int(locations.get("local_region", {}).get("radius_miles", 40)),
            ),
            accepted_locations=_location_strings(locations),
            accepted_remote_locations=_remote_location_strings(locations),
        ),
        compensation=CompensationConfig(
            minimum_base=(
                None
                if compensation.get("minimum_base") is None
                else int(compensation["minimum_base"])
            ),
        ),
        output=OutputConfig(
            directory=str(output["directory"]),
            txt=bool(output["txt"]),
            csv=bool(output["csv"]),
            json=bool(output["json"]),
            html=bool(output["html"]),
            terminal_p0_limit=int(output.get("terminal_p0_limit", 10)),
            terminal_p1_limit=int(output.get("terminal_p1_limit", 15)),
        ),
        sources=SourceConfig(
            sample=SampleSourceConfig(enabled=bool(sample["enabled"])),
            local_file=LocalFileSourceConfig(
                enabled=bool(local_file.get("enabled", False)),
                paths=[str(value) for value in local_file.get("paths", [])],
            ),
            remoteok=RemoteOkSourceConfig(
                enabled=bool(remoteok.get("enabled", False)),
                timeout_seconds=int(remoteok.get("timeout_seconds", 20)),
                max_jobs=int(remoteok.get("max_jobs", 250)),
                base_url=str(remoteok.get("base_url", "https://remoteok.com/api")),
            ),
            arbeitnow=ArbeitnowSourceConfig(
                enabled=bool(arbeitnow.get("enabled", False)),
                timeout_seconds=int(arbeitnow.get("timeout_seconds", 20)),
                max_pages=int(arbeitnow.get("max_pages", 1)),
                max_jobs=int(arbeitnow.get("max_jobs", 100)),
                base_url=str(arbeitnow.get("base_url", "https://www.arbeitnow.com/api/job-board-api")),
            ),
            greenhouse=GreenhouseSourceConfig(
                enabled=bool(greenhouse.get("enabled", False)),
                board_tokens=[str(value) for value in greenhouse.get("board_tokens", [])],
                timeout_seconds=int(greenhouse.get("timeout_seconds", 20)),
            ),
            lever=LeverSourceConfig(
                enabled=bool(lever.get("enabled", False)),
                companies=[str(value) for value in lever.get("companies", [])],
                timeout_seconds=int(lever.get("timeout_seconds", 20)),
                base_url=str(lever.get("base_url", "https://api.lever.co/v0/postings")),
            ),
            ashby=AshbySourceConfig(
                enabled=bool(ashby.get("enabled", False)),
                organizations=[str(value) for value in ashby.get("organizations", [])],
                timeout_seconds=int(ashby.get("timeout_seconds", 20)),
                base_url=str(ashby.get("base_url", "https://api.ashbyhq.com/posting-api/job-board")),
            ),
            workday=WorkdaySourceConfig(
                enabled=bool(workday.get("enabled", False)),
                sites=[
                    WorkdaySiteConfig(company=str(site["company"]), url=str(site["url"]))
                    for site in workday.get("sites", [])
                ],
                timeout_seconds=int(workday.get("timeout_seconds", 20)),
                page_size=int(workday.get("page_size", 20)),
                max_jobs_per_site=int(workday.get("max_jobs_per_site", 100)),
            ),
        ),
    )


def built_in_options_text() -> str:
    lines = [
        "Seniority levels, ordered low to high:",
        "  " + ", ".join(SENIORITY_LEVELS),
        "",
        "Built-in role families:",
        "  " + ", ".join(ROLE_FAMILIES),
        "",
        "Custom snake_case role_family_weights are valid.",
    ]
    return "\n".join(lines)


def _location_strings(locations: dict[str, Any]) -> list[str]:
    values = []
    for key in ("accepted_locations", "hybrid_locations"):
        raw_values = locations.get(key, [])
        if isinstance(raw_values, list):
            values.extend(str(value) for value in raw_values)
    return _dedupe_strings(values)


def _remote_location_strings(locations: dict[str, Any]) -> list[str]:
    raw_values = locations.get("accepted_remote_locations", [])
    if isinstance(raw_values, list):
        return _dedupe_strings([str(value) for value in raw_values])
    return []


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for value in values:
        text = str(value).strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            deduped.append(text)
    return deduped


def _require_mapping(
    mapping: dict[str, Any],
    key: str,
    errors: list[str],
    label: str | None = None,
) -> dict[str, Any] | None:
    value = mapping.get(key)
    display = label or key
    if not isinstance(value, dict):
        errors.append(f"{display} must be a mapping.")
        return None
    return value


def _optional_mapping(
    mapping: dict[str, Any],
    key: str,
    errors: list[str],
    label: str | None = None,
) -> dict[str, Any] | None:
    value = mapping.get(key)
    if value is None:
        return None
    display = label or key
    if not isinstance(value, dict):
        errors.append(f"{display} must be a mapping.")
        return None
    return value


def _require_bool(mapping: dict[str, Any], key: str, label: str, errors: list[str]) -> None:
    if not isinstance(mapping.get(key), bool):
        errors.append(f"{label} must be true or false.")


def _require_string_list(
    mapping: dict[str, Any],
    key: str,
    label: str,
    errors: list[str],
) -> None:
    value = mapping.get(key)
    if not isinstance(value, list) or not all(_is_string(item) for item in value):
        errors.append(f"{label} must be a list of strings.")


def _require_positive_int(mapping: dict[str, Any], key: str, label: str, errors: list[str]) -> None:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        errors.append(f"{label} must be a positive integer.")


def _require_int_range(
    mapping: dict[str, Any],
    key: str,
    label: str,
    minimum: int,
    maximum: int,
    errors: list[str],
) -> None:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        errors.append(f"{label} must be an integer from {minimum} to {maximum}.")


def _require_https_url(mapping: dict[str, Any], key: str, label: str, errors: list[str]) -> None:
    if not _is_string(mapping.get(key)):
        errors.append(f"{label} must be a URL string.")
    elif not str(mapping[key]).startswith("https://"):
        errors.append(f"{label} must start with https://.")


def _require_workday_sites(mapping: dict[str, Any], errors: list[str]) -> None:
    sites = mapping.get("sites")
    if not isinstance(sites, list):
        errors.append("sources.workday.sites must be a list of mappings.")
        return
    for index, site in enumerate(sites):
        label = f"sources.workday.sites[{index}]"
        if not isinstance(site, dict):
            errors.append(f"{label} must be a mapping.")
            continue
        company = site.get("company")
        url = site.get("url")
        if not _is_string(company):
            errors.append(f"{label}.company must be a non-empty string.")
        if not _is_string(url):
            errors.append(f"{label}.url must be a URL string.")
        elif not _is_workday_url(str(url)):
            errors.append(f"{label}.url must be an https://*.myworkdayjobs.com URL.")


def _is_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_workday_url(value: str) -> bool:
    parsed = urlsplit(value.strip())
    host = parsed.hostname.casefold() if parsed.hostname else ""
    try:
        port = parsed.port
    except ValueError:
        return False
    if parsed.username or parsed.password or port is not None:
        return False
    if parsed.scheme != "https" or not host.endswith(".myworkdayjobs.com"):
        return False
    return bool([part for part in parsed.path.split("/") if part])
