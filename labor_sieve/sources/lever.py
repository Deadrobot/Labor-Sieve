"""Lever Postings API source."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
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


class LeverSource(JobSource):
    name = "lever"

    def __init__(
        self,
        companies: list[str],
        timeout_seconds: int = 20,
        base_url: str = "https://api.lever.co/v0/postings",
    ) -> None:
        self.companies = companies
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url.rstrip("/")

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for company in self.companies:
            jobs.extend(self._fetch_company(company))
        return jobs

    def _fetch_company(self, company: str) -> list[Job]:
        slug = company.strip()
        if not slug:
            return []

        query = urlencode({"mode": "json"})
        url = f"{self.base_url}/{quote(slug, safe='')}?{query}"
        request = Request(url, headers={"User-Agent": "labor-sieve/0.1"})
        try:
            with open_without_redirects(request, self.timeout_seconds) as response:
                content = read_response_limited(
                    response,
                    MAX_REMOTE_RESPONSE_BYTES,
                    f"Lever company {slug!r} response",
                )
                payload = json.loads(content.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise SourceError(f"Lever company {slug!r} returned non-UTF-8 data.") from exc
        except ResponseTooLargeError as exc:
            raise SourceError(str(exc)) from exc
        except RedirectBlockedError as exc:
            detail = f" to {exc.location}" if exc.location else ""
            raise SourceError(
                f"Lever company {slug!r} redirected{detail}; redirects are not allowed."
            ) from exc
        except HTTPError as exc:
            raise SourceError(f"Lever company {slug!r} returned HTTP {exc.code}.") from exc
        except URLError as exc:
            raise SourceError(f"Lever company {slug!r} could not be reached: {exc.reason}.") from exc
        except TimeoutError as exc:
            raise SourceError(f"Lever company {slug!r} timed out.") from exc
        except json.JSONDecodeError as exc:
            raise SourceError(f"Lever company {slug!r} returned invalid JSON.") from exc

        if not isinstance(payload, list):
            raise SourceError(f"Lever company {slug!r} response was not a postings list.")
        if len(payload) > MAX_RECORDS_PER_SOURCE:
            raise SourceError(
                f"Lever company {slug!r} returned more than {MAX_RECORDS_PER_SOURCE} records."
            )

        jobs = []
        for index, record in enumerate(payload, start=1):
            if not isinstance(record, dict):
                continue
            normalized = normalize_lever_record(record, company=slug)
            jobs.append(
                normalize_job_record(
                    normalized,
                    source_name=self.name,
                    index=index,
                    company_default=slug,
                )
            )
        return jobs


def normalize_lever_record(record: dict[str, object], company: str) -> dict[str, object]:
    categories = record.get("categories") if isinstance(record.get("categories"), dict) else {}
    description = first_text(
        record,
        "descriptionPlain",
        "description",
        "additionalPlain",
        "additional",
    )
    lists = record.get("lists")
    if isinstance(lists, list):
        list_text = []
        for item in lists:
            if isinstance(item, dict):
                list_text.extend(str(value) for value in item.values() if value not in (None, ""))
        if list_text:
            description = " ".join([description, *list_text]).strip()

    return {
        "id": record.get("id"),
        "title": record.get("text"),
        "company": company,
        "location": categories.get("location") if isinstance(categories, dict) else None,
        "level": categories.get("level") if isinstance(categories, dict) else None,
        "url": record.get("hostedUrl") or record.get("applyUrl"),
        "description": clean_text(description),
        "tags": lever_tags(record),
        "salaryRange": record.get("salaryRange"),
    }


def lever_tags(record: dict[str, object]) -> list[str]:
    tags = []
    categories = record.get("categories")
    if isinstance(categories, dict):
        for key in ("team", "department", "location", "commitment", "level"):
            value = categories.get(key)
            if value not in (None, ""):
                tags.append(str(value))
    for key in ("workplaceType", "workplace_type"):
        value = record.get(key)
        if value not in (None, ""):
            tags.append(str(value))
    return tags


def first_text(record: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return ""
