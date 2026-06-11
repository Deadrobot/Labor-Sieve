import csv
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from labor_sieve.net import RedirectBlockedError
from labor_sieve.sources.ashby import AshbySource, normalize_ashby_record
from labor_sieve.sources.base import SourceError
from labor_sieve.sources.greenhouse import GreenhouseSource
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


def test_normalization_handles_ashby_style_record():
    normalized = normalize_ashby_record(
        {
            "id": "ashby-job",
            "title": "Senior Data Center Operations Engineer",
            "locationName": "Remote - United States",
            "jobUrl": "https://jobs.ashbyhq.com/example/ashby-job",
            "descriptionHtml": "<p>Hardware diagnostics and Linux fleet reliability.</p>",
            "departmentName": "Infrastructure",
            "employmentType": "FullTime",
            "compensation": {"compensationTierSummary": "$120k - $150k"},
        },
        organization="example",
    )
    job = normalize_job_record(normalized, source_name="ashby", index=1, company_default="example")

    assert job.id == "ashby-job"
    assert job.title == "Senior Data Center Operations Engineer"
    assert job.company == "example"
    assert job.location == "Remote - United States"
    assert job.role_family == "data_center_ops"
    assert job.compensation_base_min == 120000
    assert "Infrastructure" in job.tags
    assert "FullTime" in job.tags


def test_lever_source_fetches_postings(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size=-1):
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

    def fake_open(request, timeout):
        assert "https://api.lever.co/v0/postings/example?mode=json" == request.full_url
        assert timeout == 7
        return FakeResponse()

    monkeypatch.setattr("labor_sieve.sources.lever.open_without_redirects", fake_open)

    jobs = LeverSource(["example"], timeout_seconds=7).fetch()

    assert len(jobs) == 1
    assert jobs[0].source == "lever"
    assert jobs[0].source_id == "abc"


def test_ashby_source_fetches_postings(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size=-1):
            return json.dumps(
                {
                    "jobs": [
                        {
                            "id": "hidden",
                            "title": "Hidden Role",
                            "isListed": False,
                            "jobUrl": "https://jobs.ashbyhq.com/example/hidden",
                        },
                        {
                            "id": "ashby-job",
                            "title": "Senior Linux SRE",
                            "jobUrl": "https://jobs.ashbyhq.com/example/ashby-job",
                            "descriptionHtml": "<p>Linux incident response.</p>",
                            "locationName": "Remote",
                            "compensation": {"compensationTierSummary": "$130k - $150k"},
                        }
                    ]
                }
            ).encode("utf-8")

    def fake_open(request, timeout):
        assert "https://api.ashbyhq.com/posting-api/job-board/example?includeCompensation=true" == request.full_url
        assert timeout == 7
        return FakeResponse()

    monkeypatch.setattr("labor_sieve.sources.ashby.open_without_redirects", fake_open)

    jobs = AshbySource(["example"], timeout_seconds=7).fetch()

    assert len(jobs) == 1
    assert jobs[0].source == "ashby"
    assert jobs[0].source_id == "ashby-job"
    assert jobs[0].compensation_base_min == 130000


def test_ashby_source_tries_slug_variants(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size=-1):
            return json.dumps({"jobs": [{"id": "abc", "title": "Linux SRE", "jobUrl": "https://example.invalid"}]}).encode(
                "utf-8"
            )

    seen_urls = []

    def fake_open(request, timeout):
        seen_urls.append(request.full_url)
        if "/ExampleOrg?" in request.full_url:
            raise HTTPError(request.full_url, 404, "not found", {}, None)
        return FakeResponse()

    monkeypatch.setattr("labor_sieve.sources.ashby.open_without_redirects", fake_open)

    jobs = AshbySource(["ExampleOrg"]).fetch()

    assert len(jobs) == 1
    assert seen_urls == [
        "https://api.ashbyhq.com/posting-api/job-board/ExampleOrg?includeCompensation=true",
        "https://api.ashbyhq.com/posting-api/job-board/exampleorg?includeCompensation=true",
    ]


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


