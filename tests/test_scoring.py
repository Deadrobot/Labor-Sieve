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

    assert by_id["sample-ops-001"].priority == "P0"
    assert by_id["sample-sre-001"].priority == "P0"
    assert by_id["sample-logistics-001"].priority in {"P0", "P1"}
    assert by_id["sample-implementation-001"].priority in {"P0", "P1"}
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
