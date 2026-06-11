import csv
import json
from pathlib import Path

import pytest

from labor_sieve.sources.base import SourceError
from labor_sieve.sources.lever import LeverSource, normalize_lever_record
from labor_sieve.sources.local_file import LocalFileSource
from labor_sieve.sources.normalization import infer_role_family, normalize_job_record, parse_money


def test_local_file_source_reads_csv_records(tmp_path):
    path = tmp_path / "jobs.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "title",
                "company",
                "location",
                "remote",
                "seniority",
                "role_family",
                "compensation_base_min",
                "url",
                "description",
                "tags",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "title": "Linux Operations Engineer",
                "company": "Example Co",
                "location": "Remote - United States",
                "remote": "true",
                "seniority": "senior",
                "role_family": "sre_infra_ops",
                "compensation_base_min": "$150k",
                "url": "https://example.invalid/job",
                "description": "Linux incident response and automation.",
                "tags": "linux; incident response",
            }
        )

    jobs = LocalFileSource([str(path)]).fetch()

    assert len(jobs) == 1
    assert jobs[0].title == "Linux Operations Engineer"
    assert jobs[0].remote is True
    assert jobs[0].compensation_base_min == 150000
    assert jobs[0].tags == ["linux", "incident response"]


def test_local_file_source_reads_json_jobs_object(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "title": "Implementation Specialist",
                        "company": "Example Co",
                        "location": "Hybrid - Austin",
                        "description": "Customer support implementation work.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    jobs = LocalFileSource([str(path)]).fetch()

    assert len(jobs) == 1
    assert jobs[0].role_family == "implementation_support"
    assert jobs[0].hybrid is True


def test_local_file_source_reports_invalid_json(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(SourceError, match="not valid JSON"):
        LocalFileSource([str(path)]).fetch()


def test_normalization_handles_greenhouse_style_record():
    job = normalize_job_record(
        {
            "id": 123,
            "title": "Senior Data Center Operations Engineer",
            "location": {"name": "Seattle"},
            "absolute_url": "https://example.invalid/gh/123",
            "content": "<p>Hardware diagnostics and data center reliability.</p>",
            "departments": [{"name": "Infrastructure"}],
        },
        source_name="greenhouse-example",
        index=1,
        company_default="example",
    )

    assert job.id == "123"
    assert job.company == "example"
    assert job.location == "Seattle"
    assert job.seniority == "senior"
    assert job.role_family == "data_center_ops"
    assert "Infrastructure" in job.tags


def test_normalization_handles_lever_style_record():
    normalized = normalize_lever_record(
        {
            "id": "abc",
            "text": "Senior Linux SRE",
            "hostedUrl": "https://jobs.lever.co/example/abc",
            "descriptionPlain": "Linux incident response and automation.",
            "categories": {
                "team": "Infrastructure",
                "location": "Remote - United States",
                "level": "Senior",
            },
        },
        company="example",
    )
    job = normalize_job_record(normalized, source_name="lever", index=1, company_default="example")

    assert job.id == "abc"
    assert job.title == "Senior Linux SRE"
    assert job.company == "example"
    assert job.location == "Remote - United States"
    assert job.role_family == "sre_infra_ops"
    assert "Infrastructure" in job.tags


def test_lever_source_fetches_postings(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                [
                    {
                        "id": "abc",
                        "text": "Senior Linux SRE",
                        "hostedUrl": "https://jobs.lever.co/example/abc",
                        "descriptionPlain": "Linux incident response.",
                        "categories": {"location": "Remote"},
                    }
                ]
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        assert "https://api.lever.co/v0/postings/example?mode=json" == request.full_url
        assert timeout == 7
        return FakeResponse()

    monkeypatch.setattr("labor_sieve.sources.lever.urlopen", fake_urlopen)

    jobs = LeverSource(["example"], timeout_seconds=7).fetch()

    assert len(jobs) == 1
    assert jobs[0].source == "lever"
    assert jobs[0].source_id == "abc"


def test_parse_money_handles_salary_range_mapping():
    assert parse_money({"min": 140000, "max": 180000}) == 140000
    assert parse_money({"minAmount": "$150k"}) == 150000


def test_parse_money_uses_lower_bound_for_salary_ranges():
    assert parse_money("$90 - $120k base") == 90000
    assert parse_money("120k - 180k") == 120000


def test_role_family_inference_keeps_incident_manager_operational():
    assert infer_role_family("Incident Manager for Linux on-call incident response") == "sre_infra_ops"


def test_role_family_inference_keeps_executive_roles_management():
    assert infer_role_family("VP of Infrastructure Operations and people management") == "management"
