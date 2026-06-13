"""Workday public candidate experience source."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request

from labor_sieve.net import (
    MAX_REMOTE_RESPONSE_BYTES,
    RedirectBlockedError,
    ResponseTooLargeError,
    open_without_redirects,
    read_response_limited,
)
from labor_sieve.models import Job
from labor_sieve.sources.base import JobSource, SourceError
from labor_sieve.sources.normalization import clean_text, normalize_job_record


@dataclass(frozen=True, slots=True)
class WorkdaySite:
    company: str
    url: str


@dataclass(frozen=True, slots=True)
class ParsedWorkdaySite:
    company: str
    origin: str
    base_url: str
    cxs_base: str


class WorkdaySource(JobSource):
    name = "workday"

    def __init__(
        self,
        sites: list[WorkdaySite],
        timeout_seconds: int = 20,
        page_size: int = 20,
        max_jobs_per_site: int = 200,
    ) -> None:
        self.sites = sites
        self.timeout_seconds = timeout_seconds
        self.page_size = max(1, min(page_size, 100))
        self.max_jobs_per_site = max(1, min(max_jobs_per_site, 5000))

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for site in self.sites:
            jobs.extend(self._fetch_site(site))
        return jobs

    def _fetch_site(self, site: WorkdaySite) -> list[Job]:
        parsed = parse_workday_site(site)
        jobs: list[Job] = []
        offset = 0

        while len(jobs) < self.max_jobs_per_site:
            limit = min(self.page_size, self.max_jobs_per_site - len(jobs))
            payload = {
                "appliedFacets": {},
                "limit": limit,
                "offset": offset,
                "searchText": "",
            }
            data = self._request_json(
                f"{parsed.cxs_base}/jobs",
                method="POST",
                payload=payload,
                label=f"Workday site {parsed.company!r} jobs page",
            )
            if not isinstance(data, dict):
                raise SourceError(f"Workday site {parsed.company!r} response was not an object.")
            postings = data.get("jobPostings")
            if not isinstance(postings, list):
                raise SourceError(
                    f"Workday site {parsed.company!r} response did not include a jobPostings list."
                )
            if not postings:
                break

            remaining = self.max_jobs_per_site - len(jobs)
            for index, record in enumerate(postings[:remaining], start=offset + 1):
                if not isinstance(record, dict):
                    continue
                detail = self._fetch_detail(parsed, record)
                normalized = normalize_workday_record(record, detail, parsed)
                jobs.append(
                    normalize_job_record(
                        normalized,
                        source_name=self.name,
                        index=index,
                        company_default=parsed.company,
                    )
                )

            offset += len(postings)
            total = parse_int(data.get("total"))
            if (total > 0 and offset >= total) or len(postings) < limit:
                break

        return jobs

    def _fetch_detail(self, site: ParsedWorkdaySite, record: dict[str, object]) -> dict[str, object]:
        detail_url = workday_detail_url(site, record)
        if not detail_url:
            return {}
        try:
            data = self._request_json(
                detail_url,
                method="GET",
                payload=None,
                label=f"Workday site {site.company!r} job detail",
            )
        except SourceError:
            return {}
        return data if isinstance(data, dict) else {}

    def _request_json(
        self,
        url: str,
        *,
        method: str,
        payload: dict[str, object] | None,
        label: str,
    ) -> object:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"User-Agent": "labor-sieve/0.1"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with open_without_redirects(request, self.timeout_seconds) as response:
                content = read_response_limited(response, MAX_REMOTE_RESPONSE_BYTES, label)
                return json.loads(content.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise SourceError(f"{label} returned non-UTF-8 data.") from exc
        except ResponseTooLargeError as exc:
            raise SourceError(str(exc)) from exc
        except RedirectBlockedError as exc:
            detail = f" to {exc.location}" if exc.location else ""
            raise SourceError(f"{label} redirected{detail}; redirects are not allowed.") from exc
        except HTTPError as exc:
            raise SourceError(f"{label} returned HTTP {exc.code}.") from exc
        except URLError as exc:
            raise SourceError(f"{label} could not be reached: {exc.reason}.") from exc
        except TimeoutError as exc:
            raise SourceError(f"{label} timed out.") from exc
        except json.JSONDecodeError as exc:
            raise SourceError(f"{label} returned invalid JSON.") from exc


def parse_workday_site(site: WorkdaySite) -> ParsedWorkdaySite:
    company = clean_text(site.company)
    raw_url = clean_text(site.url)
    if not company or not raw_url:
        raise SourceError("Workday sites require company and url values.")

    parsed = urlsplit(raw_url)
    host = parsed.hostname.casefold() if parsed.hostname else ""
    try:
        port = parsed.port
    except ValueError as exc:
        raise SourceError(f"Unsupported Workday URL: {raw_url}") from exc
    if parsed.username or parsed.password or port is not None:
        raise SourceError(f"Unsupported Workday URL: {raw_url}")
    if parsed.scheme != "https" or not host.endswith(".myworkdayjobs.com"):
        raise SourceError(f"Unsupported Workday URL: {raw_url}")

    host_parts = host.split(".")
    tenant = host_parts[0]
    path_parts = [part for part in parsed.path.split("/") if part]
    if not tenant or not path_parts:
        raise SourceError(f"Workday URL is missing a career site path: {raw_url}")

    site_path = path_parts[-1]
    origin = f"{parsed.scheme}://{host}"
    base_url = f"{origin}/{site_path}"
    cxs_base = f"{origin}/wday/cxs/{tenant}/{site_path}"
    return ParsedWorkdaySite(company=company, origin=origin, base_url=base_url, cxs_base=cxs_base)


def normalize_workday_record(
    record: dict[str, object],
    detail: dict[str, object],
    site: ParsedWorkdaySite,
) -> dict[str, object]:
    info = workday_posting_info(detail)
    external_path = first_text(record, "externalPath")
    description = workday_description_text(record, info)

    return {
        "id": workday_job_id(record, info, external_path),
        "title": first_value(record, "title") or first_value(info, "title"),
        "company": site.company,
        "location": workday_location_text(record, info),
        "url": workday_public_url(site, external_path),
        "description": description,
        "tags": workday_tags(record, info),
        "salaryRange": workday_compensation_text(record, info),
    }


def workday_posting_info(detail: dict[str, object]) -> dict[str, object]:
    info = detail.get("jobPostingInfo")
    return info if isinstance(info, dict) else {}


def workday_job_id(
    record: dict[str, object],
    info: dict[str, object],
    external_path: str,
) -> object:
    return (
        first_value(info, "jobReqId", "jobRequisitionId", "id")
        or first_value(record, "jobReqId", "jobRequisitionId", "id")
        or external_path
    )


def workday_public_url(site: ParsedWorkdaySite, external_path: str) -> str:
    if is_safe_workday_path(external_path):
        return site.origin + external_path
    return site.base_url


def workday_detail_url(site: ParsedWorkdaySite, record: dict[str, object]) -> str:
    external_path = first_text(record, "externalPath")
    if not is_safe_workday_path(external_path):
        return ""
    return site.cxs_base + external_path


def is_safe_workday_path(value: str) -> bool:
    return value.startswith("/") and not value.startswith("//")


def workday_location_text(record: dict[str, object], info: dict[str, object]) -> str:
    values = [
        first_text(record, "locationsText", "location"),
        first_text(info, "locationsText", "location", "primaryLocation"),
    ]
    additional = first_value(info, "additionalLocations", "locations")
    if isinstance(additional, list):
        values.extend(text_value(value) for value in additional)
    return " | ".join(dedupe_texts(values)) or "Unknown"


def workday_description_text(record: dict[str, object], info: dict[str, object]) -> str:
    values = [
        first_text(info, "jobDescription", "description"),
        first_text(record, "description"),
    ]
    bullet_fields = record.get("bulletFields")
    if isinstance(bullet_fields, list):
        values.extend(text_value(value) for value in bullet_fields)
    for key in ("timeType", "jobType", "workerSubType", "scheduledWeeklyHours"):
        label = key.replace("Type", " type").replace("scheduled", "scheduled ")
        value = text_value(info.get(key) or record.get(key))
        if value:
            values.append(f"{label}: {value}")
    return clean_text(" ".join(value for value in values if value))


def workday_compensation_text(record: dict[str, object], info: dict[str, object]) -> str:
    for mapping in (info, record):
        value = first_value(
            mapping,
            "compensation",
            "salaryRange",
            "payRange",
            "payTransparency",
            "jobPostingCompensation",
        )
        text = text_value(value)
        if text:
            return text
    return ""


def workday_tags(record: dict[str, object], info: dict[str, object]) -> list[str]:
    tags = []
    bullet_fields = record.get("bulletFields")
    if isinstance(bullet_fields, list):
        tags.extend(text_value(value) for value in bullet_fields)
    for mapping in (record, info):
        for key in (
            "locationsText",
            "timeType",
            "jobType",
            "workerSubType",
            "jobFamily",
            "businessUnit",
        ):
            tags.append(text_value(mapping.get(key)))
    return dedupe_texts(tags)


def first_value(record: dict[str, object], *keys: str) -> object:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def parse_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def first_text(record: dict[str, object], *keys: str) -> str:
    return text_value(first_value(record, *keys))


def text_value(value: object) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, dict):
        name = value.get("descriptor") or value.get("name") or value.get("title") or value.get("value")
        if name not in (None, ""):
            return clean_text(str(name))
        return clean_text(" ".join(text_value(item) for item in value.values()))
    if isinstance(value, list):
        return " | ".join(dedupe_texts([text_value(item) for item in value]))
    return clean_text(str(value))


def dedupe_texts(values: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for value in values:
        text = clean_text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            deduped.append(text)
    return deduped
