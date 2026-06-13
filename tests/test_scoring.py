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


def test_hybrid_remote_outside_accepted_locations_is_capped_below_p1():
    config = load_config()
    item = score_job(
        Job(
            id="remote-hybrid-sf",
            title="Senior Linux SRE",
            company="Example Co",
            location="Remote / Hybrid - San Francisco, CA",
            remote=True,
            hybrid=True,
            seniority="senior",
            role_family="sre_infra_ops",
            compensation_base_min=180000,
            url="https://example.invalid/jobs/remote-hybrid-sf",
            description="Linux SRE incident response automation capacity planning.",
            tags=["linux", "sre"],
            source="test",
            source_id="remote-hybrid-sf",
        ),
        config,
    )

    assert item.priority not in {"P0", "P1"}
    assert item.score <= 64
    assert any("hybrid location" in reason and "not in accepted_locations" in reason for reason in item.reasons)


def test_on_site_outside_accepted_locations_is_capped_below_p1():
    config = load_config()
    item = score_job(
        Job(
            id="onsite-sf",
            title="Senior Linux SRE",
            company="Example Co",
            location="San Francisco, CA",
            remote=False,
            hybrid=False,
            seniority="senior",
            role_family="sre_infra_ops",
            compensation_base_min=180000,
            url="https://example.invalid/jobs/onsite-sf",
            description="Linux SRE incident response automation capacity planning.",
            tags=["linux", "sre"],
            source="test",
            source_id="onsite-sf",
        ),
        config,
    )

    assert item.priority not in {"P0", "P1"}
    assert item.score <= 64
    assert any("outside accepted_locations" in reason for reason in item.reasons)


def test_fleet_operations_engineer_reaches_p0_when_location_matches():
    config = load_config()
    item = score_job(
        Job(
            id="fleet-ops",
            title="Operations Engineer, Fleet Reliability",
            company="Example Co",
            location="New York, NY / Plano, TX / Bellevue, WA / Sunnyvale, CA / Richmond, VA",
            remote=False,
            hybrid=False,
            seniority="mid",
            role_family="data_center_ops",
            compensation_base_min=None,
            url="https://example.invalid/jobs/fleet-ops",
            description="Data center operations, fleet reliability, hardware automation, and troubleshooting.",
            tags=["data center", "fleet", "reliability", "hardware"],
            source="test",
            source_id="fleet-ops",
        ),
        config,
    )

    assert item.priority == "P0"
    assert item.score >= 90
    assert any("fleet operations title focus" in reason for reason in item.reasons)


def test_entry_compensation_uses_entry_floor():
    config = load_config()
    item = score_job(
        Job(
            id="entry-comp",
            title="Data Center Operations Technician",
            company="Example Co",
            location="Remote - United States",
            remote=True,
            hybrid=False,
            seniority="entry",
            role_family="data_center_ops",
            compensation_base_min=90000,
            url="https://example.invalid/jobs/entry-comp",
            description="Data center operations, hardware troubleshooting, and reliability.",
            tags=["data center", "hardware"],
            source="test",
            source_id="entry-comp",
        ),
        config,
    )

    assert any("base compensation meets entry compensation floor $85,000" in reason for reason in item.reasons)


def test_senior_compensation_uses_senior_floor():
    config = load_config()
    item = score_job(
        Job(
            id="senior-comp",
            title="Senior Data Center Operations Engineer",
            company="Example Co",
            location="Remote - United States",
            remote=True,
            hybrid=False,
            seniority="senior",
            role_family="data_center_ops",
            compensation_base_min=90000,
            url="https://example.invalid/jobs/senior-comp",
            description="Data center operations, hardware troubleshooting, and reliability.",
            tags=["data center", "hardware"],
            source="test",
            source_id="senior-comp",
        ),
        config,
    )

    assert any("base compensation below senior compensation floor $105,000" in reason for reason in item.reasons)


