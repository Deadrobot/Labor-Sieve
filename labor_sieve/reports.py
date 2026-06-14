"""Report rendering and writing."""

from __future__ import annotations

import csv
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .config import Config
from .models import ScoredJob
from .taxonomy import PRIORITY_BUCKETS


CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

HTML_REPORT_STYLE = """
      body { font-family: system-ui, sans-serif; line-height: 1.45; margin: 2rem; color: #17202a; }
      header, main { max-width: 1040px; margin: 0 auto 2rem; }
      header { border-bottom: 1px solid #d8dee4; padding-bottom: 1rem; }
      h1, h2, h3 { line-height: 1.2; }
      a { color: #0969da; }
      button { border: 1px solid #b6c2cf; border-radius: 5px; background: #fff; color: #17202a; cursor: pointer; font: inherit; padding: 0.35rem 0.55rem; }
      button:hover { border-color: #0969da; }
      button[aria-pressed="true"] { background: #0969da; border-color: #0969da; color: #fff; }
      .report-controls { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 1rem; }
      .tracking-note { color: #57606a; margin-bottom: 0; }
      .bucket { border-bottom: 1px solid #d8dee4; margin-bottom: 1rem; padding-bottom: 1rem; }
      .bucket-summary { cursor: pointer; font-size: 1.25rem; font-weight: 700; padding: 0.75rem 0; }
      .job-card { border: 1px solid #d8dee4; border-radius: 6px; margin: 0.75rem 0; padding: 0.75rem; }
      .job-card[open] { background: #f8fafc; }
      .job-summary { align-items: center; cursor: pointer; display: flex; gap: 0.75rem; justify-content: space-between; }
      .job-title-line { align-items: center; display: inline-flex; gap: 0.5rem; min-width: 0; }
      .score-pill, .state-badge { border-radius: 999px; display: inline-block; font-size: 0.85rem; font-weight: 700; line-height: 1; padding: 0.25rem 0.45rem; white-space: nowrap; }
      .score-pill { background: #17202a; color: #fff; }
      .state-badges { display: inline-flex; flex-wrap: wrap; gap: 0.35rem; justify-content: flex-end; }
      .state-badge { background: #dbeafe; color: #0f376f; }
      .state-badge.history { background: #dcfce7; color: #14532d; }
      .state-badge.rejected, .state-badge.hidden { background: #fee2e2; color: #8a1f1f; }
      .state-badge[hidden] { display: none; }
      .job-body { padding-top: 0.75rem; }
      .tracking-controls { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0.75rem 0; }
      .is-rejected { opacity: 0.72; }
      @media (max-width: 720px) {
        body { margin: 1rem; }
        .job-summary { align-items: flex-start; flex-direction: column; }
        .state-badges { justify-content: flex-start; }
      }
"""

HTML_REPORT_SCRIPT = """
    <script>
      (function () {
        const storageKey = "labor-sieve-report-state-v1";
        let state = {};
        let showHidden = false;

        function loadState() {
          try {
            state = JSON.parse(window.localStorage.getItem(storageKey) || "{}") || {};
          } catch (_) {
            state = {};
          }
        }

        function saveState() {
          try {
            window.localStorage.setItem(storageKey, JSON.stringify(state));
          } catch (_) {
          }
        }

        function stateFor(key) {
          if (!state[key]) {
            state[key] = {};
          }
          return state[key];
        }

        function setPressed(article, action, value) {
          const button = article.querySelector('[data-action="' + action + '"]');
          if (button) {
            button.setAttribute("aria-pressed", value ? "true" : "false");
          }
        }

        function setBadge(article, name, value) {
          const badge = article.querySelector('[data-state-badge="' + name + '"]');
          if (badge) {
            badge.hidden = !value;
          }
        }

        function updateArticle(article) {
          const current = state[article.dataset.jobKey] || {};
          const hidden = Boolean(current.hidden);
          const rejected = Boolean(current.rejected);
          article.hidden = (hidden || rejected) && !showHidden;
          article.classList.toggle("is-rejected", rejected);
          setPressed(article, "interested", Boolean(current.interested));
          setPressed(article, "applied", Boolean(current.applied));
          setPressed(article, "rejected", rejected);
          setPressed(article, "hidden", hidden);
          setBadge(article, "interested", Boolean(current.interested));
          setBadge(article, "applied", Boolean(current.applied));
          setBadge(article, "rejected", rejected);
          setBadge(article, "hidden", hidden);
        }

        function updateControls() {
          const toggleHidden = document.querySelector('[data-action="toggle-hidden"]');
          if (toggleHidden) {
            toggleHidden.setAttribute("aria-pressed", showHidden ? "true" : "false");
            toggleHidden.textContent = showHidden ? "Hide rejected/hidden" : "Show rejected/hidden";
          }
        }

        function updateAll() {
          document.querySelectorAll("[data-job-key]").forEach(updateArticle);
          updateControls();
        }

        document.addEventListener("click", function (event) {
          const button = event.target.closest("button[data-action]");
          if (!button) {
            return;
          }
          const action = button.dataset.action;
          if (action === "toggle-hidden") {
            showHidden = !showHidden;
            updateAll();
            return;
          }
          if (action === "clear-report-state") {
            if (window.confirm("Clear tracking for this browser?")) {
              state = {};
              saveState();
              updateAll();
            }
            return;
          }

          const article = button.closest("[data-job-key]");
          if (!article) {
            return;
          }
          const key = article.dataset.jobKey;
          if (action === "clear") {
            delete state[key];
          } else {
            const current = stateFor(key);
            current[action] = !current[action];
          }
          saveState();
          updateAll();
        });

        loadState();
        updateAll();
      })();
    </script>
"""