def test_greenhouse_source_rejects_oversized_response(monkeypatch):
    class FakeResponse:
        headers = {"Content-Length": "11"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size=-1):
            return b"{}"

    monkeypatch.setattr("labor_sieve.sources.greenhouse.MAX_REMOTE_RESPONSE_BYTES", 10)
    monkeypatch.setattr(
        "labor_sieve.sources.greenhouse.open_without_redirects",
        lambda request, timeout: FakeResponse(),
    )

    with pytest.raises(SourceError, match="larger than the 10 byte limit"):
        GreenhouseSource(["example"]).fetch()


def test_greenhouse_source_blocks_redirects(monkeypatch):
    def fake_open(request, timeout):
        raise RedirectBlockedError("https://127.0.0.1/private")

    monkeypatch.setattr("labor_sieve.sources.greenhouse.open_without_redirects", fake_open)

    with pytest.raises(SourceError, match="redirected to https://127.0.0.1/private"):
        GreenhouseSource(["example"]).fetch()


def test_lever_source_blocks_redirects(monkeypatch):
    def fake_open(request, timeout):
        raise RedirectBlockedError("https://127.0.0.1/private")

    monkeypatch.setattr("labor_sieve.sources.lever.open_without_redirects", fake_open)

    with pytest.raises(SourceError, match="redirected to https://127.0.0.1/private"):
        LeverSource(["example"]).fetch()


def test_ashby_source_blocks_redirects(monkeypatch):
    def fake_open(request, timeout):
        raise RedirectBlockedError("https://127.0.0.1/private")

    monkeypatch.setattr("labor_sieve.sources.ashby.open_without_redirects", fake_open)

    with pytest.raises(SourceError, match="redirected to https://127.0.0.1/private"):
        AshbySource(["example"]).fetch()


def test_lever_source_rejects_excessive_records(monkeypatch):
    class FakeResponse:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size=-1):
            return json.dumps([{"text": "one"}, {"text": "two"}]).encode("utf-8")

    monkeypatch.setattr("labor_sieve.sources.lever.MAX_RECORDS_PER_SOURCE", 1)
    monkeypatch.setattr(
        "labor_sieve.sources.lever.open_without_redirects",
        lambda request, timeout: FakeResponse(),
    )

    with pytest.raises(SourceError, match="more than 1 records"):
        LeverSource(["example"]).fetch()


def test_ashby_source_rejects_excessive_records(monkeypatch):
    class FakeResponse:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size=-1):
            return json.dumps({"jobs": [{"title": "one"}, {"title": "two"}]}).encode("utf-8")

    monkeypatch.setattr("labor_sieve.sources.ashby.MAX_RECORDS_PER_SOURCE", 1)
    monkeypatch.setattr(
        "labor_sieve.sources.ashby.open_without_redirects",
        lambda request, timeout: FakeResponse(),
    )

    with pytest.raises(SourceError, match="more than 1 records"):
        AshbySource(["example"]).fetch()


def test_local_file_source_rejects_oversized_files(tmp_path, monkeypatch):
    path = tmp_path / "jobs.json"
    path.write_text('{"jobs": []}', encoding="utf-8")
    monkeypatch.setattr("labor_sieve.sources.local_file.MAX_LOCAL_FILE_BYTES", 5)

    with pytest.raises(SourceError, match="larger than the 5 byte limit"):
        LocalFileSource([str(path)]).fetch()


def test_local_file_source_rejects_excessive_csv_records(tmp_path, monkeypatch):
    path = tmp_path / "jobs.csv"
    path.write_text("title\none\ntwo\n", encoding="utf-8")
    monkeypatch.setattr("labor_sieve.sources.local_file.MAX_RECORDS_PER_SOURCE", 1)

    with pytest.raises(SourceError, match="contains more than 1 records"):
        LocalFileSource([str(path)]).fetch()
