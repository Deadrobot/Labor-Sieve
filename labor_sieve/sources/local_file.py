"""Local CSV/JSON/YAML job source."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from labor_sieve.config import yaml
from labor_sieve.models import Job
from labor_sieve.net import MAX_LOCAL_FILE_BYTES, MAX_RECORDS_PER_SOURCE
from labor_sieve.sources.base import JobSource, SourceError
from labor_sieve.sources.normalization import normalize_job_record


class LocalFileSource(JobSource):
    name = "local_file"

    def __init__(self, paths: list[str]) -> None:
        self.paths = [Path(path).expanduser() for path in paths]

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for path in self.paths:
            records = self._read_records(path)
            for index, record in enumerate(records, start=1):
                if not isinstance(record, dict):
                    raise SourceError(f"{path}: record {index} must be a mapping/object.")
                jobs.append(normalize_job_record(record, source_name=self.name, index=index))
        return jobs

    def _read_records(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            raise SourceError(f"{path} does not exist.")
        _check_file_size(path)
        suffix = path.suffix.casefold()
        if suffix == ".csv":
            try:
                with path.open("r", newline="", encoding="utf-8") as handle:
                    records = []
                    for index, record in enumerate(csv.DictReader(handle), start=1):
                        if index > MAX_RECORDS_PER_SOURCE:
                            raise SourceError(
                                f"{path}: contains more than {MAX_RECORDS_PER_SOURCE} records."
                            )
                        records.append(record)
                    return records
            except OSError as exc:
                raise SourceError(f"{path} could not be read: {exc}") from exc
        if suffix == ".json":
            try:
                return _limit_records(
                    _extract_jobs(json.loads(path.read_text(encoding="utf-8")), path),
                    path,
                )
            except OSError as exc:
                raise SourceError(f"{path} could not be read: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise SourceError(f"{path} is not valid JSON: {exc}") from exc
        if suffix in {".yaml", ".yml"}:
            if yaml is None:
                raise SourceError("PyYAML is required for YAML local_file sources.")
            try:
                return _limit_records(
                    _extract_jobs(yaml.safe_load(path.read_text(encoding="utf-8")), path),
                    path,
                )
            except OSError as exc:
                raise SourceError(f"{path} could not be read: {exc}") from exc
            except yaml.YAMLError as exc:
                raise SourceError(f"{path} is not valid YAML: {exc}") from exc
        raise SourceError(f"{path}: unsupported file type. Use .csv, .json, .yaml, or .yml.")


def _extract_jobs(data: Any, path: Path) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("jobs"), list):
        return data["jobs"]
    raise SourceError(f"{path}: expected a list of jobs or an object with a jobs list.")


def _check_file_size(path: Path) -> None:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise SourceError(f"{path} could not be inspected: {exc}") from exc
    if size > MAX_LOCAL_FILE_BYTES:
        raise SourceError(f"{path} is larger than the {MAX_LOCAL_FILE_BYTES} byte limit.")


def _limit_records(records: list[dict[str, Any]], path: Path) -> list[dict[str, Any]]:
    if len(records) > MAX_RECORDS_PER_SOURCE:
        raise SourceError(f"{path}: contains more than {MAX_RECORDS_PER_SOURCE} records.")
    return records
