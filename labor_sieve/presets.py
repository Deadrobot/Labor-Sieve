"""Preset discovery, remote updates, and config application."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .net import MAX_PRESET_BYTES, ResponseTooLargeError, read_response_limited
from .config import ConfigError, read_yaml_file, validate_config_data, yaml


PRESET_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
CONFIG_FRAGMENT_KEYS = {
    "seniority",
    "role_family_weights",
    "keywords",
    "locations",
    "compensation",
    "output",
    "sources",
}


class PresetError(Exception):
    """Raised when preset discovery, update, or application fails."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass(slots=True)
class PresetInfo:
    name: str
    description: str
    version: str | None
    path: Path
    source: str


@dataclass(slots=True)
class PresetUpdateResult:
    name: str
    path: Path | None
    verified: bool
    skipped: bool
    message: str


def default_user_preset_dir() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home).expanduser() / "labor-sieve" / "presets"
    return Path.home() / ".config" / "labor-sieve" / "presets"


def bundled_preset_dirs() -> list[Path]:
    package_root = Path(__file__).resolve().parents[1]
    candidates = [
        package_root / "presets",
        Path(sys.prefix) / "share" / "labor-sieve" / "presets",
    ]
    directories: list[Path] = []
    seen = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            directories.append(candidate)
    return directories


def list_presets(preset_dir: Path | None = None) -> list[PresetInfo]:
    """Return presets, with downloaded presets overriding bundled presets by name."""
    by_name: dict[str, PresetInfo] = {}
    for directory in bundled_preset_dirs():
        for path in sorted(directory.glob("*.yaml")):
            info = load_preset_info(path, source="bundled")
            by_name.setdefault(info.name, info)

    user_dir = preset_dir or default_user_preset_dir()
    for path in sorted(user_dir.glob("*.yaml")):
        info = load_preset_info(path, source="downloaded")
        by_name[info.name] = info

    return [by_name[name] for name in sorted(by_name)]


def find_preset(name: str, preset_dir: Path | None = None) -> PresetInfo:
    for preset in list_presets(preset_dir):
        if preset.name == name:
            return preset
    raise PresetError([f"Preset {name!r} was not found. Run: labor-sieve list-presets"])


def load_preset_info(path: Path, source: str) -> PresetInfo:
    data = read_yaml_file(path)
    name = str(data.get("name") or path.stem).strip()
    if not PRESET_NAME_RE.fullmatch(name):
        raise PresetError([f"{path}: preset name must match {PRESET_NAME_RE.pattern}."])
    description = str(data.get("description") or "").strip()
    version_value = data.get("version")
    version = None if version_value in (None, "") else str(version_value)
    return PresetInfo(
        name=name,
        description=description,
        version=version,
        path=path,
        source=source,
    )