def write_reports(
    scored_jobs: list[ScoredJob],
    config: Config,
    *,
    base_dir: Path | None = None,
    history: object | None = None,
) -> dict[str, Path]:
    output_dir = Path(config.output.directory).expanduser()
    if base_dir is not None and not output_dir.is_absolute():
        output_dir = base_dir / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}
    if config.output.txt:
        path = output_dir / "latest.txt"
        path.write_text(render_text_report(scored_jobs, history=history), encoding="utf-8")
        written["txt"] = path
    if config.output.csv:
        path = output_dir / "latest.csv"
        write_csv_report(scored_jobs, path)
        written["csv"] = path
    if config.output.json:
        path = output_dir / "latest.json"
        path.write_text(render_json_report(scored_jobs, history=history), encoding="utf-8")
        written["json"] = path
    if config.output.html:
        path = output_dir / "latest.html"
        path.write_text(render_html_report(scored_jobs, history=history), encoding="utf-8")
        written["html"] = path
    return written


def render_terminal_summary(
    scored_jobs: list[ScoredJob],
    written: dict[str, Path],
    duplicate_count: int = 0,
    excluded_count: int = 0,
    config: Config | None = None,
    history: object | None = None,
) -> str:
    counts = bucket_counts(scored_jobs)
    lines = [
        f"Scanned {len(scored_jobs)} jobs.",
        f"Deduplicated {duplicate_count} duplicate jobs.",
        f"Excluded {excluded_count} jobs by config.",
        "Buckets: " + " | ".join(f"{bucket} {counts[bucket]}" for bucket in PRIORITY_BUCKETS),
        "",
    ]
    if history is not None:
        lines.extend(
            [
                (
                    "History: "
                    f"{getattr(history, 'new_count', 0)} new | "
                    f"{getattr(history, 'seen_count', 0)} seen | "
                    f"{_history_disappeared_count(history)} disappeared"
                ),
                "",
            ]
        )

    terminal_p0_limit = config.output.terminal_p0_limit if config is not None else 10
    terminal_p1_limit = config.output.terminal_p1_limit if config is not None else 15
    top_matches = limited_terminal_matches(
        scored_jobs,
        terminal_p0_limit=terminal_p0_limit,
        terminal_p1_limit=terminal_p1_limit,
    )
    if top_matches:
        lines.append("P0/P1 matches:")
        for item in top_matches:
            job = item.job
            comp = format_compensation(job.compensation_base_min)
            location = terminal_location(job.location, job.remote)
            lines.extend(
                [
                    f"{item.priority} {item.score}: {job.title} at {job.company}",
                    f"  {location} | {job.seniority} | {job.role_family} | {comp} | {job.source}",
                    f"  {terminal_history_text(item)}",
                    f"  Why: {terminal_reason_text(item)}",
                    f"  {job.url}",
                ]
            )
        hidden_count = hidden_terminal_match_count(
            scored_jobs,
            terminal_p0_limit=terminal_p0_limit,
            terminal_p1_limit=terminal_p1_limit,
        )
        if hidden_count:
            lines.append(f"... {hidden_count} additional P0/P1 matches are in the full reports.")
    else:
        lines.append("No P0/P1 matches.")

    if written:
        lines.extend(["", "Reports written:"])
        for report_type, path in written.items():
            lines.append(f"  {report_type}: {path}")
    return "\n".join(lines)


