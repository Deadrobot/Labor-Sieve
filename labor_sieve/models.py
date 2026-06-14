"""Data models for jobs and scored jobs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Job:
    id: str
    title: str
    company: str
    location: str
    remote: bool
    hybrid: bool
    seniority: str
    role_family: str
    compensation_base_min: int | None
    url: str
    description: str
    tags: list[str] = field(default_factory=list)
    source: str = "unknown"
    source_id: str = ""
    merged_sources: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ScoredJob:
    job: Job
    score: int
    priority: str
    reasons: list[str] = field(default_factory=list)
    history_status: str = ""
    previous_score: int | None = None
    score_delta: int | None = None
