import csv
from pathlib import Path

import yaml

from labor_sieve.config import config_from_data
from labor_sieve.models import Job, ScoredJob
from labor_sieve.reports import (
    render_html_report,
    render_terminal_summary,
    render_text_report,
    write_csv_report,
    write_reports,
)
from labor_sieve.scoring import score_jobs
from labor_sieve.sources.sample import SampleSource


ROOT = Path(__file__).resolve().parents[1]


def load_config(tmp_path):
    data = yaml.safe_load((ROOT / "config.example.yaml").read_text(encoding="utf-8"))
    data["output"]["directory"] = str(tmp_path / "output")
    return config_from_data(data)


def test_text_report_includes_all_priority_groups_and_block_entries(tmp_path):
    config = load_config(tmp_path)
    scored = score_jobs(SampleSource().fetch(), config)

    report = render_text_report(scored)

    assert "## P0" in report
    assert "## P1" in report
    assert "## P2" in report
    assert "## P3" in report
    assert "## rejected" in report
    assert "Operations Reliability Engineer" in report
    assert "Senior Full-Stack Software Engineer" in report
    assert "  Company:" in report
    assert "  Score reasons:" in report


def test_write_reports_creates_enabled_formats(tmp_path):
    config = load_config(tmp_path)
    scored = score_jobs(SampleSource().fetch(), config)

    written = write_reports(scored, config)

    assert set(written) == {"txt", "csv", "json", "html"}
    for path in written.values():
        assert path.exists()
        assert path.read_text(encoding="utf-8")


def test_terminal_summary_only_lists_p0_p1_matches(tmp_path):
    config = load_config(tmp_path)
    scored = score_jobs(SampleSource().fetch(), config)
    written = write_reports(scored, config)

    summary = render_terminal_summary(scored, written)

    assert "Scanned 7 jobs." in summary
    assert "P0/P1 matches:" in summary
    assert "Operations Reliability Engineer" in summary
    assert "Senior Full-Stack Software Engineer" not in summary


def test_terminal_summary_limits_p0_and_p1_output(tmp_path):
    config = load_config(tmp_path)
    config.output.terminal_p0_limit = 1
    config.output.terminal_p1_limit = 1
    scored = [
        ScoredJob(job=summary_job("p0-a"), score=95, priority="P0", reasons=[]),
        ScoredJob(job=summary_job("p0-b"), score=94, priority="P0", reasons=[]),
        ScoredJob(job=summary_job("p1-a"), score=85, priority="P1", reasons=[]),
        ScoredJob(job=summary_job("p1-b"), score=84, priority="P1", reasons=[]),
    ]

    summary = render_terminal_summary(scored, {}, config=config)

    assert "p0-a at Example Co" in summary
    assert "p0-b at Example Co" not in summary
    assert "p1-a at Example Co" in summary
    assert "p1-b at Example Co" not in summary
    assert "... 2 additional P0/P1 matches are in the full reports." in summary


def test_html_report_does_not_link_unsafe_urls(tmp_path):
    config = load_config(tmp_path)
    jobs = SampleSource().fetch()
    jobs[0].url = "javascript:alert(1)"
    scored = score_jobs([jobs[0]], config)

    report = render_html_report(scored)

    assert 'href="javascript:alert(1)"' not in report
    assert "javascript:alert(1)" in report


def test_csv_report_neutralizes_formula_prefixed_cells(tmp_path):
    path = tmp_path / "latest.csv"
    job = Job(
        id="1",
        title='=HYPERLINK("http://example.invalid","click")',
        company="@example",
        location="+Remote",
        remote=True,
        hybrid=False,
        seniority="senior",
        role_family="sre_infra_ops",
        compensation_base_min=None,
        url="https://example.invalid/job",
        description="-SUM(1,1)",
        tags=["=tag"],
        source="local_file",
        source_id="=source-id",
        merged_sources=["@merged"],
    )
    scored = [ScoredJob(job=job, score=100, priority="P0", reasons=["=reason"])]

    write_csv_report(scored, path)

    with path.open("r", newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["title"].startswith("'=")
    assert row["company"].startswith("'@")
    assert row["location"].startswith("'+")
    assert row["description"].startswith("'-")
    assert row["tags"].startswith("'=")
    assert row["reasons"].startswith("'=")
    assert row["source_id"].startswith("'=")
    assert row["merged_sources"].startswith("'@")
    assert row["url"] == "https://example.invalid/job"


def summary_job(title: str) -> Job:
    return Job(
        id=title,
        title=title,
        company="Example Co",
        location="Remote - United States",
        remote=True,
        hybrid=False,
        seniority="senior",
        role_family="sre_infra_ops",
        compensation_base_min=150000,
        url=f"https://example.invalid/jobs/{title}",
        description="",
        tags=[],
        source="test",
        source_id=title,
    )