def limited_terminal_matches(
    scored_jobs: list[ScoredJob],
    *,
    terminal_p0_limit: int,
    terminal_p1_limit: int,
) -> list[ScoredJob]:
    matches = []
    p0_count = 0
    p1_count = 0
    for item in scored_jobs:
        if item.priority == "P0" and p0_count < terminal_p0_limit:
            matches.append(item)
            p0_count += 1
        elif item.priority == "P1" and p1_count < terminal_p1_limit:
            matches.append(item)
            p1_count += 1
    return matches


def hidden_terminal_match_count(
    scored_jobs: list[ScoredJob],
    *,
    terminal_p0_limit: int,
    terminal_p1_limit: int,
) -> int:
    p0_total = sum(1 for item in scored_jobs if item.priority == "P0")
    p1_total = sum(1 for item in scored_jobs if item.priority == "P1")
    return max(0, p0_total - terminal_p0_limit) + max(
        0,
        p1_total - terminal_p1_limit,
    )


def terminal_location(location: str, remote: bool) -> str:
    if location and location != "Unknown":
        return location
    return "Remote" if remote else location


def render_text_report(scored_jobs: list[ScoredJob], *, history: object | None = None) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    counts = bucket_counts(scored_jobs)
    lines = [
        "LaborSieve Report",
        f"Generated: {generated}",
        f"Scanned: {len(scored_jobs)} jobs",
        "Buckets: " + " | ".join(f"{bucket} {counts[bucket]}" for bucket in PRIORITY_BUCKETS),
        "",
    ]
    if history is not None:
        lines.extend(
            [
                (
                    "History: "
                    f"{getattr(history, 'new_count', 0)} new | "
                    f"{getattr(history, 'seen_count', 0)} seen | "
                    f"{_history_disappeared_count(history)} disappeared"
                ),
                "",
            ]
        )

    for bucket in PRIORITY_BUCKETS:
        bucket_jobs = [item for item in scored_jobs if item.priority == bucket]
        lines.append(f"## {bucket} ({len(bucket_jobs)})")
        if not bucket_jobs:
            lines.extend(["No jobs in this bucket.", ""])
            continue

        for item in bucket_jobs:
            job = item.job
            lines.extend(
                [
                    f"{job.title}",
                    f"  Company: {job.company}",
                    f"  Score: {item.score}",
                    f"  Priority: {item.priority}",
                    f"  History: {history_text(item)}",
                    f"  Seniority: {job.seniority}",
                    f"  Role family: {job.role_family}",
                    f"  Location: {job.location}",
                    f"  Remote: {yes_no(job.remote)}",
                    f"  Hybrid: {yes_no(job.hybrid)}",
                    f"  Base compensation min: {format_compensation(job.compensation_base_min)}",
                    f"  URL: {job.url}",
                    f"  Source: {job.source}",
                    f"  Source ID: {job.source_id or 'not listed'}",
                    f"  Merged sources: {', '.join(job.merged_sources) if job.merged_sources else 'none'}",
                    f"  Tags: {', '.join(job.tags) if job.tags else 'none'}",
                    "  Score reasons:",
                ]
            )
            for reason in item.reasons:
                lines.append(f"    - {reason}")
            lines.append("")
    disappeared = _history_disappeared(history)
    if disappeared:
        lines.append("## Disappeared since last run")
        for record in disappeared:
            lines.extend(
                [
                    f"{getattr(record, 'title', '')}",
                    f"  Company: {getattr(record, 'company', '')}",
                    f"  Previous score: {getattr(record, 'score', '')}",
                    f"  Previous priority: {getattr(record, 'priority', '')}",
                    f"  Source: {getattr(record, 'source', '')}",
                    f"  URL: {getattr(record, 'url', '') or 'not listed'}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def write_csv_report(scored_jobs: list[ScoredJob], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "priority",
                "score",
                "title",
                "company",
                "location",
                "remote",
                "hybrid",
                "seniority",
                "role_family",
                "compensation_base_min",
                "url",
                "tags",
                "reasons",
                "history_status",
                "previous_score",
                "score_delta",
                "source",
                "source_id",
                "merged_sources",
            ],
        )
        writer.writeheader()
        for item in scored_jobs:
            job = item.job
            writer.writerow(
                {
                    "priority": item.priority,
                    "score": item.score,
                    "title": csv_safe_cell(job.title),
                    "company": csv_safe_cell(job.company),
                    "location": csv_safe_cell(job.location),
                    "remote": job.remote,
                    "hybrid": job.hybrid,
                    "seniority": csv_safe_cell(job.seniority),
                    "role_family": csv_safe_cell(job.role_family),
                    "compensation_base_min": job.compensation_base_min or "",
                    "url": csv_safe_cell(job.url),
                    "tags": csv_safe_cell("; ".join(job.tags)),
                    "reasons": csv_safe_cell("; ".join(item.reasons)),
                    "history_status": csv_safe_cell(item.history_status),
                    "previous_score": "" if item.previous_score is None else item.previous_score,
                    "score_delta": "" if item.score_delta is None else item.score_delta,
                    "source": csv_safe_cell(job.source),
                    "source_id": csv_safe_cell(job.source_id),
                    "merged_sources": csv_safe_cell("; ".join(job.merged_sources)),
                }
            )


