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
    score = 10.0
    score_cap = 100.0
    reasons: list[str] = ["base score 10"]

    role_weight = config.role_family_weights.get(
        job.role_family,
        config.role_family_weights.get("unknown", 0.0),
    )
    score += role_weight * 35
    if job.role_family in config.role_family_weights:
        reasons.append(f"role family {job.role_family} weight {role_weight:.2f}")
    else:
        reasons.append(f"role family {job.role_family} not configured; used unknown weight {role_weight:.2f}")

    score += _seniority_points(job, config, reasons)
    location_points, location_cap = _location_points_and_cap(job, config, reasons)
    score += location_points
    score_cap = min(score_cap, location_cap)
    score += _compensation_points(job, config, reasons)

    searchable_text = _job_text(job)
    boost_matches = _matching_keywords(searchable_text, config.keywords.boost)
    if boost_matches:
        boost_points = min(len(boost_matches) * 3, 15)
        score += boost_points
        reasons.append(f"boost keywords +{boost_points}: {', '.join(boost_matches)}")

    score += _title_focus_points(job, reasons)

    penalty_matches = _matching_keywords(searchable_text, config.keywords.penalize)
    if penalty_matches:
        penalty_points = len(penalty_matches) * 10
        score -= penalty_points
        reasons.append(f"penalty keywords -{penalty_points}: {', '.join(penalty_matches)}")

    title_cap = _title_scope_cap(job, role_weight, reasons)
    score_cap = min(score_cap, title_cap)
    if job.seniority == "principal" and not config.seniority.allow_principal:
        score_cap = min(score_cap, 64)
        reasons.append("principal roles are capped because allow_principal is false")
    if job.seniority == "executive" and not config.seniority.allow_executive:
        score_cap = min(score_cap, 49)
        reasons.append("executive roles are capped because allow_executive is false")

    if score > score_cap:
        reasons.append(f"score capped at {round(score_cap)} by scope limits")

    final_score = max(0, min(100, round(min(score, score_cap))))
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
        reasons.append(f"seniority {job.seniority} within {config.seniority.min}-{config.seniority.max}; +15")
        return 15
    if job_index < min_index:
        gap = min_index - job_index
        points = max(0, 8 - (gap * 3))
        reasons.append(f"seniority {job.seniority} below target range; +{points}")
        return points

    gap = job_index - max_index
    points = max(0, 8 - (gap * 4))
    reasons.append(f"seniority {job.seniority} above target range; +{points}")
    return points


def _title_focus_points(job: Job, reasons: list[str]) -> float:
    title = job.title.casefold()
    if re.search(r"\boperations engineer\b", title) and re.search(r"\bfleet reliability\b|\breliability\b", title):
        reasons.append("fleet operations title focus +8")
        return 8
    if re.search(r"\boperations reliability engineer\b|\bfleet reliability\b", title):
        reasons.append("fleet reliability title focus +8")
        return 8
    return 0


def _location_points_and_cap(job: Job, config: Config, reasons: list[str]) -> tuple[float, float]:
    local_region = (
        f"{config.locations.local_region.center} "
        f"within {config.locations.local_region.radius_miles} miles"
    )
    if job.hybrid:
        if _location_matches(job.location, config.locations.accepted_locations):
            reasons.append(f"hybrid location {job.location} accepted for {local_region}; +8")
            return 8, 100
        reasons.append(f"hybrid location {job.location} is not in accepted_locations; capped below P1")
        return 0, 64

    if job.remote:
        if config.locations.remote:
            if _remote_location_allowed(job.location, config):
                reasons.append(f"remote location {job.location} accepted; +10")
                return 10, 100
            reasons.append(
                f"remote location {job.location} does not match accepted_remote_locations; capped below P1"
            )
            return 0, 64
        reasons.append("remote role but remote is disabled; capped below P1")
        return 0, 64

    if _location_matches(job.location, config.locations.accepted_locations):
        reasons.append(f"local on-site location {job.location} accepted for {local_region}; +6")
        return 6, 100

    reasons.append("on-site or unspecified location outside accepted_locations; capped below P1")
    return 0, 64


def _location_matches(job_location: str, accepted_locations: list[str]) -> bool:
    normalized_job_location = _normalized_location_text(job_location)
    return any(
        _location_contains(normalized_job_location, _normalized_location_text(location))
        for location in accepted_locations
    )


def _remote_location_allowed(job_location: str, config: Config) -> bool:
    if _is_generic_remote_location(job_location):
        return True
    return _location_matches(
        job_location,
        [*config.locations.accepted_remote_locations, *config.locations.accepted_locations],
    )


def _is_generic_remote_location(job_location: str) -> bool:
    normalized = _normalized_location_text(job_location)
    return normalized in {"remote", "remote only", "fully remote", "virtual"}


def _location_contains(normalized_haystack: str, normalized_needle: str) -> bool:
    if not normalized_needle:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(normalized_needle) + r"(?![a-z0-9])"
    return re.search(pattern, normalized_haystack) is not None


def _normalized_location_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.casefold())).strip()


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


def _title_scope_cap(job: Job, role_weight: float, reasons: list[str]) -> float:
    title = job.title.casefold()
    cap = 100.0
    if job.role_family == "management" and role_weight <= 0.25:
        cap = min(cap, 49)
        reasons.append("management role family is low-weighted; capped below P3")
    if job.role_family == "software_engineering" and role_weight <= 0.25:
        cap = min(cap, 64)
        reasons.append("software engineering role family is low-weighted; capped below P1")
    if job.role_family == "networking" and role_weight <= 0.35:
        cap = min(cap, 64)
        reasons.append("networking role family is low-weighted; capped below P1")
    if re.search(r"\b(master electrician|electrician|superintendent|field services)\b", title):
        cap = min(cap, 64)
        reasons.append("trade or field-services title matched; capped below P1")
    if re.search(r"\b(physical security|security engineer|detection and response|security regional lead)\b", title):
        cap = min(cap, 64)
        reasons.append("security title matched; capped below P1")
    if re.search(r"\b(service desk|help desk|desktop support)\b", title):
        cap = min(cap, 64)
        reasons.append("service desk title matched; capped below P1")
    if re.search(r"\b(manager|director|vp|vice president|head of|chief)\b", title):
        cap = min(cap, 49)
        reasons.append("management title term matched; capped below P3")
    if re.search(r"\bsales engineer\b", title):
        cap = min(cap, 64)
        reasons.append("sales engineer title matched; capped below P1")
    if re.search(
        r"\b(applied scientist|data scientist|research scientist|machine learning scientist|ml scientist)\b",
        title,
    ):
        cap = min(cap, 64)
        reasons.append("scientist title matched; capped below P1")
    if re.search(r"\b(frontend|front-end|full[- ]stack|mobile|ios|android)\b", title):
        cap = min(cap, 64)
        reasons.append("product software title term matched; capped below P1")
    if re.search(r"\bsoftware engineer\b", title) and not re.search(
        r"\b(site reliability|sre)\b",
        title,
    ):
        cap = min(cap, 64)
        reasons.append("software engineer title matched; capped below P1")
    return cap


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
