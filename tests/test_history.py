import json

from labor_sieve.history import annotate_run_history, load_history, save_history
from labor_sieve.models import Job, ScoredJob
from labor_sieve.reports import render_json_report, render_terminal_summary, render_text_report


def test_history_annotations_track_new_seen_and_disappeared():
    scored = [
        ScoredJob(job=history_job("current", "Current Role"), score=90, priority="P0", reasons=["base score +10"])
    ]
    previous = {
        "https://example.invalid/current": previous_record("current", "Current Role", 80),
        "https://example.invalid/old": previous_record("old", "Old Role", 70),
    }

    history = annotate_run_history(scored, previous)

    assert history.new_count == 0
    assert history.seen_count == 1
    assert history.disappeared_count() == 1
    assert scored[0].history_status == "seen"
    assert scored[0].previous_score == 80
    assert scored[0].score_delta == 10


def test_save_and_load_history_round_trip(tmp_path, monkeypatch):
    monkeypatch.delenv("LABOR_SIEVE_SKIP_RUN_HISTORY", raising=False)
    path = tmp_path / "history.json"
    scored = [ScoredJob(job=history_job("job", "Job"), score=91, priority="P0", reasons=[])]

    save_history(scored, path)
    loaded = load_history(path)

    assert "https://example.invalid/job" in loaded
    assert loaded["https://example.invalid/job"].score == 91
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1


def test_reports_include_history_summary():
    scored = [
        ScoredJob(
            job=history_job("current", "Current Role"),
            score=90,
            priority="P0",
            reasons=["base score +10"],
            history_status="new",
        )
    ]
    history = annotate_run_history(scored, {"https://example.invalid/old": previous_record("old", "Old Role", 70)})

    text = render_text_report(scored, history=history)
    summary = render_terminal_summary(scored, {}, history=history)
    payload = json.loads(render_json_report(scored, history=history))

    assert "History: 1 new | 0 seen | 1 disappeared" in text
    assert "## Disappeared since last run" in text
    assert "History: 1 new | 0 seen | 1 disappeared" in summary
    assert payload["history"]["disappeared_count"] == 1
    assert payload["jobs"][0]["history_status"] == "new"


def history_job(job_id: str, title: str) -> Job:
    return Job(
        id=job_id,
        title=title,
        company="Example Co",
        location="Remote - United States",
        remote=True,
        hybrid=False,
        seniority="senior",
        role_family="sre_infra_ops",
        compensation_base_min=150000,
        url=f"https://example.invalid/{job_id}",
        description="",
        tags=[],
        source="test",
        source_id=job_id,
    )


def previous_record(job_id: str, title: str, score: int):
    from labor_sieve.history import HistoryRecord

    return HistoryRecord(
        key=f"https://example.invalid/{job_id}",
        title=title,
        company="Example Co",
        url=f"https://example.invalid/{job_id}",
        source="test",
        source_id=job_id,
        score=score,
        priority="P2",
        seen_at="2026-06-14T00:00:00+00:00",
    )
