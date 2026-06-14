"""Packaged company target catalog."""

from __future__ import annotations

import re
import shutil
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .config import ConfigError, read_yaml_file, validate_config_data, yaml
from .presets import next_backup_path


CATALOG_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
KNOWN_SOURCE_FIELDS = {
    "greenhouse": ("board_token",),
    "lever": ("company",),
    "ashby": ("organization",),
    "workday": ("url",),
}


@dataclass(frozen=True, slots=True)
class CompanyCatalogEntry:
    key: str
    name: str
    tags: tuple[str, ...]
    sources: dict[str, dict[str, str]]
    last_verified: date | None = None
    notes: str = ""


def load_company_catalog(path: Path | None = None) -> list[CompanyCatalogEntry]:
    """Load and validate the packaged or provided company catalog."""
    if yaml is None:
        raise ConfigError(["PyYAML is required. Install with: python -m pip install PyYAML"])
    source = path if path is not None else find_company_catalog()
    if source is None:
        raise ConfigError(["Company catalog could not be found."])
    try:
        loaded = yaml.safe_load(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError([f"{source} could not be read: {exc}"]) from exc
    except yaml.YAMLError as exc:
        raise ConfigError([f"{source} is not valid YAML: {exc}"]) from exc
    return catalog_from_data(loaded)


def find_company_catalog() -> Path | None:
    """Find the catalog in source checkouts or installed package data."""
    candidates = [
        Path(__file__).with_name("company_catalog.yaml"),
        Path(sys.prefix) / "share" / "labor-sieve" / "company_catalog.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def catalog_from_data(data: Any) -> list[CompanyCatalogEntry]:
    errors: list[str] = []
    if not isinstance(data, dict):
        raise ConfigError(["Company catalog must contain a YAML mapping at the top level."])
    companies = data.get("companies")
    if not isinstance(companies, dict):
        raise ConfigError(["companies must be a mapping."])

    entries: list[CompanyCatalogEntry] = []
    for key, raw_entry in companies.items():
        label = f"companies.{key}"
        if not isinstance(key, str) or not CATALOG_ID_RE.fullmatch(key):
            errors.append(f"{label} key must be lowercase letters, numbers, hyphens, or underscores.")
            continue
        if not isinstance(raw_entry, dict):
            errors.append(f"{label} must be a mapping.")
            continue

        name = raw_entry.get("name")
        if not _is_string(name):
            errors.append(f"{label}.name must be a non-empty string.")
            name = key

        raw_tags = raw_entry.get("tags", [])
        if raw_tags is None:
            raw_tags = []
        if not isinstance(raw_tags, list) or not all(_is_string(tag) for tag in raw_tags):
            errors.append(f"{label}.tags must be a list of strings.")
            tags: tuple[str, ...] = ()
        else:
            tags = tuple(_dedupe_strings([str(tag) for tag in raw_tags]))

        raw_sources = raw_entry.get("sources")
        if not isinstance(raw_sources, dict) or not raw_sources:
            errors.append(f"{label}.sources must be a non-empty mapping.")
            sources: dict[str, dict[str, str]] = {}
        else:
            sources = _source_mapping(raw_sources, label, errors)

        if not sources:
            errors.append(f"{label}.sources must contain at least one valid source target.")
        entries.append(
            CompanyCatalogEntry(
                key=key,
                name=str(name),
                tags=tags,
                sources=sources,
                last_verified=_verified_date(raw_entry.get("last_verified"), label, errors),
                notes=str(raw_entry.get("notes") or "").strip(),
            )
        )

    if errors:
        raise ConfigError(errors)
    return sorted(entries, key=lambda entry: entry.name.casefold())


def filter_company_catalog(
    entries: list[CompanyCatalogEntry],
    *,
    source: str | None = None,
    tag: str | None = None,
    search: str | None = None,
    stale_days: int | None = None,
    today: date | None = None,
) -> list[CompanyCatalogEntry]:
    """Filter catalog entries by source, tag, and case-insensitive search text."""
    filtered = entries
    if source:
        source_key = source.casefold()
        filtered = [entry for entry in filtered if source_key in entry.sources]
    if tag:
        tag_key = tag.casefold()
        filtered = [entry for entry in filtered if tag_key in {value.casefold() for value in entry.tags}]
    if search:
        needle = search.casefold()
        filtered = [entry for entry in filtered if needle in _search_text(entry)]
    if stale_days is not None:
        checked_at = today or date.today()
        filtered = [entry for entry in filtered if company_catalog_entry_is_stale(entry, stale_days, checked_at)]
    return filtered


def format_company_entry(entry: CompanyCatalogEntry) -> str:
    tag_text = ", ".join(entry.tags) if entry.tags else "untagged"
    verified_text = entry.last_verified.isoformat() if entry.last_verified is not None else "not verified"
    source_text = "; ".join(
        f"{source}: " + ", ".join(f"{key}={value}" for key, value in values.items())
        for source, values in sorted(entry.sources.items())
    )
    lines = [
        f"{entry.key} - {entry.name} [{tag_text}]",
        f"    verified: {verified_text}",
        f"    {source_text}",
    ]
    if entry.notes:
        lines.append(f"    notes: {entry.notes}")
    return "\n".join(lines)


def company_catalog_entry_is_stale(entry: CompanyCatalogEntry, stale_days: int, today: date) -> bool:
    if entry.last_verified is None:
        return True
    return (today - entry.last_verified).days > stale_days


def enable_catalog_entries_in_config(
    entries: list[CompanyCatalogEntry],
    config_path: Path,
    *,
    source: str | None = None,
) -> tuple[Path, Path | None, list[str]]:
    """Enable catalog entries in a config file and return changed target descriptions."""
    if yaml is None:
        raise ConfigError(["PyYAML is required. Install with: python -m pip install PyYAML"])
    data = read_yaml_file(config_path)
    changed = add_catalog_entries_to_config_data(data, entries, source=source)
    if not changed:
        return config_path, None, []

    errors = validate_config_data(data)
    if errors:
        raise ConfigError([f"Catalog targets would make {config_path} invalid:", *errors])

    backup_path = next_backup_path(config_path)
    try:
        shutil.copyfile(config_path, backup_path)
        header = "# Generated by labor-sieve enable-company. Previous config: " + backup_path.name + "\n"
        config_path.write_text(header + yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    except OSError as exc:
        raise ConfigError([f"{config_path} could not be updated: {exc}"]) from exc
    return config_path, backup_path, changed


def add_catalog_entries_to_config_data(
    data: dict[str, Any],
    entries: list[CompanyCatalogEntry],
    *,
    source: str | None = None,
) -> list[str]:
    sources = data.setdefault("sources", {})
    if not isinstance(sources, dict):
        return []

    changed: list[str] = []
    source_filter = source.casefold() if source else None
    for entry in entries:
        for source_name, values in sorted(entry.sources.items()):
            if source_filter and source_name != source_filter:
                continue
            if source_name == "greenhouse":
                if _append_unique_source_list(sources, source_name, "board_tokens", values["board_token"]):
                    changed.append(f"{entry.key}: greenhouse board_token={values['board_token']}")
            elif source_name == "lever":
                if _append_unique_source_list(sources, source_name, "companies", values["company"]):
                    changed.append(f"{entry.key}: lever company={values['company']}")
            elif source_name == "ashby":
                if _append_unique_source_list(sources, source_name, "organizations", values["organization"]):
                    changed.append(f"{entry.key}: ashby organization={values['organization']}")
            elif source_name == "workday":
                if _append_unique_workday_site(sources, entry.name, values["url"]):
                    changed.append(f"{entry.key}: workday url={values['url']}")
    return changed


def _append_unique_source_list(
    sources: dict[str, Any],
    source_name: str,
    list_key: str,
    value: str,
) -> bool:
    source_config = sources.setdefault(source_name, {})
    if not isinstance(source_config, dict):
        return False
    source_config["enabled"] = True
    raw_values = source_config.setdefault(list_key, [])
    if not isinstance(raw_values, list):
        raw_values = []
        source_config[list_key] = raw_values
    seen = {str(item).casefold() for item in raw_values}
    if value.casefold() in seen:
        return False
    raw_values.append(value)
    return True


def _append_unique_workday_site(sources: dict[str, Any], company: str, url: str) -> bool:
    source_config = sources.setdefault("workday", {})
    if not isinstance(source_config, dict):
        return False
    source_config["enabled"] = True
    raw_sites = source_config.setdefault("sites", [])
    if not isinstance(raw_sites, list):
        raw_sites = []
        source_config["sites"] = raw_sites
    normalized_url = url.casefold().rstrip("/")
    for site in raw_sites:
        if isinstance(site, dict) and str(site.get("url") or "").casefold().rstrip("/") == normalized_url:
            return False
    raw_sites.append({"company": company, "url": url})
    return True


def _source_mapping(
    raw_sources: dict[Any, Any],
    label: str,
    errors: list[str],
) -> dict[str, dict[str, str]]:
    sources: dict[str, dict[str, str]] = {}
    for raw_source, raw_values in raw_sources.items():
        source = str(raw_source).casefold()
        source_label = f"{label}.sources.{source}"
        if source not in KNOWN_SOURCE_FIELDS:
            errors.append(f"{source_label} is not a supported catalog source.")
            continue
        if not isinstance(raw_values, dict):
            errors.append(f"{source_label} must be a mapping.")
            continue
        allowed_fields = KNOWN_SOURCE_FIELDS[source]
        required_field = allowed_fields[0]
        source_values: dict[str, str] = {}
        for field in allowed_fields:
            value = raw_values.get(field)
            if not _is_string(value):
                errors.append(f"{source_label}.{field} must be a non-empty string.")
            else:
                source_values[field] = str(value).strip()
        unexpected = sorted(str(field) for field in raw_values if field not in allowed_fields)
        for field in unexpected:
            errors.append(f"{source_label}.{field} is not supported.")
        if required_field in source_values:
            sources[source] = source_values
    return sources


def _verified_date(value: Any, label: str, errors: list[str]) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    errors.append(f"{label}.last_verified must be an ISO date.")
    return None


def _search_text(entry: CompanyCatalogEntry) -> str:
    values = [entry.key, entry.name, *entry.tags]
    for source, fields in entry.sources.items():
        values.append(source)
        values.extend(fields.values())
    return " ".join(values).casefold()


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for value in values:
        text = value.strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            deduped.append(text)
    return deduped


def _is_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
