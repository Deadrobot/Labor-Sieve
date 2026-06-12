"""Arbeitnow public job board API source."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
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


class ArbeitnowSource(JobSource):
    name = "arbeitnow"

    def __init__(
        self,
        timeout_seconds: int = 20,
        max_pages: int = 1,
        max_jobs: int = 100,
        base_url: str = "https://www.arbeitnow.com/api/job-board-api",
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_pages = max(1, min(max_pages, 20))
        self.max_jobs = max(1, min(max_jobs, MAX_RECORDS_PER_SOURCE))
        self.base_url = base_url

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for page in range(1, self.max_pages + 1):
            records = self._fetch_page(page)
            if not records:
                break
            remaining = self.max_jobs - len(jobs)
            for index, record in enumerate(records[:remaining], start=len(jobs) + 1):
                normalized = normalize_arbeitnow_record(record)
                jobs.append(
                    normalize_job_record(
                        normalized,
                        source_name=self.name,
                        index=index,
                        company_default="Arbeitnow",
                    )
                )
            if len(jobs) >= self.max_jobs:
                break
        return jobs

    def _fetch_page(self, page: int) -> list[dict[str, object]]:
        query = urlencode({"page": page})
        url = f"{self.base_url}?{query}"
        request = Request(url, headers={"User-Agent": "labor-sieve/0.1"})
        try:
            with open_without_redirects(request, self.timeout_seconds) as response:
                content = read_response_limited(
                    response,
                    MAX_REMOTE_RESPONSE_BYTES,
                    f"Arbeitnow page {page} response",
                )
                payload = json.loads(content.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise SourceError(f"Arbeitnow page {page} returned non-UTF-8 data.") from exc
        except ResponseTooLargeError as exc:
            raise SourceError(str(exc)) from exc
        except RedirectBlockedError as exc:
            detail = f" to {exc.location}" if exc.location else ""
            raise SourceError(f"Arbeitnow page {page} redirected{detail}; redirects are not allowed.") from exc
        except HTTPError as exc:
            raise SourceError(f"Arbeitnow page {page} returned HTTP {exc.code}.") from exc
        except URLError as exc:
            raise SourceError(f"Arbeitnow page {page} could not be reached: {exc.reason}.") from exc
        except TimeoutError as exc:
            raise SourceError(f"Arbeitnow page {page} timed out.") from exc
        except json.JSONDecodeError as exc:
            raise SourceError(f"Arbeitnow page {page} returned invalid JSON.") from exc

        records = arbeitnow_records(payload, page)
        if len(records) > MAX_RECORDS_PER_SOURCE:
            raise SourceError(f"Arbeitnow page {page} returned more than {MAX_RECORDS_PER_SOURCE} records.")
        return records


def arbeitnow_records(payload: object, page: int) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        raise SourceError(f"Arbeitnow page {page} response was not an object.")
    raw_records = payload.get("data")
    if not isinstance(raw_records, list):
        raise SourceError(f"Arbeitnow page {page} response did not include a data list.")
    return [record for record in raw_records if isinstance(record, dict)]


def normalize_arbeitnow_record(record: dict[str, object]) -> dict[str, object]:
    tags = record.get("tags")
    if not isinstance(tags, list):
        tags = []
    job_types = record.get("job_types")
    if not isinstance(job_types, list):
        job_types = []
    return {
        "id": record.get("slug"),
        "title": record.get("title"),
        "company": record.get("company_name"),
        "location": record.get("location") or ("Remote" if record.get("remote") is True else "Unknown"),
        "remote": record.get("remote"),
        "url": record.get("url"),
        "description": clean_text(text_value(record.get("description"))),
        "tags": [text_value(tag) for tag in [*tags, *job_types] if text_value(tag)],
    }


def text_value(value: object) -> str:
    if value in (None, ""):
        return ""
    return clean_text(str(value))
