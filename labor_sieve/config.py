"""Config loading and validation."""

from __future__ import annotations

import re
import shutil
import sys
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
    - leetcode
    - product engineering
    - director
    - vp
    - head of
    - people management

locations:
  remote: true
  hybrid_locations:
    - San Francisco Bay Area
    - Seattle
    - Austin

compensation:
  minimum_base: 115000

output:
  directory: output
  txt: true
  csv: true
  json: true
  html: true

sources:
  sample:
    enabled: true
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
    timeout_seconds: 20
    base_url: https://api.ashbyhq.com/posting-api/job-board
  workday:
    enabled: false
    sites: []
    timeout_seconds: 20
    page_size: 20
    max_jobs_per_site: 200
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
class LocationConfig:
    remote: bool
    hybrid_locations: list[str]


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


@dataclass(slots=True)
class SampleSourceConfig:
    enabled: bool


@dataclass(slots=True)
class LocalFileSourceConfig:
    enabled: bool
    paths: list[str]


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


ROLE_FAMILY_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def init_config(destination: Path = Path("config.yaml")) -> str:
    """Create a config file from the example when one does not already exist."""
    destination = destination.expanduser()
    display_path = destination.resolve(strict=False)
    if destination.exists():
        return f"{display_path} already exists; leaving it unchanged."

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = find_config_example()
        if source is not None:
            shutil.copyfile(source, destination)
        else:
            destination.write_text(DEFAULT_CONFIG_EXAMPLE, encoding="utf-8")
    except OSError as exc:
        raise ConfigError([f"{display_path} could not be created: {exc}"]) from exc
    return f"Created {display_path} with default commented settings."


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
        _require_string_list(locations, "hybrid_locations", "locations.hybrid_locations", errors)

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

    sources = _require_mapping(data, "sources", errors)
    if sources is not None:
        sample = _require_mapping(sources, "sample", errors, label="sources.sample")
        if sample is not None:
            _require_bool(sample, "enabled", "sources.sample.enabled", errors)
        local_file = _optional_mapping(sources, "local_file", errors, label="sources.local_file")
        if local_file is not None:
            _require_bool(local_file, "enabled", "sources.local_file.enabled", errors)
            _require_string_list(local_file, "paths", "sources.local_file.paths", errors)
        greenhouse = _optional_mapping(sources, "greenhouse", errors, label="sources.greenhouse")
        if greenhouse is not None:
            _require_bool(greenhouse, "enabled", "sources.greenhouse.enabled", errors)
            _require_string_list(
                greenhouse,
                "board_tokens",
                "sources.greenhouse.board_tokens",
                errors,
            )
            timeout = greenhouse.get("timeout_seconds")
            if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
                errors.append("sources.greenhouse.timeout_seconds must be a positive integer.")
        lever = _optional_mapping(sources, "lever", errors, label="sources.lever")
        if lever is not None:
            _require_bool(lever, "enabled", "sources.lever.enabled", errors)
            _require_string_list(lever, "companies", "sources.lever.companies", errors)
            timeout = lever.get("timeout_seconds")
            if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
                errors.append("sources.lever.timeout_seconds must be a positive integer.")
            if not _is_string(lever.get("base_url")):
                errors.append("sources.lever.base_url must be a URL string.")
            elif not str(lever["base_url"]).startswith("https://"):
                errors.append("sources.lever.base_url must start with https://.")
        ashby = _optional_mapping(sources, "ashby", errors, label="sources.ashby")
        if ashby is not None:
            _require_bool(ashby, "enabled", "sources.ashby.enabled", errors)
            _require_string_list(ashby, "organizations", "sources.ashby.organizations", errors)
            timeout = ashby.get("timeout_seconds")
            if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
                errors.append("sources.ashby.timeout_seconds must be a positive integer.")
            if not _is_string(ashby.get("base_url")):
                errors.append("sources.ashby.base_url must be a URL string.")
            elif not str(ashby["base_url"]).startswith("https://"):
                errors.append("sources.ashby.base_url must start with https://.")
        workday = _optional_mapping(sources, "workday", errors, label="sources.workday")
        if workday is not None:
            _require_bool(workday, "enabled", "sources.workday.enabled", errors)
            _require_workday_sites(workday, errors)
            timeout = workday.get("timeout_seconds")
            if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
                errors.append("sources.workday.timeout_seconds must be a positive integer.")
            page_size = workday.get("page_size")
            if (
                not isinstance(page_size, int)
                or isinstance(page_size, bool)
                or not 1 <= page_size <= 100
            ):
                errors.append("sources.workday.page_size must be an integer from 1 to 100.")
            max_jobs = workday.get("max_jobs_per_site")
            if (
                not isinstance(max_jobs, int)
                or isinstance(max_jobs, bool)
                or not 1 <= max_jobs <= 5000
            ):
                errors.append("sources.workday.max_jobs_per_site must be an integer from 1 to 5000.")

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
            hybrid_locations=[str(value) for value in locations["hybrid_locations"]],
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
        ),
        sources=SourceConfig(
            sample=SampleSourceConfig(enabled=bool(sample["enabled"])),
            local_file=LocalFileSourceConfig(
                enabled=bool(local_file.get("enabled", False)),
                paths=[str(value) for value in local_file.get("paths", [])],
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
                max_jobs_per_site=int(workday.get("max_jobs_per_site", 200)),
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
