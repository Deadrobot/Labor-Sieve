import csv
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from labor_sieve.net import MAX_REMOTE_RESPONSE_BYTES, RedirectBlockedError, ResponseTooLargeError
from labor_sieve.sources.ashby import MAX_ASHBY_RESPONSE_BYTES, AshbySource, normalize_ashby_record
from labor_sieve.sources.arbeitnow import ArbeitnowSource
from labor_sieve.sources.base import SourceError
from labor_sieve.sources.greenhouse import GreenhouseSource
from labor_sieve.sources.lever import LeverSource, normalize_lever_record
from labor_sieve.sources.local_file import LocalFileSource
from labor_sieve.sources.normalization import infer_role_family, normalize_job_record, parse_money
from labor_sieve.sources.remoteok import RemoteOkSource
from labor_sieve.sources.workday import WorkdaySite, WorkdaySource, normalize_workday_record, parse_workday_site


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


def test_normalization_handles_workday_style_record():
    site = parse_workday_site(
        WorkdaySite(
            company="Example Company",
            url="https://example.wd5.myworkdayjobs.com/ExampleExternalCareerSite",
        )
    )
    normalized = normalize_workday_record(
        {
            "externalPath": "/en-US/ExampleExternalCareerSite/job/Austin-TX/Linux-SRE_R123",
            "title": "Senior Linux SRE",
            "locationsText": "Austin, TX",
            "bulletFields": ["Full time", "Remote"],
        },
        {
            "jobPostingInfo": {
                "jobReqId": "R123",
                "jobDescription": "<p>Linux incident response and automation.</p>",
                "payRange": "$140k - $160k",
            }
        },
        site,
    )
    job = normalize_job_record(normalized, source_name="workday", index=1, company_default="Example Company")

    assert job.id == "R123"
    assert job.title == "Senior Linux SRE"
    assert job.company == "Example Company"
    assert job.url == "https://example.wd5.myworkdayjobs.com/en-US/ExampleExternalCareerSite/job/Austin-TX/Linux-SRE_R123"
    assert job.location == "Austin, TX"
    assert job.remote is True
    assert job.role_family == "sre_infra_ops"
    assert job.compensation_base_min == 140000
    assert "Full time" in job.tags


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


def test_remoteok_source_fetches_postings(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size=-1):
            return json.dumps(
                [
                    {"legal": "metadata"},
                    {
                        "id": "remoteok-1",
                        "position": "Senior Linux SRE",
                        "company": "Distributed Compute",
                        "location": "Remote - United States",
                        "url": "https://remoteok.com/remote-jobs/remoteok-1",
                        "description": "<p>Linux incident response.</p>",
                        "tags": ["linux", "sre"],
                        "salary_min": 140000,
                    },
                ]
            ).encode("utf-8")

    def fake_open(request, timeout):
        assert request.full_url == "https://remoteok.com/api"
        assert timeout == 7
        return FakeResponse()

    monkeypatch.setattr("labor_sieve.sources.remoteok.open_without_redirects", fake_open)

    jobs = RemoteOkSource(timeout_seconds=7, max_jobs=10).fetch()

    assert len(jobs) == 1
    assert jobs[0].source == "remoteok"
    assert jobs[0].source_id == "remoteok-1"
    assert jobs[0].remote is True
    assert jobs[0].compensation_base_min == 140000
    assert jobs[0].tags == ["linux", "sre"]


def test_arbeitnow_source_fetches_postings(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size=-1):
            return json.dumps(
                {
                    "data": [
                        {
                            "slug": "linux-sre-richmond",
                            "company_name": "Regional Compute",
                            "title": "Linux SRE",
                            "description": "<p>Incident response and automation.</p>",
                            "remote": True,
                            "url": "https://www.arbeitnow.com/jobs/linux-sre-richmond",
                            "tags": ["Remote", "System and Network Administration"],
                            "job_types": ["Full Time"],
                            "location": "Remote",
                        }
                    ]
                }
            ).encode("utf-8")

    seen_urls = []

    def fake_open(request, timeout):
        seen_urls.append(request.full_url)
        assert timeout == 7
        return FakeResponse()

    monkeypatch.setattr("labor_sieve.sources.arbeitnow.open_without_redirects", fake_open)

    jobs = ArbeitnowSource(timeout_seconds=7, max_pages=1, max_jobs=10).fetch()

    assert len(jobs) == 1
    assert jobs[0].source == "arbeitnow"
    assert jobs[0].source_id == "linux-sre-richmond"
    assert jobs[0].remote is True
    assert jobs[0].tags == ["Remote", "System and Network Administration", "Full Time"]
    assert seen_urls == ["https://www.arbeitnow.com/api/job-board-api?page=1"]


def test_arbeitnow_source_fetches_multiple_pages_until_limit(monkeypatch):
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size=-1):
            return json.dumps(self.payload).encode("utf-8")

    def fake_open(request, timeout):
        if request.full_url.endswith("page=1"):
            return FakeResponse(
                {
                    "data": [
                        {
                            "slug": "job-1",
                            "company_name": "Company One",
                            "title": "Linux SRE",
                            "remote": True,
                            "url": "https://example.invalid/job-1",
                            "location": "Remote",
                        }
                    ]
                }
            )
        return FakeResponse(
            {
                "data": [
                    {
                        "slug": "job-2",
                        "company_name": "Company Two",
                        "title": "Data Center Technician",
                        "remote": False,
                        "url": "https://example.invalid/job-2",
                        "location": "Richmond, VA",
                    }
                ]
            }
        )

    monkeypatch.setattr("labor_sieve.sources.arbeitnow.open_without_redirects", fake_open)

    jobs = ArbeitnowSource(max_pages=2, max_jobs=2).fetch()

    assert [job.source_id for job in jobs] == ["job-1", "job-2"]


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