def test_site_reliability_engineer_reaches_p1_with_default_remote_us_scope():
    config = load_config()
    item = score_job(
        Job(
            id="site-reliability-engineer",
            title="Site Reliability Engineer",
            company="Example Co",
            location="Remote - United States",
            remote=True,
            hybrid=False,
            seniority="mid",
            role_family="sre_infra_ops",
            compensation_base_min=None,
            url="https://example.invalid/jobs/site-reliability-engineer",
            description="Hardware infrastructure operations, incident response, automation, and reliability.",
            tags=["Hardware Infrastructure"],
            source="test",
            source_id="site-reliability-engineer",
        ),
        config,
    )

    assert item.priority in {"P0", "P1"}
    assert item.score >= 80
    assert any("site reliability title focus" in reason for reason in item.reasons)


def test_language_requirement_penalizes_unaccepted_bilingual_role():
    config = load_config()
    item = score_job(
        Job(
            id="bilingual-integration",
            title="Solutions Integration Engineer",
            company="Example Co",
            location="Remote - US",
            remote=True,
            hybrid=False,
            seniority="senior",
            role_family="data_center_ops",
            compensation_base_min=None,
            url="https://example.invalid/jobs/bilingual-integration",
            description=(
                "Bilingual speakers are required, ideally in Spanish. "
                "Customer implementation, troubleshooting, data center hardware integrations, and operations support."
            ),
            tags=["implementation", "hardware"],
            source="test",
            source_id="bilingual-integration",
        ),
        config,
    )

    assert item.priority not in {"P0", "P1"}
    assert any("language requirement -8" in reason for reason in item.reasons)


def test_language_requirement_accepts_configured_language():
    config = load_config()
    config.language_requirements.accepted.append("spanish")
    item = score_job(
        Job(
            id="spanish-accepted",
            title="Solutions Integration Engineer",
            company="Example Co",
            location="Remote - US",
            remote=True,
            hybrid=False,
            seniority="senior",
            role_family="data_center_ops",
            compensation_base_min=None,
            url="https://example.invalid/jobs/spanish-accepted",
            description=(
                "Bilingual speakers are required, ideally in Spanish. "
                "Customer implementation, troubleshooting, data center hardware integrations, and operations support."
            ),
            tags=["implementation", "hardware"],
            source="test",
            source_id="spanish-accepted",
        ),
        config,
    )

    assert not any("language requirement" in reason for reason in item.reasons)


def test_language_requirement_boosts_configured_language():
    config = load_config()
    config.language_requirements.boost.append("korean")
    item = score_job(
        Job(
            id="korean-boosted",
            title="Operations Reliability Engineer",
            company="Example Co",
            location="Remote - US",
            remote=True,
            hybrid=False,
            seniority="mid",
            role_family="fleet_reliability",
            compensation_base_min=None,
            url="https://example.invalid/jobs/korean-boosted",
            description="Korean language fluency preferred. Fleet reliability, automation, and troubleshooting.",
            tags=["fleet", "reliability"],
            source="test",
            source_id="korean-boosted",
        ),
        config,
    )

    assert any("language preference +6: korean" in reason for reason in item.reasons)
    assert not any("language requirement" in reason for reason in item.reasons)


def test_language_requirement_accepts_custom_configured_language_term():
    config = load_config()
    config.language_requirements.accepted.append("tagalog")
    item = score_job(
        Job(
            id="tagalog-accepted",
            title="Operations Reliability Engineer",
            company="Example Co",
            location="Remote - US",
            remote=True,
            hybrid=False,
            seniority="mid",
            role_family="fleet_reliability",
            compensation_base_min=None,
            url="https://example.invalid/jobs/tagalog-accepted",
            description="Tagalog fluency required. Fleet reliability, automation, and troubleshooting.",
            tags=["fleet", "reliability"],
            source="test",
            source_id="tagalog-accepted",
        ),
        config,
    )

    assert not any("language requirement" in reason for reason in item.reasons)


def test_language_requirement_boosts_custom_configured_language_phrase():
    config = load_config()
    config.language_requirements.boost.append("american sign language")
    item = score_job(
        Job(
            id="asl-boosted",
            title="Operations Reliability Engineer",
            company="Example Co",
            location="Remote - US",
            remote=True,
            hybrid=False,
            seniority="mid",
            role_family="fleet_reliability",
            compensation_base_min=None,
            url="https://example.invalid/jobs/asl-boosted",
            description="American Sign Language proficiency preferred. Fleet reliability and troubleshooting.",
            tags=["fleet", "reliability"],
            source="test",
            source_id="asl-boosted",
        ),
        config,
    )

    assert any("language preference +6: american sign language" in reason for reason in item.reasons)
    assert not any("language requirement" in reason for reason in item.reasons)


