"""Run history state and annotations."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ScoredJob
from .reports import report_job_key


SKIP_HISTORY_ENV_VAR = "LABOR_SIEVE_SKIP_RUN_HISTORY"
HISTORY_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class HistoryRecord:
    key: str
    title: str
    company: str
    url: str
    source: str
    source_id: str
    score: int
    priority: str
    seen_at: str


@dataclass(slots=True)
class RunHistory:
    previous_count: int = 0
    new_count: int = 0
    seen_count: int = 0
    disappeared: list[HistoryRecord] | None = None

    def disappeared_count(self) -> int:
        return len(self.disappeared or [])


def default_history_path() -> Path:
    return Path.home() / ".local" / "state" / "labor-sieve" / "run-history.json"


def load_history(path: Path | None = None) -> dict[str, HistoryRecord]:
    state_path = path or default_history_path()
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    jobs = payload.get("jobs")
    if not isinstance(jobs, dict):
        return {}
    records: dict[str, HistoryRecord] = {}
    for key, raw_record in jobs.items():
        if isinstance(key, str) and isinstance(raw_record, dict):
            record = history_record_from_data(key, raw_record)
            if record is not None:
                records[key] = record
    return records


def annotate_run_history(scored_jobs: list[ScoredJob], previous: dict[str, HistoryRecord]) -> RunHistory:
    current_keys = set()
    new_count = 0
    seen_count = 0
    for item in scored_jobs:
        key = report_job_key(item)
        current_keys.add(key)
        old = previous.get(key)
        if old is None:
            item.history_status = "new"
            new_count += 1
            continue
        item.history_status = "seen"
        item.previous_score = old.score
        item.score_delta = item.score - old.score
        seen_count += 1

    disappeared = [
        record
        for key, record in sorted(previous.items(), key=lambda pair: (pair[1].company.casefold(), pair[1].title.casefold()))
        if key not in current_keys
    ]
    return RunHistory(
        previous_count=len(previous),
        new_count=new_count,
        seen_count=seen_count,
        disappeared=disappeared,
    )


def save_history(scored_jobs: list[ScoredJob], path: Path | None = None) -> None:
    if os.environ.get(SKIP_HISTORY_ENV_VAR):
        return
    state_path = path or default_history_path()
    checked_at = datetime.now(timezone.utc).isoformat()
    jobs = {
        report_job_key(item): scored_job_history_record(item, checked_at)
        for item in scored_jobs
    }
    payload = {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "updated_at": checked_at,
        "jobs": jobs,
    }
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        return


def history_enabled() -> bool:
    return not bool(os.environ.get(SKIP_HISTORY_ENV_VAR))


def history_record_from_data(key: str, data: dict[str, Any]) -> HistoryRecord | None:
    try:
        return HistoryRecord(
            key=key,
            title=str(data.get("title") or ""),
            company=str(data.get("company") or ""),
            url=str(data.get("url") or ""),
            source=str(data.get("source") or ""),
            source_id=str(data.get("source_id") or ""),
            score=int(data.get("score") or 0),
            priority=str(data.get("priority") or ""),
            seen_at=str(data.get("seen_at") or data.get("updated_at") or ""),
        )
    except (TypeError, ValueError):
        return None


def scored_job_history_record(item: ScoredJob, seen_at: str) -> dict[str, object]:
    job = item.job
    return {
        "title": job.title,
        "company": job.company,
        "url": job.url,
        "source": job.source,
        "source_id": job.source_id,
        "score": item.score,
        "priority": item.priority,
        "seen_at": seen_at,
    }
