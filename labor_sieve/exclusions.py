"""Configured job exclusion helpers."""

from __future__ import annotations

import re

from .config import Config
from .dedupe import normalized_url
from .models import Job


def apply_exclusions(jobs: list[Job], config: Config) -> tuple[list[Job], int]:
    kept = []
    excluded_count = 0
    for job in jobs:
        if job_is_excluded(job, config):
            excluded_count += 1
        else:
            kept.append(job)
    return kept, excluded_count


def job_is_excluded(job: Job, config: Config) -> bool:
    return (
        company_is_excluded(job.company, config.exclusions.companies)
        or url_is_excluded(job.url, config.exclusions.urls)
        or source_id_is_excluded(job, config.exclusions.source_ids)
    )


def company_is_excluded(company: str, excluded_companies: list[str]) -> bool:
    normalized_company = normalize_text(company)
    return any(phrase_matches(normalized_company, normalize_text(value)) for value in excluded_companies)


def url_is_excluded(url: str, excluded_urls: list[str]) -> bool:
    if not url:
        return False
    normalized = normalized_url(url) or url.strip().casefold()
    excluded = {normalized_url(value) or value.strip().casefold() for value in excluded_urls if value.strip()}
    return normalized in excluded


def source_id_is_excluded(job: Job, excluded_source_ids: list[str]) -> bool:
    excluded = {value.strip().casefold() for value in excluded_source_ids if value.strip()}
    if not excluded:
        return False
    candidates = {
        job.id,
        job.source_id,
        f"{job.source}:{job.id}",
        f"{job.source}:{job.source_id}",
    }
    return any(candidate.strip().casefold() in excluded for candidate in candidates if candidate)


def phrase_matches(normalized_text: str, normalized_phrase: str) -> bool:
    if not normalized_text or not normalized_phrase:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(normalized_phrase) + r"(?![a-z0-9])"
    return re.search(pattern, normalized_text) is not None


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.casefold())).strip()
