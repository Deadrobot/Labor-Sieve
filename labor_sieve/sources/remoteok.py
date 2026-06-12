"""RemoteOK public API source."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request

from labor_sieve.net import (
    MAX_RECORDS_PER_SOURCE,
    MAX_REMOTE_RESPONSE_BYTES,
    RedirectBlockedError,
    ResponseTooLargeError,
    open_without_redirects,
    read_response_limited,
)
from labor_sieve.models import Job
from labor_sieve.sources.base import JobSource, SourceError
from labor_sieve.sources.normalization import clean_text, normalize_job_record


class RemoteOkSource(JobSource):
    name = "remoteok"

    def __init__(
        self,
        timeout_seconds: int = 20,
        max_jobs: int = 250,
        base_url: str = "https://remoteok.com/api",
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_jobs = max(1, min(max_jobs, MAX_RECORDS_PER_SOURCE))
        self.base_url = base_url

    def fetch(self) -> list[Job]:
        request = Request(
            self.base_url,
            headers={
                "User-Agent": "labor-sieve/0.1",
                "Accept": "application/json",
            },
        )
        try:
            with open_without_redirects(request, self.timeout_seconds) as response:
                content = read_response_limited(
                    response,
                    MAX_REMOTE_RESPONSE_BYTES,
                    "RemoteOK API response",
                )
                payload = json.loads(content.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise SourceError("RemoteOK returned non-UTF-8 data.") from exc
        except ResponseTooLargeError as exc:
            raise SourceError(str(exc)) from exc
        except RedirectBlockedError as exc:
            detail = f" to {exc.location}" if exc.location else ""
            raise SourceError(f"RemoteOK redirected{detail}; redirects are not allowed.") from exc
        except HTTPError as exc:
            raise SourceError(f"RemoteOK returned HTTP {exc.code}.") from exc
        except URLError as exc:
            raise SourceError(f"RemoteOK could not be reached: {exc.reason}.") from exc
        except TimeoutError as exc:
            raise SourceError("RemoteOK timed out.") from exc
        except json.JSONDecodeError as exc:
            raise SourceError("RemoteOK returned invalid JSON.") from exc

        if not isinstance(payload, list):
            raise SourceError("RemoteOK response was not a list.")
        if len(payload) > MAX_RECORDS_PER_SOURCE:
            raise SourceError(f"RemoteOK returned more than {MAX_RECORDS_PER_SOURCE} records.")

        jobs = []
        for index, record in enumerate(remoteok_records(payload)[: self.max_jobs], start=1):
            normalized = normalize_remoteok_record(record)
            jobs.append(
                normalize_job_record(
                    normalized,
                    source_name=self.name,
                    index=index,
                    company_default="RemoteOK",
                )
            )
        return jobs


def remoteok_records(payload: list[object]) -> list[dict[str, object]]:
    records = []
    for value in payload:
        if not isinstance(value, dict):
            continue
        if "legal" in value and not any(key in value for key in ("position", "title", "company")):
            continue
        title = text_value(value.get("position") or value.get("title"))
        company = text_value(value.get("company"))
        if title and company:
            records.append(value)
    return records


def normalize_remoteok_record(record: dict[str, object]) -> dict[str, object]:
    tags = record.get("tags")
    if not isinstance(tags, list):
        tags = []
    salary_min = record.get("salary_min")
    if salary_min in (None, "", 0):
        salary_min = record.get("salary")
    return {
        "id": record.get("id") or record.get("slug"),
        "title": record.get("position") or record.get("title"),
        "company": record.get("company"),
        "location": record.get("location") or "Remote",
        "remote": True,
        "url": record.get("url") or record.get("apply_url"),
        "description": clean_text(text_value(record.get("description"))),
        "tags": [text_value(tag) for tag in tags if text_value(tag)],
        "compensation_base_min": salary_min,
    }


def text_value(value: object) -> str:
    if value in (None, ""):
        return ""
    return clean_text(str(value))