def test_ashby_source_allows_openai_sized_payload(monkeypatch):
    openai_payload_bytes = 12103473

    class FakeResponse:
        headers = {"Content-Length": str(openai_payload_bytes)}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size=-1):
            return json.dumps({"jobs": [{"id": "abc", "title": "Linux SRE", "jobUrl": "https://example.invalid"}]}).encode(
                "utf-8"
            )

    def fake_open(request, timeout):
        return FakeResponse()

    monkeypatch.setattr("labor_sieve.sources.ashby.open_without_redirects", fake_open)

    assert openai_payload_bytes > MAX_REMOTE_RESPONSE_BYTES
    assert MAX_ASHBY_RESPONSE_BYTES > MAX_REMOTE_RESPONSE_BYTES
    jobs = AshbySource(["openai"]).fetch()

    assert len(jobs) == 1
    assert jobs[0].source_id == "abc"


def test_ashby_source_stops_slug_variants_after_oversized_response(monkeypatch):
    seen_urls = []

    def fake_open(request, timeout):
        seen_urls.append(request.full_url)
        raise ResponseTooLargeError("Ashby organization 'openai' response is larger than the byte limit.")

    monkeypatch.setattr("labor_sieve.sources.ashby.open_without_redirects", fake_open)

    with pytest.raises(SourceError):
        AshbySource(["openai"]).fetch()

    assert seen_urls == ["https://api.ashbyhq.com/posting-api/job-board/openai?includeCompensation=true"]


def test_ashby_source_keeps_successful_jobs_when_one_organization_times_out(monkeypatch):
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
        if "/slow?" in request.full_url:
            raise TimeoutError("timed out")
        return FakeResponse()

    monkeypatch.setattr("labor_sieve.sources.ashby.open_without_redirects", fake_open)

    source = AshbySource(["slow", "example"])
    jobs = source.fetch()

    assert len(jobs) == 1
    assert jobs[0].source_id == "abc"
    assert len(source.warnings) == 1
    assert "slow" in source.warnings[0]
    assert seen_urls == [
        "https://api.ashbyhq.com/posting-api/job-board/slow?includeCompensation=true",
        "https://api.ashbyhq.com/posting-api/job-board/example?includeCompensation=true",
    ]


def test_workday_source_fetches_postings_and_details(monkeypatch):
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size=-1):
            return json.dumps(self.payload).encode("utf-8")

    seen_requests = []

    def fake_open(request, timeout):
        seen_requests.append((request.get_method(), request.full_url, request.data))
        assert timeout == 7
        if request.full_url.endswith("/wday/cxs/example/ExampleExternalCareerSite/jobs"):
            assert request.get_method() == "POST"
            body = json.loads(request.data.decode("utf-8"))
            assert body["limit"] == 2
            assert body["offset"] == 0
            return FakeResponse(
                {
                    "total": 1,
                    "jobPostings": [
                        {
                            "externalPath": "/en-US/ExampleExternalCareerSite/job/Linux-SRE_R123",
                            "title": "Senior Linux SRE",
                            "locationsText": "Remote",
                            "bulletFields": ["Full time"],
                        }
                    ],
                }
            )
        assert request.full_url.endswith(
            "/wday/cxs/example/ExampleExternalCareerSite/en-US/ExampleExternalCareerSite/job/Linux-SRE_R123"
        )
        assert request.get_method() == "GET"
        return FakeResponse(
            {
                "jobPostingInfo": {
                    "jobReqId": "R123",
                    "jobDescription": "<p>Linux incident response.</p>",
                    "payRange": "$130k - $150k",
                }
            }
        )

    monkeypatch.setattr("labor_sieve.sources.workday.open_without_redirects", fake_open)

    jobs = WorkdaySource(
        [
            WorkdaySite(
                company="Example Company",
                url="https://example.wd5.myworkdayjobs.com/ExampleExternalCareerSite",
            )
        ],
        timeout_seconds=7,
        page_size=2,
    ).fetch()

    assert len(jobs) == 1
    assert jobs[0].source == "workday"
    assert jobs[0].source_id == "R123"
    assert jobs[0].compensation_base_min == 130000
    assert jobs[0].url == "https://example.wd5.myworkdayjobs.com/en-US/ExampleExternalCareerSite/job/Linux-SRE_R123"
    assert [method for method, _url, _data in seen_requests] == ["POST", "GET"]


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


def test_role_family_inference_respects_out_of_scope_title_terms():
    assert infer_role_family("Sales Engineer I", "fleet hardware customer operations") == "customer_operations"
    assert infer_role_family("Sr Staff Applied Scientist", "fleet reliability capacity planning") == "software_engineering"


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


def test_workday_source_blocks_redirects(monkeypatch):
    def fake_open(request, timeout):
        raise RedirectBlockedError("https://127.0.0.1/private")

    monkeypatch.setattr("labor_sieve.sources.workday.open_without_redirects", fake_open)

    with pytest.raises(SourceError, match="redirected to https://127.0.0.1/private"):
        WorkdaySource(
            [
                WorkdaySite(
                    company="Example Company",
                    url="https://example.wd5.myworkdayjobs.com/ExampleExternalCareerSite",
                )
            ]
        ).fetch()


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
