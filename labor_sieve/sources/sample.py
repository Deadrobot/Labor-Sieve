"""Sample source with fake jobs for testing scoring and reports."""

from __future__ import annotations

from labor_sieve.models import Job
from labor_sieve.sources.base import JobSource


class SampleSource(JobSource):
    name = "sample"

    def fetch(self) -> list[Job]:
        return [
            Job(
                id="sample-ops-001",
                title="Operations Reliability Engineer",
                company="Regional Fulfillment Systems",
                location="Remote - United States",
                remote=True,
                hybrid=False,
                seniority="senior",
                role_family="fleet_reliability",
                compensation_base_min=168000,
                url="https://example.invalid/jobs/operations-reliability-engineer",
                tags=["production operations", "incident response", "automation", "fleet"],
                description=(
                    "Own production operations for a large distributed fleet. Improve runbooks, "
                    "incident response, reliability reviews, automation, and capacity planning."
                ),
                source=self.name,
                source_id="sample-ops-001",
            ),
            Job(
                id="sample-sre-001",
                title="Linux SRE - Infrastructure Operations",
                company="Northstar Compute",
                location="Remote - United States",
                remote=True,
                hybrid=False,
                seniority="senior",
                role_family="sre_infra_ops",
                compensation_base_min=172000,
                url="https://example.invalid/jobs/linux-sre-infra-ops",
                tags=["linux", "sre", "observability", "shell"],
                description=(
                    "Operate Linux infrastructure, build automation, handle incident response, "
                    "improve observability, and support capacity planning for production systems."
                ),
                source=self.name,
                source_id="sample-sre-001",
            ),
            Job(
                id="sample-logistics-001",
                title="Logistics Process Improvement Lead",
                company="Relay Warehouse Network",
                location="Hybrid - Richmond, VA",
                remote=False,
                hybrid=True,
                seniority="mid",
                role_family="logistics_process",
                compensation_base_min=126000,
                url="https://example.invalid/jobs/logistics-process-lead",
                tags=["logistics", "process improvement", "workflow", "kpi"],
                description=(
                    "Improve logistics workflow, SOPs, operations analytics, KPI tracking, "
                    "root cause reviews, and cross-site process quality."
                ),
                source=self.name,
                source_id="sample-logistics-001",
            ),
            Job(
                id="sample-implementation-001",
                title="Implementation Support Engineer",
                company="LaunchOps Software",
                location="Remote - United States",
                remote=True,
                hybrid=False,
                seniority="mid",
                role_family="implementation_support",
                compensation_base_min=118000,
                url="https://example.invalid/jobs/implementation-support-engineer",
                tags=["implementation", "customer support", "troubleshooting"],
                description=(
                    "Support technical implementations, customer support escalations, Linux-based "
                    "troubleshooting, integration rollout checks, and internal runbook updates."
                ),
                source=self.name,
                source_id="sample-implementation-001",
            ),
            Job(
                id="sample-software-001",
                title="Senior Full-Stack Software Engineer",
                company="Consumer Apps Lab",
                location="Remote - United States",
                remote=True,
                hybrid=False,
                seniority="senior",
                role_family="software_engineering",
                compensation_base_min=190000,
                url="https://example.invalid/jobs/full-stack-software-engineer",
                tags=["frontend", "product engineering", "leetcode"],
                description=(
                    "Build frontend product features for a consumer mobile app. Interview process "
                    "focuses on leetcode and full-stack product engineering."
                ),
                source=self.name,
                source_id="sample-software-001",
            ),
            Job(
                id="sample-executive-001",
                title="VP of Infrastructure Operations",
                company="ScaleGrid Holdings",
                location="Remote - United States",
                remote=True,
                hybrid=False,
                seniority="executive",
                role_family="management",
                compensation_base_min=260000,
                url="https://example.invalid/jobs/vp-infrastructure-operations",
                tags=["vp", "people management", "director"],
                description=(
                    "Executive role owning headcount planning, director management, quarterly "
                    "strategy, people management, and executive operating reviews."
                ),
                source=self.name,
                source_id="sample-executive-001",
            ),
            Job(
                id="sample-unknown-001",
                title="Operations Associate",
                company="Generic Staffing Group",
                location="On-site - Petersburg, VA",
                remote=False,
                hybrid=False,
                seniority="entry",
                role_family="unknown",
                compensation_base_min=52000,
                url="https://example.invalid/jobs/operations-associate",
                tags=["general labor"],
                description=(
                    "Entry-level operations associate role with broad duties, changing schedules, "
                    "and limited technical ownership."
                ),
                source=self.name,
                source_id="sample-unknown-001",
            ),
        ]
