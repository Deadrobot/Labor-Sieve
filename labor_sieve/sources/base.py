"""Base source adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from labor_sieve.models import Job


class SourceError(Exception):
    """Raised when a job source cannot be read."""


class JobSource(ABC):
    name: str

    @abstractmethod
    def fetch(self) -> list[Job]:
        """Return jobs from this source."""