def update_presets(
    index_url: str,
    *,
    preset_dir: Path | None = None,
    timeout_seconds: int = 20,
    allow_unverified: bool = False,
) -> list[PresetUpdateResult]:
    if yaml is None:
        raise PresetError(["PyYAML is required. Install with: python -m pip install PyYAML"])
    destination = preset_dir or default_user_preset_dir()
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PresetError([f"{destination} could not be created: {exc}"]) from exc

    index = _download_json(index_url, timeout_seconds)
    entries = index.get("presets")
    if not isinstance(entries, list):
        raise PresetError(["Preset index must contain a presets list."])

    results = []
    saved_index = {"source": index_url, "updated_at": _now_iso(), "presets": []}
    for raw_entry in entries:
        result = _download_preset_entry(
            raw_entry,
            destination=destination,
            timeout_seconds=timeout_seconds,
            allow_unverified=allow_unverified,
        )
        results.append(result)
        if not result.skipped and result.path is not None:
            saved_index["presets"].append(
                {
                    "name": result.name,
                    "path": result.path.name,
                    "verified": result.verified,
                }
            )

    try:
        (destination / "index.json").write_text(
            json.dumps(saved_index, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise PresetError([f"{destination / 'index.json'} could not be written: {exc}"]) from exc
    return results


def apply_preset_to_config(
    preset_name: str,
    config_path: Path,
    *,
    preset_dir: Path | None = None,
) -> tuple[Path, Path]:
    if yaml is None:
        raise PresetError(["PyYAML is required. Install with: python -m pip install PyYAML"])
    if not config_path.exists():
        raise PresetError([f"{config_path} not found. Run: labor-sieve init"])

    preset = find_preset(preset_name, preset_dir)
    config_data = read_yaml_file(config_path)
    preset_data = read_yaml_file(preset.path)
    fragment = preset_config_fragment(preset_data)
    if not fragment:
        raise PresetError([f"Preset {preset.name!r} does not contain config keys to apply."])

    merged = deep_merge(config_data, fragment)
    errors = validate_config_data(merged)
    if errors:
        raise PresetError([f"Preset {preset.name!r} would make {config_path} invalid:", *errors])

    backup_path = next_backup_path(config_path)
    try:
        shutil.copyfile(config_path, backup_path)
    except OSError as exc:
        raise PresetError([f"Backup {backup_path} could not be written: {exc}"]) from exc
    header = f"# Generated by labor-sieve use-preset {preset.name}. Previous config: {backup_path.name}\n"
    try:
        config_path.write_text(header + yaml.safe_dump(merged, sort_keys=False), encoding="utf-8")
    except OSError as exc:
        raise PresetError([f"{config_path} could not be written: {exc}"]) from exc
    return config_path, backup_path


def preset_config_fragment(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key in CONFIG_FRAGMENT_KEYS}


def deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            if key in merged:
                merged[key] = deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged
    return override


def next_backup_path(path: Path) -> Path:
    candidate = path.with_name(path.name + ".bak")
    if not candidate.exists():
        return candidate
    for index in range(1, 1000):
        candidate = path.with_name(f"{path.name}.bak.{index}")
        if not candidate.exists():
            return candidate
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return path.with_name(f"{path.name}.bak.{timestamp}")


def _download_preset_entry(
    raw_entry: Any,
    *,
    destination: Path,
    timeout_seconds: int,
    allow_unverified: bool,
) -> PresetUpdateResult:
    if not isinstance(raw_entry, dict):
        return PresetUpdateResult(
            name="<invalid>",
            path=None,
            verified=False,
            skipped=True,
            message="index entry must be an object",
        )

    name = str(raw_entry.get("name") or "").strip()
    url = str(raw_entry.get("url") or "").strip()
    expected_sha = str(raw_entry.get("sha256") or "").strip().casefold()
    if not PRESET_NAME_RE.fullmatch(name):
        return PresetUpdateResult(name or "<invalid>", None, False, True, "invalid preset name")
    if not url:
        return PresetUpdateResult(name, None, False, True, "missing preset url")
    if not expected_sha and not allow_unverified:
        return PresetUpdateResult(name, None, False, True, "missing sha256")

    try:
        content = _download_bytes(url, timeout_seconds)
    except PresetError as exc:
        return PresetUpdateResult(name, None, False, True, "; ".join(exc.errors))

    digest = hashlib.sha256(content).hexdigest()
    verified = bool(expected_sha and digest == expected_sha)
    if expected_sha and not verified:
        return PresetUpdateResult(name, None, False, True, "sha256 mismatch")

    try:
        loaded = yaml.safe_load(content.decode("utf-8"))
    except UnicodeDecodeError:
        return PresetUpdateResult(name, None, verified, True, "preset is not UTF-8")
    except yaml.YAMLError as exc:
        return PresetUpdateResult(name, None, verified, True, f"invalid YAML: {exc}")

    if not isinstance(loaded, dict):
        return PresetUpdateResult(name, None, verified, True, "preset YAML must be a mapping")
    loaded["name"] = str(loaded.get("name") or name)
    if loaded["name"] != name:
        return PresetUpdateResult(name, None, verified, True, "preset name does not match index")
    if not preset_config_fragment(loaded):
        return PresetUpdateResult(name, None, verified, True, "preset has no config keys")

    target = destination / f"{name}.yaml"
    try:
        target.write_bytes(content)
    except OSError as exc:
        return PresetUpdateResult(name, None, verified, True, f"preset could not be written: {exc}")
    return PresetUpdateResult(
        name=name,
        path=target,
        verified=verified,
        skipped=False,
        message="updated",
    )


def _download_json(url: str, timeout_seconds: int) -> dict[str, Any]:
    try:
        payload = json.loads(_download_bytes(url, timeout_seconds).decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise PresetError([f"Preset index is not valid JSON: {exc}"]) from exc
    except UnicodeDecodeError as exc:
        raise PresetError(["Preset index is not UTF-8."]) from exc
    if not isinstance(payload, dict):
        raise PresetError(["Preset index must be a JSON object."])
    return payload


def _download_bytes(url: str, timeout_seconds: int) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https", "file"}:
        raise PresetError([f"Unsupported URL scheme {parsed.scheme!r}. Use http, https, or file."])
    request = Request(url, headers={"User-Agent": "labor-sieve/0.1"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return read_response_limited(response, MAX_PRESET_BYTES, f"{url} response")
    except ResponseTooLargeError as exc:
        raise PresetError([str(exc)]) from exc
    except HTTPError as exc:
        raise PresetError([f"{url} returned HTTP {exc.code}."]) from exc
    except URLError as exc:
        raise PresetError([f"{url} could not be reached: {exc.reason}."]) from exc
    except TimeoutError as exc:
        raise PresetError([f"{url} timed out."]) from exc


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