def csv_safe_cell(value: str) -> str:
    if not value:
        return value
    if value.startswith(CSV_FORMULA_PREFIXES):
        return "'" + value
    stripped = value.lstrip()
    if stripped != value and stripped.startswith(CSV_FORMULA_PREFIXES[:4]):
        return "'" + value
    return value


def render_json_report(scored_jobs: list[ScoredJob], *, history: object | None = None) -> str:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(scored_jobs),
        "buckets": bucket_counts(scored_jobs),
        "jobs": [scored_job_to_dict(item) for item in scored_jobs],
    }
    if history is not None:
        payload["history"] = {
            "previous_count": getattr(history, "previous_count", 0),
            "new_count": getattr(history, "new_count", 0),
            "seen_count": getattr(history, "seen_count", 0),
            "disappeared_count": _history_disappeared_count(history),
            "disappeared": [_history_record_to_dict(record) for record in _history_disappeared(history)],
        }
    return json.dumps(payload, indent=2) + "\n"


def render_html_report(scored_jobs: list[ScoredJob], *, history: object | None = None) -> str:
    counts = bucket_counts(scored_jobs)
    sections = []
    for bucket in PRIORITY_BUCKETS:
        cards = []
        for item in [job for job in scored_jobs if job.priority == bucket]:
            job = item.job
            job_key = html.escape(report_job_key(item), quote=True)
            reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in item.reasons)
            tags = html.escape(", ".join(job.tags) if job.tags else "none")
            history_label = html.escape(history_text(item))
            history_badge = html.escape(item.history_status.title()) if item.history_status else ""
            history_badge_html = (
                f'<span class="state-badge history">{history_badge}</span>' if history_badge else ""
            )
            cards.append(
                f"""
          <details class="job-card" data-job-key="{job_key}">
            <summary class="job-summary">
              <span class="job-title-line">
                <span class="score-pill">{html.escape(item.priority)} {item.score}</span>
                <span>{html.escape(job.title)}</span>
              </span>
              <span class="state-badges" aria-label="Tracking state">
                {history_badge_html}
                <span class="state-badge" data-state-badge="interested" hidden>Interested</span>
                <span class="state-badge" data-state-badge="applied" hidden>Applied</span>
                <span class="state-badge rejected" data-state-badge="rejected" hidden>Rejected</span>
                <span class="state-badge hidden" data-state-badge="hidden" hidden>Hidden</span>
              </span>
            </summary>
            <div class="job-body">
              <p><strong>{html.escape(job.company)}</strong> | {html.escape(job.location)} | {html.escape(job.seniority)} | {html.escape(job.role_family)}</p>
              <p>History: {history_label}</p>
              <p>Base compensation min: {html.escape(format_compensation(job.compensation_base_min))}</p>
              <p>Source: {html.escape(job.source)} | Merged sources: {html.escape(', '.join(job.merged_sources) if job.merged_sources else 'none')}</p>
              <p>{render_job_url(job.url)}</p>
              <div class="tracking-controls" aria-label="Tracking controls">
                <button type="button" data-action="interested" aria-pressed="false">Interested</button>
                <button type="button" data-action="applied" aria-pressed="false">Applied</button>
                <button type="button" data-action="rejected" aria-pressed="false">Reject</button>
                <button type="button" data-action="hidden" aria-pressed="false">Hide</button>
                <button type="button" data-action="clear">Clear</button>
              </div>
              <p>Tags: {tags}</p>
              <ul>{reasons}</ul>
            </div>
          </details>"""
            )
        if not cards:
            cards.append("<p>No jobs in this bucket.</p>")
        open_attr = " open" if bucket in {"P0", "P1"} else ""
        sections.append(
            f"""
      <details class="bucket"{open_attr}>
        <summary class="bucket-summary">{html.escape(bucket)} ({counts[bucket]})</summary>
        {''.join(cards)}
      </details>"""
        )

    disappeared_section = ""
    disappeared = _history_disappeared(history)
    if disappeared:
        items = "".join(
            "<li>"
            + html.escape(
                f"{getattr(record, 'title', '')} at {getattr(record, 'company', '')} "
                f"({getattr(record, 'priority', '')} {getattr(record, 'score', '')})"
            )
            + "</li>"
            for record in disappeared
        )
        disappeared_section = f"""
      <section class="bucket">
        <h2>Disappeared since last run ({len(disappeared)})</h2>
        <ul>{items}</ul>
      </section>"""

    history_summary = ""
    if history is not None:
        history_summary = (
            f" History: {getattr(history, 'new_count', 0)} new | "
            f"{getattr(history, 'seen_count', 0)} seen | "
            f"{_history_disappeared_count(history)} disappeared."
        )

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>LaborSieve Report</title>
    <style>
{HTML_REPORT_STYLE}
    </style>
  </head>
  <body>
    <header>
      <h1>LaborSieve Report</h1>
      <p>Scanned {len(scored_jobs)} jobs. {' | '.join(f'{bucket} {counts[bucket]}' for bucket in PRIORITY_BUCKETS)}.{html.escape(history_summary)}</p>
      <p class="tracking-note">Tracking buttons are stored in this browser.</p>
      <div class="report-controls">
        <button type="button" data-action="toggle-hidden" aria-pressed="false">Show rejected/hidden</button>
        <button type="button" data-action="clear-report-state">Clear tracking</button>
      </div>
    </header>
    <main>
      {''.join(sections)}
      {disappeared_section}
    </main>
{HTML_REPORT_SCRIPT}
  </body>
