from labor_sieve.dedupe import dedupe_jobs
from labor_sieve.models import Job


def make_job(**overrides):
    values = {
        "id": "1",
        "title": "Senior Linux SRE",
        "company": "Example Co",
        "location": "Remote - United States",
        "remote": True,
        "hybrid": False,
        "seniority": "senior",
        "role_family": "sre_infra_ops",
        "compensation_base_min": None,
        "url": "https://example.invalid/jobs/1?utm_source=test",
        "description": "Linux operations.",
        "tags": ["linux"],
        "source": "greenhouse",
        "source_id": "1",
    }
    values.update(overrides)
    return Job(**values)


def test_dedupe_matches_tracking_url_variants_and_keeps_richer_record():
    jobs = [
        make_job(description="Short."),
        make_job(
            id="2",
            source="local_file",
            source_id="2",
            url="https://example.invalid/jobs/1",
            compensation_base_min=160000,
            description="Longer Linux operations description.",
            tags=["incident response"],
        ),
    ]

    deduped, duplicate_count = dedupe_jobs(jobs)

    assert duplicate_count == 1
    assert len(deduped) == 1
    assert deduped[0].compensation_base_min == 160000
    assert deduped[0].tags == ["linux", "incident response"]
    assert "greenhouse:1" in deduped[0].merged_sources
    assert "local_file:2" in deduped[0].merged_sources


def test_dedupe_matches_url_query_order_variants():
    jobs = [
        make_job(url="https://example.invalid/jobs/1?a=1&b=2"),
        make_job(id="2", source_id="2", url="https://example.invalid/jobs/1?b=2&a=1"),
    ]

    deduped, duplicate_count = dedupe_jobs(jobs)

    assert duplicate_count == 1
    assert len(deduped) == 1


def test_dedupe_matches_normalized_company_title_location_without_url():
    jobs = [
        make_job(id="1", url="", title="Sr. Linux SRE", source="lever", source_id="1"),
        make_job(id="2", url="", title="Senior Linux SRE", source="greenhouse", source_id="2"),
    ]

    deduped, duplicate_count = dedupe_jobs(jobs)

    assert duplicate_count == 1
    assert len(deduped) == 1
    assert deduped[0].merged_sources == ["lever:1", "greenhouse:2"]


def test_dedupe_does_not_merge_unknown_untitled_jobs_without_url():
    jobs = [
        make_job(id="1", title="Untitled job", company="Unknown company", url="", source_id="1"),
        make_job(id="2", title="Untitled job", company="Unknown company", url="", source_id="2"),
    ]

    deduped, duplicate_count = dedupe_jobs(jobs)

    assert duplicate_count == 0
    assert len(deduped) == 2