def test_language_requirement_treats_asl_as_neutral_by_default():
    config = load_config()
    item = score_job(
        Job(
            id="asl-neutral",
            title="Operations Reliability Engineer",
            company="Example Co",
            location="Remote - US",
            remote=True,
            hybrid=False,
            seniority="mid",
            role_family="fleet_reliability",
            compensation_base_min=None,
            url="https://example.invalid/jobs/asl-neutral",
            description="ASL proficiency preferred. Fleet reliability and troubleshooting.",
            tags=["fleet", "reliability"],
            source="test",
            source_id="asl-neutral",
        ),
        config,
    )

    assert not any("language requirement" in reason for reason in item.reasons)


def test_language_requirement_treats_american_sign_language_as_neutral_by_default():
    config = load_config()
    item = score_job(
        Job(
            id="american-sign-language-neutral",
            title="Operations Reliability Engineer",
            company="Example Co",
            location="Remote - US",
            remote=True,
            hybrid=False,
            seniority="mid",
            role_family="fleet_reliability",
            compensation_base_min=None,
            url="https://example.invalid/jobs/american-sign-language-neutral",
            description="American Sign Language proficiency preferred. Fleet reliability and troubleshooting.",
            tags=["fleet", "reliability"],
            source="test",
            source_id="american-sign-language-neutral",
        ),
        config,
    )

    assert not any("language requirement" in reason for reason in item.reasons)


def test_language_requirement_does_not_penalize_bilingual_asl_by_default():
    config = load_config()
    item = score_job(
        Job(
            id="bilingual-asl-neutral",
            title="Operations Reliability Engineer",
            company="Example Co",
            location="Remote - US",
            remote=True,
            hybrid=False,
            seniority="mid",
            role_family="fleet_reliability",
            compensation_base_min=None,
            url="https://example.invalid/jobs/bilingual-asl-neutral",
            description="Bilingual required. ASL proficiency preferred. Fleet reliability and troubleshooting.",
            tags=["fleet", "reliability"],
            source="test",
            source_id="bilingual-asl-neutral",
        ),
        config,
    )

    assert not any("language requirement" in reason for reason in item.reasons)


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


def test_sales_engineer_title_is_capped_below_p1():
    config = load_config()
    item = score_job(
        Job(
            id="sales-engineer",
            title="Sales Engineer I, SE Desk - Southeast",
            company="Example Co",
            location="Remote - United States",
            remote=True,
            hybrid=False,
            seniority="mid",
            role_family="data_center_ops",
            compensation_base_min=180000,
            url="https://example.invalid/jobs/sales-engineer",
            description="Fleet hardware integrations, customer troubleshooting, and operations support.",
            tags=["fleet", "hardware"],
            source="test",
            source_id="sales-engineer",
        ),
        config,
    )

    assert item.priority not in {"P0", "P1"}
    assert item.score <= 64
    assert any("sales engineer title matched" in reason for reason in item.reasons)


def test_scientist_title_is_capped_below_p1():
    config = load_config()
    item = score_job(
        Job(
            id="applied-scientist",
            title="Sr Staff / Staff Applied Scientist",
            company="Example Co",
            location="Remote - United States",
            remote=True,
            hybrid=False,
            seniority="staff",
            role_family="data_center_ops",
            compensation_base_min=220000,
            url="https://example.invalid/jobs/applied-scientist",
            description="Fleet telemetry, capacity planning, reliability, and automation.",
            tags=["fleet", "automation"],
            source="test",
            source_id="applied-scientist",
        ),
        config,
    )

    assert item.priority not in {"P0", "P1"}
    assert item.score <= 64
    assert any("scientist title matched" in reason for reason in item.reasons)


