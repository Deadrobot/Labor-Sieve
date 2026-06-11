"""Ashby Job Posting API source."""

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


class AshbySource(JobSource):
    name = "ashby"

    def __init__(
        self,
        organizations: list[str],
        timeout_seconds: int = 20,
        base_url: str = "https://api.ashbyhq.com/posting-api/job-board",
    ) -> None:
        self.organizations = organizations
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url.rstrip("/")

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for organization in self.organizations:
            jobs.extend(self._fetch_organization(organization))
        return jobs

    def _fetch_organization(self, organization: str) -> list[Job]:
        slug = organization.strip()
        if not slug:
            return []

        errors = []
        for variant in ashby_slug_variants(slug):
            try:
                return self._fetch_slug(variant, company_default=slug)
            except SourceError as exc:
                errors.append(str(exc))
        raise SourceError("; ".join(errors[:3]))

    def _fetch_slug(self, slug: str, *, company_default: str) -> list[Job]:
        query = urlencode({"includeCompensation": "true"})
        url = f"{self.base_url}/{quote(slug, safe='')}"
        url = f"{url}?{query}"
        request = Request(url, headers={"User-Agent": "labor-sieve/0.1"})
        try:
            with open_without_redirects(request, self.timeout_seconds) as response:
                content = read_response_limited(
                    response,
                    MAX_REMOTE_RESPONSE_BYTES,
                    f"Ashby organization {slug!r} response",
                )
                payload = json.loads(content.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise SourceError(f"Ashby organization {slug!r} returned non-UTF-8 data.") from exc
        except ResponseTooLargeError as exc:
            raise SourceError(str(exc)) from exc
        except RedirectBlockedError as exc:
            detail = f" to {exc.location}" if exc.location else ""
            raise SourceError(
                f"Ashby organization {slug!r} redirected{detail}; redirects are not allowed."
            ) from exc
        except HTTPError as exc:
            raise SourceError(f"Ashby organization {slug!r} returned HTTP {exc.code}.") from exc
        except URLError as exc:
            raise SourceError(f"Ashby organization {slug!r} could not be reached: {exc.reason}.") from exc
        except TimeoutError as exc:
            raise SourceError(f"Ashby organization {slug!r} timed out.") from exc
        except json.JSONDecodeError as exc:
            raise SourceError(f"Ashby organization {slug!r} returned invalid JSON.") from exc

        records = ashby_records(payload, slug)
        if len(records) > MAX_RECORDS_PER_SOURCE:
            raise SourceError(
                f"Ashby organization {slug!r} returned more than {MAX_RECORDS_PER_SOURCE} records."
            )

        jobs = []
        for index, record in enumerate(records, start=1):
            if record.get("isListed") is False:
                continue
            normalized = normalize_ashby_record(record, organization=slug)
            jobs.append(
                normalize_job_record(
                    normalized,
                    source_name=self.name,
                    index=index,
                    company_default=company_default,
                )
            )
        return jobs


def ashby_records(payload: object, organization: str) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        raise SourceError(f"Ashby organization {organization!r} response was not an object.")

    raw_records = payload.get("jobs")
    if raw_records is None:
        raw_records = payload.get("jobPostings")
    if not isinstance(raw_records, list):
        raise SourceError(f"Ashby organization {organization!r} response did not include a jobs list.")
    return [record for record in raw_records if isinstance(record, dict)]


def normalize_ashby_record(record: dict[str, object], organization: str) -> dict[str, object]:
    description = ashby_description_text(record)
    location = ashby_location_text(record)
    url = first_text(record, "jobUrl", "job_url", "url", "applyUrl", "hostedUrl")

    return {
        "id": ashby_job_id(record),
        "title": record.get("title"),
        "company": organization,
        "location": location,
        "url": url,
        "description": clean_text(description),
        "tags": ashby_tags(record),
        "salaryRange": ashby_compensation_text(record),
    }


def ashby_slug_variants(slug: str) -> list[str]:
    lowered = slug.lower()
    variants = [
        slug,
        lowered,
        lowered[:1].upper() + lowered[1:] if lowered else "",
    ]
    return dedupe_slug_variants(variants)


def ashby_job_id(record: dict[str, object]) -> object:
    return first_value(record, "id", "jobId", "jobPostingId", "uuid")


def ashby_location_text(record: dict[str, object]) -> str:
    values = []
    if record.get("isRemote") is True:
        values.append("Remote")
    values.extend(
        [
            first_text(record, "locationName", "location", "location_name"),
            ashby_address_text(record.get("address")),
        ]
    )
    secondary = record.get("secondaryLocations")
    if isinstance(secondary, list):
        values.extend(location_text(value) for value in secondary)
    values.append(first_text(record, "workplaceType"))
    return " | ".join(dedupe_texts(values)) or "Unknown"


def ashby_address_text(value: object) -> str:
    postal = value.get("postalAddress") if isinstance(value, dict) else None
    if not isinstance(postal, dict):
        return ""
    return ", ".join(
        dedupe_texts(
            [
                text_value(postal.get("addressLocality")),
                text_value(postal.get("addressRegion")),
                text_value(postal.get("addressCountry")),
            ]
        )
    )


def ashby_description_text(record: dict[str, object]) -> str:
    values = [
        first_text(record, "descriptionPlain", "descriptionHtml", "description", "jobDescription", "summary"),
        field_label(record, "department", "Department"),
        field_label(record, "team", "Team"),
        field_label(record, "employmentType", "Employment type"),
        field_label(record, "workplaceType", "Workplace"),
    ]
    compensation = ashby_compensation_text(record)
    if compensation:
        values.append(f"Compensation: {compensation}")
    return clean_text(" ".join(value for value in values if value))


def ashby_compensation_text(record: dict[str, object]) -> str:
    compensation = first_value(record, "compensation", "salaryRange", "payRange")
    if isinstance(compensation, dict):
        for key in (
            "compensationTierSummary",
            "scrapeableCompensationSalarySummary",
            "salaryRange",
            "payRange",
            "summary",
        ):
            text = text_value(compensation.get(key))
            if text:
                return text
    return text_value(compensation)


def ashby_tags(record: dict[str, object]) -> list[str]:
    tags = []
    for key in (
        "department",
        "departmentName",
        "team",
        "teamName",
        "employmentType",
        "employmentTypeName",
        "jobType",
        "workplaceType",
        "locationName",
    ):
        value = text_value(record.get(key))
        if value:
            tags.append(value)
    return dedupe_texts(tags)


def field_label(record: dict[str, object], key: str, label: str) -> str:
    value = text_value(record.get(key))
    return f"{label}: {value}" if value else ""


def location_text(value: object) -> str:
    if isinstance(value, dict):
        return text_value(value.get("name") or value.get("location") or value.get("locationName") or value.get("label"))
    return text_value(value)


def first_value(record: dict[str, object], *keys: str) -> object:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def first_text(record: dict[str, object], *keys: str) -> str:
    value = first_value(record, *keys)
    return text_value(value)


def text_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return location_text(value)
    return str(value)


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


def dedupe_slug_variants(values: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for value in values:
        text = clean_text(value)
        if text and text not in seen:
            seen.add(text)
            deduped.append(text)
    return deduped
