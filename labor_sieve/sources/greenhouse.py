"""Greenhouse Job Board API source."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from labor_sieve.models import Job
from labor_sieve.sources.base import JobSource, SourceError
from labor_sieve.sources.normalization import normalize_job_record


class GreenhouseSource(JobSource):
    name = "greenhouse"

    def __init__(self, board_tokens: list[str], timeout_seconds: int = 20) -> None:
        self.board_tokens = board_tokens
        self.timeout_seconds = timeout_seconds

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for board_token in self.board_tokens:
            jobs.extend(self._fetch_board(board_token))
        return jobs

    def _fetch_board(self, board_token: str) -> list[Job]:
        token = board_token.strip()
        if not token:
            return []

        query = urlencode({"content": "true"})
        url = f"https://boards-api.greenhouse.io/v1/boards/{quote(token, safe='')}/jobs?{query}"
        request = Request(url, headers={"User-Agent": "labor-sieve/0.1"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise SourceError(f"Greenhouse board {token!r} returned non-UTF-8 data.") from exc
        except HTTPError as exc:
            raise SourceError(f"Greenhouse board {token!r} returned HTTP {exc.code}.") from exc
        except URLError as exc:
            raise SourceError(f"Greenhouse board {token!r} could not be reached: {exc.reason}.") from exc
        except TimeoutError as exc:
            raise SourceError(f"Greenhouse board {token!r} timed out.") from exc
        except json.JSONDecodeError as exc:
            raise SourceError(f"Greenhouse board {token!r} returned invalid JSON.") from exc

        records = payload.get("jobs")
        if not isinstance(records, list):
            raise SourceError(f"Greenhouse board {token!r} response did not include a jobs list.")

        return [
            normalize_job_record(
                record,
                source_name=f"greenhouse-{token}",
                index=index,
                company_default=token,
            )
            for index, record in enumerate(records, start=1)
            if isinstance(record, dict)
        ]
