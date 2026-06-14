"""Lightweight PyPI update notices."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO


PYPI_JSON_URL = "https://pypi.org/pypi/labor-sieve/json"
DEFAULT_TIMEOUT_SECONDS = 2.0
SKIP_ENV_VAR = "LABOR_SIEVE_SKIP_UPDATE_CHECK"


def maybe_print_update_notice(
    *,
    installed_version: str,
    enabled: bool,
    interval_days: int,
    stream: TextIO,
    state_path: Path | None = None,
    now: float | None = None,
    fetch_latest_version: Callable[[], str | None] | None = None,
) -> bool:
    """Check PyPI at most once per interval and print an upgrade notice when newer."""
    if not enabled or os.environ.get(SKIP_ENV_VAR):
        return False
    checked_at = time.time() if now is None else now
    state_file = state_path or default_update_state_path()
    state = read_update_state(state_file)
    if not update_check_due(state, now=checked_at, interval_days=interval_days):
        return False

    fetcher = fetch_latest_version or fetch_pypi_latest_version
    latest_version = None
    try:
        latest_version = fetcher()
    except Exception:
        latest_version = None

    write_update_state(
        state_file,
        {
            "checked_at": checked_at,
            "latest_version": latest_version,
        },
    )
    if latest_version and is_version_newer(latest_version, installed_version):
        print(
            f"LaborSieve {latest_version} is available. Installed version: {installed_version}.",
            file=stream,
        )
        print("Upgrade with: pipx upgrade labor-sieve", file=stream)
        return True
    return False


def fetch_pypi_latest_version(timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> str | None:
    request = urllib.request.Request(
        PYPI_JSON_URL,
        headers={"User-Agent": "labor-sieve update-check"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    version = payload.get("info", {}).get("version")
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def default_update_state_path() -> Path:
    return Path.home() / ".local" / "state" / "labor-sieve" / "update-check.json"


def read_update_state(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}


def write_update_state(path: Path, state: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        return


def update_check_due(state: dict[str, Any], *, now: float, interval_days: int) -> bool:
    last_checked = state.get("checked_at")
    if not isinstance(last_checked, int | float) or isinstance(last_checked, bool):
        return True
    if now < float(last_checked):
        return True
    interval_seconds = max(interval_days, 1) * 24 * 60 * 60
    return now - float(last_checked) >= interval_seconds


def is_version_newer(latest_version: str, installed_version: str) -> bool:
    latest = version_release_key(latest_version)
    installed = version_release_key(installed_version)
    length = max(len(latest), len(installed))
    latest += (0,) * (length - len(latest))
    installed += (0,) * (length - len(installed))
    return latest > installed


def version_release_key(version: str) -> tuple[int, ...]:
    parts = []
    for part in re.split(r"[.+!-]", version):
        match = re.match(r"^(\d+)", part)
        if match is None:
            break
        parts.append(int(match.group(1)))
    return tuple(parts) or (0,)
