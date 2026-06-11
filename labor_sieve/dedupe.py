"""Job deduplication helpers."""

from __future__ import annotations

import re
from dataclasses import replace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Job
from .sources.normalization import dedupe_preserve_order


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"gh_src", "lever-source", "source", "ref", "referrer"}


def dedupe_jobs(jobs: list[Job]) -> tuple[list[Job], int]:
    """Deduplicate jobs by URL first, then normalized company/title/location."""
    by_url: dict[str, Job] = {}
    by_fingerprint: dict[str, Job] = {}
    deduped: list[Job] = []
    duplicate_count = 0

    for job in jobs:
        current = clone_job(job)
        match = None
        url_key = normalized_url(current.url)
        if url_key:
            match = by_url.get(url_key)
        if match is None:
            fingerprint = job_fingerprint(current)
            if fingerprint:
                match = by_fingerprint.get(fingerprint)

        if match is None:
            deduped.append(current)
            index_job(current, by_url, by_fingerprint)
            continue

        duplicate_count += 1
        replacement = merge_jobs(match, current)
        if replacement is not match:
            replace_by_identity(deduped, match, replacement)
            remove_job_indexes(match, by_url, by_fingerprint)
            index_job(replacement, by_url, by_fingerprint)
        else:
            index_job(match, by_url, by_fingerprint)

    return deduped, duplicate_count


def merge_jobs(existing: Job, incoming: Job) -> Job:
    winner, other = choose_better_job(existing, incoming)
    merged = clone_job(winner)
    merged.tags = dedupe_preserve_order([*existing.tags, *incoming.tags])
    merged.merged_sources = dedupe_preserve_order(
        [
            *existing.merged_sources,
            *incoming.merged_sources,
            source_ref(existing),
            source_ref(incoming),
        ]
    )
    if not merged.url:
        merged.url = other.url
    if merged.compensation_base_min is None:
        merged.compensation_base_min = other.compensation_base_min
    if len(other.description) > len(merged.description):
        merged.description = other.description
    return merged


def choose_better_job(left: Job, right: Job) -> tuple[Job, Job]:
    if job_quality(right) > job_quality(left):
        return right, left
    return left, right


def job_quality(job: Job) -> tuple[int, int, int, int]:
    return (
        1 if job.url else 0,
        1 if job.compensation_base_min is not None else 0,
        len(job.description),
        len(job.tags),
    )


def index_job(job: Job, by_url: dict[str, Job], by_fingerprint: dict[str, Job]) -> None:
    url_key = normalized_url(job.url)
    if url_key:
        by_url[url_key] = job
    fingerprint = job_fingerprint(job)
    if fingerprint:
        by_fingerprint[fingerprint] = job


def remove_job_indexes(job: Job, by_url: dict[str, Job], by_fingerprint: dict[str, Job]) -> None:
    url_key = normalized_url(job.url)
    if url_key:
        by_url.pop(url_key, None)
    fingerprint = job_fingerprint(job)
    if fingerprint:
        by_fingerprint.pop(fingerprint, None)


def replace_by_identity(jobs: list[Job], old: Job, new: Job) -> None:
    for index, job in enumerate(jobs):
        if job is old:
            jobs[index] = new
            return
    raise ValueError("dedupe match was not found in job list")


def clone_job(job: Job) -> Job:
    return replace(job, tags=list(job.tags), merged_sources=list(job.merged_sources))


def source_ref(job: Job) -> str:
    return f"{job.source}:{job.source_id}" if job.source_id else job.source


def job_fingerprint(job: Job) -> str:
    company = normalize_text(job.company)
    title = normalize_title(job.title)
    location = normalize_location(job.location)
    if company in {"", "unknown", "unknown company"} or title in {"", "untitled job"}:
        return ""
    return "|".join(
        [
            company,
            title,
            location,
        ]
    )


def normalized_url(url: str) -> str:
    if not url:
        return ""
    split = urlsplit(url.strip())
    if not split.scheme or not split.netloc:
        return ""
    query_items = [
        (key, value)
        for key, value in parse_qsl(split.query, keep_blank_values=True)
        if not key.startswith(TRACKING_QUERY_PREFIXES) and key not in TRACKING_QUERY_KEYS
    ]
    path = split.path.rstrip("/")
    return urlunsplit(
        (
            split.scheme.lower(),
            split.netloc.lower(),
            path,
            urlencode(sorted(query_items)),
            "",
        )
    )


def normalize_title(value: str) -> str:
    normalized = normalize_text(value)
    normalized = re.sub(r"\b(sr|senior)\b", "senior", normalized)
    normalized = re.sub(r"\b(jr|junior)\b", "junior", normalized)
    return normalized


def normalize_location(value: str) -> str:
    normalized = normalize_text(value)
    normalized = normalized.replace("remote united states", "remote")
    normalized = normalized.replace("remote us", "remote")
    return normalized


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.casefold())).strip()
