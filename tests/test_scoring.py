from pathlib import Path

import yaml

from labor_sieve.config import config_from_data
from labor_sieve.models import Job
from labor_sieve.scoring import priority_bucket, score_job, score_jobs
from labor_sieve.sources.sample import SampleSource


ROOT = Path(__file__).resolve().parents[1]


def load_config():
    data = yaml.safe_load((ROOT / "config.example.yaml").read_text(encoding="utf-8"))
    return config_from_data(data)


def test_priority_bucket_boundaries():
    assert priority_bucket(100) == "P0"
    assert priority_bucket(90) == "P0"
    assert priority_bucket(89) == "P1"
    assert priority_bucket(80) == "P1"
    assert priority_bucket(79) == "P2"
    assert priority_bucket(65) == "P2"
    assert priority_bucket(64) == "P3"
    assert priority_bucket(50) == "P3"
    assert priority_bucket(49) == "rejected"


def test_sample_jobs_exercise_expected_buckets():
    config = load_config()
    scored = score_jobs(SampleSource().fetch(), config)
    by_id = {item.job.id: item for item in scored}

    assert by_id["sample-ops-001"].priority in {"P0", "P1"}
    assert by_id["sample-sre-001"].priority == "P0"
    assert by_id["sample-logistics-001"].priority in {"P1", "P2"}
    assert by_id["sample-implementation-001"].priority in {"P1", "P2"}
    assert by_id["sample-software-001"].priority == "rejected"
    assert by_id["sample-executive-001"].priority == "rejected"
    assert by_id["sample-unknown-001"].priority == "rejected"


def test_local_on_site_location_gets_region_credit():
    config = load_config()
    item = score_job(
        Job(
            id="local-onsite",
            title="Data Center Operations Technician",
            company="Example Data Center",
            location="On-site - Petersburg, VA",
            remote=False,
            hybrid=False,
            seniority="mid",
            role_family="data_center_ops",
            compensation_base_min=125000,
            url="https://example.invalid/jobs/local-onsite",
            description="Hardware diagnostics, Linux fleet support, and data center operations.",
            tags=["data center", "hardware"],
            source="test",
            source_id="local-onsite",
        ),
        config,
    )

    assert any("local on-site location On-site - Petersburg, VA accepted" in reason for reason in item.reasons)


def test_hybrid_outside_accepted_locations_is_capped_below_p1():
    config = load_config()
    item = score_job(
        Job(
            id="hybrid-ny",
            title="Senior Linux SRE",
            company="Example Co",
            location="Hybrid - New York, NY",
            remote=False,
            hybrid=True,
            seniority="senior",
            role_family="sre_infra_ops",
            compensation_base_min=180000,
            url="https://example.invalid/jobs/hybrid-ny",
            description="Linux SRE incident response automation capacity planning.",
            tags=["linux", "sre"],
            source="test",
            source_id="hybrid-ny",
        ),
        config,
    )

    assert item.priority not in {"P0", "P1"}
    assert item.score <= 64
    assert any("not in accepted_locations" in reason for reason in item.reasons)


def test_remote_restricted_outside_accepted_remote_locations_is_capped_below_p1():
    config = load_config()
    item = score_job(
        Job(
            id="remote-au",
            title="Senior Linux SRE",
            company="Example Co",
            location="Remote - Australia",
            remote=True,
            hybrid=False,
            seniority="senior",
            role_family="sre_infra_ops",
            compensation_base_min=180000,
            url="https://example.invalid/jobs/remote-au",
            description="Linux SRE incident response automation capacity planning.",
            tags=["linux", "sre"],
            source="test",
            source_id="remote-au",
        ),
        config,
    )

    assert item.priority not in {"P0", "P1"}
    assert item.score <= 64
    assert any("accepted_remote_locations" in reason for reason in item.reasons)


def test_software_engineer_title_is_capped_below_p1():
    config = load_config()
    item = score_job(
        Job(
            id="software-infra",
            title="Senior Software Engineer, Infrastructure",
            company="Example Co",
            location="Remote - United States",
            remote=True,
            hybrid=False,
            seniority="senior",
            role_family="platform_ops",
            compensation_base_min=200000,
            url="https://example.invalid/jobs/software-infra",
            description="Infrastructure automation incident response Linux reliability.",
            tags=["linux", "automation"],
            source="test",
            source_id="software-infra",
        ),
        config,
    )

    assert item.priority not in {"P0", "P1"}
    assert item.score <= 64
    assert any("software engineer title matched" in reason for reason in item.reasons)


def test_manager_title_is_rejected_by_default():
    config = load_config()
    item = score_job(
        Job(
            id="manager",
            title="Infrastructure Operations Manager",
            company="Example Co",
            location="Remote - United States",
            remote=True,
            hybrid=False,
            seniority="senior",
            role_family="sre_infra_ops",
            compensation_base_min=200000,
            url="https://example.invalid/jobs/manager",
            description="Linux incident response automation capacity planning.",
            tags=["linux"],
            source="test",
            source_id="manager",
        ),
        config,
    )

    assert item.priority == "rejected"
    assert item.score <= 49
    assert any("management title term matched" in reason for reason in item.reasons)