def test_networking_role_family_is_capped_below_p1_by_default():
    config = load_config()
    item = score_job(
        Job(
            id="network-engineer",
            title="Staff Network Engineer, Deployment",
            company="Example Co",
            location="Remote - United States",
            remote=True,
            hybrid=False,
            seniority="staff",
            role_family="networking",
            compensation_base_min=220000,
            url="https://example.invalid/jobs/network-engineer",
            description="Data center hardware fleet reliability automation.",
            tags=["data center", "hardware", "fleet"],
            source="test",
            source_id="network-engineer",
        ),
        config,
    )

    assert item.priority not in {"P0", "P1"}
    assert item.score <= 64
    assert any("networking role family is low-weighted" in reason for reason in item.reasons)


def test_trade_field_services_title_is_capped_below_p1():
    config = load_config()
    item = score_job(
        Job(
            id="master-electrician",
            title="Master Electrician - Field Services",
            company="Example Co",
            location="Remote - US",
            remote=True,
            hybrid=False,
            seniority="senior",
            role_family="data_center_ops",
            compensation_base_min=None,
            url="https://example.invalid/jobs/master-electrician",
            description="Data center hardware deployment, field services, and troubleshooting.",
            tags=["data center", "hardware"],
            source="test",
            source_id="master-electrician",
        ),
        config,
    )

    assert item.priority not in {"P0", "P1"}
    assert item.score <= 64
    assert any("trade or field-services title matched" in reason for reason in item.reasons)


def test_security_title_is_capped_below_p1():
    config = load_config()
    item = score_job(
        Job(
            id="physical-security",
            title="Data Center Physical Security Regional Lead",
            company="Example Co",
            location="Remote - US",
            remote=True,
            hybrid=False,
            seniority="senior",
            role_family="data_center_ops",
            compensation_base_min=162400,
            url="https://example.invalid/jobs/physical-security",
            description="Data center physical security operations and regional response.",
            tags=["data center", "security"],
            source="test",
            source_id="physical-security",
        ),
        config,
    )

    assert item.priority not in {"P0", "P1"}
    assert item.score <= 64
    assert any("security title matched" in reason for reason in item.reasons)


def test_service_desk_title_is_capped_below_p1():
    config = load_config()
    item = score_job(
        Job(
            id="service-desk",
            title="Service Desk Analyst 11am 8pm",
            company="Example Co",
            location="Pennsylvania, Pennsylvania, United States",
            remote=True,
            hybrid=False,
            seniority="mid",
            role_family="data_center_ops",
            compensation_base_min=None,
            url="https://example.invalid/jobs/service-desk",
            description="Customer support, troubleshooting, hardware, and operational response.",
            tags=["customer support", "hardware"],
            source="test",
            source_id="service-desk",
        ),
        config,
    )

    assert item.priority not in {"P0", "P1"}
    assert item.score <= 64
    assert any("service desk title matched" in reason for reason in item.reasons)


def test_manufacturing_engineering_title_is_capped_below_p1():
    config = load_config()
    item = score_job(
        Job(
            id="manufacturing-test",
            title="Manufacturing Test Engineer, AI Compute Infrastructure",
            company="Example Co",
            location="Remote - United States",
            remote=True,
            hybrid=False,
            seniority="senior",
            role_family="platform_ops",
            compensation_base_min=205000,
            url="https://example.invalid/jobs/manufacturing-test",
            description="AI compute infrastructure, hardware automation, and reliability.",
            tags=["hardware", "infrastructure"],
            source="test",
            source_id="manufacturing-test",
        ),
        config,
    )

    assert item.priority not in {"P0", "P1"}
    assert item.score <= 64
    assert any("manufacturing engineering title matched" in reason for reason in item.reasons)


def test_staff_roles_are_above_default_seniority_range():
    config = load_config()
    item = score_job(
        Job(
            id="staff-platform",
            title="Staff ML Engineer - ML Infrastructure",
            company="Example Co",
            location="Remote - US",
            remote=True,
            hybrid=False,
            seniority="staff",
            role_family="platform_ops",
            compensation_base_min=None,
            url="https://example.invalid/jobs/staff-platform",
            description="Infrastructure automation reliability and capacity planning.",
            tags=["infrastructure", "automation"],
            source="test",
            source_id="staff-platform",
        ),
        config,
    )

    assert item.priority not in {"P0", "P1"}
    assert any("seniority staff above target range" in reason for reason in item.reasons)


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
