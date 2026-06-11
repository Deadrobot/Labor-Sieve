from pathlib import Path

import yaml

from labor_sieve.config import config_from_data
from labor_sieve.reports import render_html_report, render_terminal_summary, render_text_report, write_reports
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


def test_html_report_does_not_link_unsafe_urls(tmp_path):
    config = load_config(tmp_path)
    jobs = SampleSource().fetch()
    jobs[0].url = "javascript:alert(1)"
    scored = score_jobs([jobs[0]], config)

    report = render_html_report(scored)

    assert 'href="javascript:alert(1)"' not in report
    assert "javascript:alert(1)" in report
