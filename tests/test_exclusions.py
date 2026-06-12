from pathlib import Path

import yaml

from labor_sieve.config import config_from_data
from labor_sieve.exclusions import apply_exclusions
from labor_sieve.models import Job


ROOT = Path(__file__).resolve().parents[1]


def load_example():
    return yaml.safe_load((ROOT / "config.example.yaml").read_text(encoding="utf-8"))


def test_apply_exclusions_filters_company_url_and_source_id():
    data = load_example()
    data["exclusions"]["companies"] = ["Palantir"]
    data["exclusions"]["urls"] = ["https://example.invalid/jobs/keep?utm_source=test"]
    data["exclusions"]["source_ids"] = ["ashby:abc123"]
    config = config_from_data(data)

    jobs = [
        job(company="Palantir Technologies", url="https://example.invalid/jobs/company", source_id="company"),
        job(company="Example Co", url="https://example.invalid/jobs/keep", source_id="url"),
        job(company="Example Co", url="https://example.invalid/jobs/source", source="ashby", source_id="abc123"),
        job(company="Example Co", url="https://example.invalid/jobs/kept", source_id="kept"),
    ]

    kept, excluded_count = apply_exclusions(jobs, config)

    assert excluded_count == 3
    assert [item.source_id for item in kept] == ["kept"]


def job(
    *,
    company: str,
    url: str,
    source: str = "test",
    source_id: str,
) -> Job:
    return Job(
        id=source_id,
        title="Linux SRE",
        company=company,
        location="Remote - United States",
        remote=True,
        hybrid=False,
        seniority="senior",
        role_family="sre_infra_ops",
        compensation_base_min=None,
        url=url,
        description="Linux reliability.",
        tags=[],
        source=source,
        source_id=source_id,
    )