</html>
"""


def scored_job_to_dict(item: ScoredJob) -> dict[str, object]:
    job = item.job
    return {
        "id": job.id,
        "priority": item.priority,
        "score": item.score,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote": job.remote,
        "hybrid": job.hybrid,
        "seniority": job.seniority,
        "role_family": job.role_family,
        "compensation_base_min": job.compensation_base_min,
        "url": job.url,
        "tags": job.tags,
        "source": job.source,
        "source_id": job.source_id,
        "merged_sources": job.merged_sources,
        "reasons": item.reasons,
        "history_status": item.history_status,
        "previous_score": item.previous_score,
        "score_delta": item.score_delta,
    }


def report_job_key(item: ScoredJob) -> str:
    job = item.job
    if job.url.strip():
        return job.url.strip()
    return f"{job.source}:{job.source_id or job.id}"


def bucket_counts(scored_jobs: list[ScoredJob]) -> dict[str, int]:
    counts = Counter(item.priority for item in scored_jobs)
    return {bucket: counts.get(bucket, 0) for bucket in PRIORITY_BUCKETS}


def history_text(item: ScoredJob) -> str:
    if not item.history_status:
        return "not tracked"
    if item.history_status == "new":
        return "new since last run"
    if item.score_delta is None or item.previous_score is None:
        return item.history_status
    if item.score_delta == 0:
        return f"seen before; score unchanged from {item.previous_score}"
    sign = "+" if item.score_delta > 0 else ""
    return f"seen before; score {sign}{item.score_delta} from {item.previous_score}"


def terminal_history_text(item: ScoredJob) -> str:
    return "History: " + history_text(item)


def terminal_reason_text(item: ScoredJob) -> str:
    if not item.reasons:
        return "no score reasons listed"
    return "; ".join(item.reasons[:3])


def _history_disappeared(history: object | None) -> list[object]:
    if history is None:
        return []
    disappeared = getattr(history, "disappeared", None)
    if isinstance(disappeared, list):
        return disappeared
    return []


def _history_disappeared_count(history: object | None) -> int:
    return len(_history_disappeared(history))


def _history_record_to_dict(record: object) -> dict[str, object]:
    return {
        "key": getattr(record, "key", ""),
        "title": getattr(record, "title", ""),
        "company": getattr(record, "company", ""),
        "url": getattr(record, "url", ""),
        "source": getattr(record, "source", ""),
        "source_id": getattr(record, "source_id", ""),
        "score": getattr(record, "score", 0),
        "priority": getattr(record, "priority", ""),
        "seen_at": getattr(record, "seen_at", ""),
    }


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def format_compensation(value: int | None) -> str:
    if value is None:
        return "not listed"
    return f"${value:,}"


def render_job_url(url: str) -> str:
    cleaned = url.strip()
    display = html.escape(cleaned or "not listed")
    if not is_safe_report_url(cleaned):
        return display
    return f'<a href="{html.escape(cleaned, quote=True)}">{display}</a>'


def is_safe_report_url(url: str) -> bool:
    split = urlsplit(url)
    return split.scheme in {"http", "https"} and bool(split.netloc)
