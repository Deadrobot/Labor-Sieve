"""Job scoring and priority bucketing."""

from __future__ import annotations

import re

from .config import Config
from .models import Job, ScoredJob
from .taxonomy import SENIORITY_LEVELS, seniority_index


def priority_bucket(score: int) -> str:
    if score >= 90:
        return "P0"
    if score >= 80:
        return "P1"
    if score >= 65:
        return "P2"
    if score >= 50:
        return "P3"
    return "rejected"


def score_jobs(jobs: list[Job], config: Config) -> list[ScoredJob]:
    scored = [score_job(job, config) for job in jobs]
    return sorted(scored, key=lambda item: (item.priority == "rejected", -item.score, item.job.company))


def score_job(job: Job, config: Config) -> ScoredJob:
    score = 20.0
    reasons: list[str] = ["base score 20"]

    role_weight = config.role_family_weights.get(
        job.role_family,
        config.role_family_weights.get("unknown", 0.0),
    )
    score += role_weight * 40
    if job.role_family in config.role_family_weights:
        reasons.append(f"role family {job.role_family} weight {role_weight:.2f}")
    else:
        reasons.append(f"role family {job.role_family} not configured; used unknown weight {role_weight:.2f}")

    score += _seniority_points(job, config, reasons)
    score += _location_points(job, config, reasons)
    score += _compensation_points(job, config, reasons)

    searchable_text = _job_text(job)
    boost_matches = _matching_keywords(searchable_text, config.keywords.boost)
    if boost_matches:
        boost_points = min(len(boost_matches) * 4, 20)
        score += boost_points
        reasons.append(f"boost keywords +{boost_points}: {', '.join(boost_matches)}")

    penalty_matches = _matching_keywords(searchable_text, config.keywords.penalize)
    if penalty_matches:
        penalty_points = len(penalty_matches) * 7
        score -= penalty_points
        reasons.append(f"penalty keywords -{penalty_points}: {', '.join(penalty_matches)}")

    if job.seniority == "principal" and not config.seniority.allow_principal:
        score = min(score, 64)
        reasons.append("principal roles are capped because allow_principal is false")
    if job.seniority == "executive" and not config.seniority.allow_executive:
        score = min(score, 49)
        reasons.append("executive roles are capped because allow_executive is false")

    final_score = max(0, min(100, round(score)))
    return ScoredJob(
        job=job,
        score=final_score,
        priority=priority_bucket(final_score),
        reasons=reasons,
    )


def _seniority_points(job: Job, config: Config, reasons: list[str]) -> float:
    if job.seniority not in SENIORITY_LEVELS:
        reasons.append(f"unknown seniority {job.seniority}; +0")
        return 0

    job_index = seniority_index(job.seniority)
    min_index = seniority_index(config.seniority.min)
    max_index = seniority_index(config.seniority.max)

    if min_index <= job_index <= max_index:
        reasons.append(f"seniority {job.seniority} within {config.seniority.min}-{config.seniority.max}; +20")
        return 20
    if job_index < min_index:
        gap = min_index - job_index
        points = max(0, 10 - (gap * 3))
        reasons.append(f"seniority {job.seniority} below target range; +{points}")
        return points

    gap = job_index - max_index
    points = max(0, 12 - (gap * 4))
    reasons.append(f"seniority {job.seniority} above target range; +{points}")
    return points


def _location_points(job: Job, config: Config, reasons: list[str]) -> float:
    if job.remote:
        if config.locations.remote:
            reasons.append("remote role accepted; +10")
            return 10
        reasons.append("remote role but remote is disabled; +0")
        return 0

    if job.hybrid:
        normalized_locations = [location.casefold() for location in config.locations.hybrid_locations]
        if any(location in job.location.casefold() for location in normalized_locations):
            reasons.append(f"hybrid location {job.location} accepted; +8")
            return 8
        reasons.append(f"hybrid location {job.location} is not configured; +2")
        return 2

    reasons.append("on-site or unspecified location; +0")
    return 0


def _compensation_points(job: Job, config: Config, reasons: list[str]) -> float:
    minimum = config.compensation.minimum_base
    if minimum is None:
        reasons.append("no compensation floor configured; +0")
        return 0
    if job.compensation_base_min is None:
        reasons.append("no base compensation listed; +3")
        return 3
    if job.compensation_base_min >= minimum:
        reasons.append(f"base compensation meets minimum ${minimum:,}; +5")
        return 5
    reasons.append(f"base compensation below minimum ${minimum:,}; -15")
    return -15


def _job_text(job: Job) -> str:
    return " ".join(
        [
            job.title,
            job.company,
            job.location,
            job.description,
            " ".join(job.tags),
        ]
    ).casefold()


def _matching_keywords(text: str, keywords: list[str]) -> list[str]:
    matches = []
    for keyword in keywords:
        normalized = keyword.casefold().strip()
        if not normalized:
            continue
        pattern = r"(?<![a-z0-9])" + re.escape(normalized) + r"(?![a-z0-9])"
        if re.search(pattern, text):
            matches.append(keyword)
    return matches
