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


def write_reports(scored_jobs: list[ScoredJob], config: Config) -> dict[str, Path]:
    output_dir = Path(config.output.directory)
    output_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}
    if config.output.txt:
        path = output_dir / "latest.txt"
        path.write_text(render_text_report(scored_jobs), encoding="utf-8")
        written["txt"] = path
    if config.output.csv:
        path = output_dir / "latest.csv"
        write_csv_report(scored_jobs, path)
        written["csv"] = path
    if config.output.json:
        path = output_dir / "latest.json"
        path.write_text(render_json_report(scored_jobs), encoding="utf-8")
        written["json"] = path
    if config.output.html:
        path = output_dir / "latest.html"
        path.write_text(render_html_report(scored_jobs), encoding="utf-8")
        written["html"] = path
    return written


def render_terminal_summary(
    scored_jobs: list[ScoredJob],
    written: dict[str, Path],
    duplicate_count: int = 0,
) -> str:
    counts = bucket_counts(scored_jobs)
    lines = [
        f"Scanned {len(scored_jobs)} jobs.",
        f"Deduplicated {duplicate_count} duplicate jobs.",
        "Buckets: " + " | ".join(f"{bucket} {counts[bucket]}" for bucket in PRIORITY_BUCKETS),
        "",
    ]

    top_matches = [item for item in scored_jobs if item.priority in {"P0", "P1"}]
    if top_matches:
        lines.append("P0/P1 matches:")
        for item in top_matches:
            job = item.job
            comp = format_compensation(job.compensation_base_min)
            location = "Remote" if job.remote else job.location
            lines.extend(
                [
                    f"{item.priority} {item.score}: {job.title} at {job.company}",
                    f"  {location} | {job.seniority} | {job.role_family} | {comp} | {job.source}",
                    f"  {job.url}",
                ]
            )
    else:
        lines.append("No P0/P1 matches.")

    if written:
        lines.extend(["", "Reports written:"])
        for report_type, path in written.items():
            lines.append(f"  {report_type}: {path}")
    return "\n".join(lines)


def render_text_report(scored_jobs: list[ScoredJob]) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    counts = bucket_counts(scored_jobs)
    lines = [
        "LaborSieve Report",
        f"Generated: {generated}",
        f"Scanned: {len(scored_jobs)} jobs",
        "Buckets: " + " | ".join(f"{bucket} {counts[bucket]}" for bucket in PRIORITY_BUCKETS),
        "",
    ]

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
            lines.extend(["  Description:", indent_block(job.description, 4), ""])
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
                "description",
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
                    "description": csv_safe_cell(job.description),
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


def render_json_report(scored_jobs: list[ScoredJob]) -> str:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(scored_jobs),
        "buckets": bucket_counts(scored_jobs),
        "jobs": [scored_job_to_dict(item) for item in scored_jobs],
    }
    return json.dumps(payload, indent=2) + "\n"


def render_html_report(scored_jobs: list[ScoredJob]) -> str:
    counts = bucket_counts(scored_jobs)
    sections = []
    for bucket in PRIORITY_BUCKETS:
        cards = []
        for item in [job for job in scored_jobs if job.priority == bucket]:
            job = item.job
            reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in item.reasons)
            tags = html.escape(", ".join(job.tags) if job.tags else "none")
            cards.append(
                f"""
        <article>
          <h3>{html.escape(job.title)}</h3>
          <p><strong>{html.escape(job.company)}</strong> | {html.escape(job.location)} | {html.escape(job.seniority)} | {html.escape(job.role_family)}</p>
          <p>Score: {item.score} | Base compensation min: {html.escape(format_compensation(job.compensation_base_min))}</p>
          <p>Source: {html.escape(job.source)} | Merged sources: {html.escape(', '.join(job.merged_sources) if job.merged_sources else 'none')}</p>
          <p>{render_job_url(job.url)}</p>
          <p>Tags: {tags}</p>
          <ul>{reasons}</ul>
          <p>{html.escape(job.description)}</p>
        </article>"""
            )
        if not cards:
            cards.append("<p>No jobs in this bucket.</p>")
        sections.append(
            f"""
      <section>
        <h2>{html.escape(bucket)} ({counts[bucket]})</h2>
        {''.join(cards)}
      </section>"""
        )

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>LaborSieve Report</title>
    <style>
      body {{ font-family: system-ui, sans-serif; line-height: 1.45; margin: 2rem; color: #17202a; }}
      header, section {{ max-width: 960px; margin: 0 auto 2rem; }}
      article {{ border: 1px solid #d8dee4; border-radius: 6px; padding: 1rem; margin: 1rem 0; }}
      h1, h2, h3 {{ line-height: 1.2; }}
      a {{ color: #0969da; }}
    </style>
  </head>
  <body>
    <header>
      <h1>LaborSieve Report</h1>
      <p>Scanned {len(scored_jobs)} jobs. {' | '.join(f'{bucket} {counts[bucket]}' for bucket in PRIORITY_BUCKETS)}</p>
    </header>
    {''.join(sections)}
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
        "description": job.description,
        "tags": job.tags,
        "source": job.source,
        "source_id": job.source_id,
        "merged_sources": job.merged_sources,
        "reasons": item.reasons,
    }


def bucket_counts(scored_jobs: list[ScoredJob]) -> dict[str, int]:
    counts = Counter(item.priority for item in scored_jobs)
    return {bucket: counts.get(bucket, 0) for bucket in PRIORITY_BUCKETS}


def indent_block(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line else prefix for line in text.splitlines())


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
