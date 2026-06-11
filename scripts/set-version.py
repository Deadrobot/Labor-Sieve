#!/usr/bin/env python3
"""Set the LaborSieve package version and promote changelog entries."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = ROOT / "labor_sieve" / "__init__.py"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[a-zA-Z0-9.+-]*)?$")
INIT_VERSION_RE = re.compile(r'^__version__ = "([^"]+)"$', re.MULTILINE)
CHANGELOG_HEADING_RE = re.compile(r"^## .+$", re.MULTILINE)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a LaborSieve release version.")
    parser.add_argument("version", help="Version to set, for example 0.1.2")
    args = parser.parse_args()

    version = args.version.strip()
    if not VERSION_RE.fullmatch(version):
        raise SystemExit(f"Invalid version {version!r}. Expected a version like 0.1.2.")

    old_version = update_init(version)
    promoted = update_changelog(version)

    print(f"Updated {INIT_PATH.relative_to(ROOT)}: {old_version} -> {version}")
    if promoted:
        print(f"Moved Unreleased changelog entries under {version}.")
    else:
        print(f"Added changelog section for {version}.")
    return 0


def update_init(version: str) -> str:
    text = INIT_PATH.read_text(encoding="utf-8")
    match = INIT_VERSION_RE.search(text)
    if not match:
        raise SystemExit(f"{INIT_PATH} does not contain a __version__ assignment.")
    old_version = match.group(1)
    updated = INIT_VERSION_RE.sub(f'__version__ = "{version}"', text, count=1)
    INIT_PATH.write_text(updated, encoding="utf-8")
    return old_version


def update_changelog(version: str) -> bool:
    text = CHANGELOG_PATH.read_text(encoding="utf-8")
    if f"## {version}" in text:
        raise SystemExit(f"{CHANGELOG_PATH} already contains a {version} section.")

    unreleased = "## Unreleased"
    start = text.find(unreleased)
    if start == -1:
        raise SystemExit(f"{CHANGELOG_PATH} does not contain an Unreleased section.")

    body_start = start + len(unreleased)
    next_heading = CHANGELOG_HEADING_RE.search(text, body_start)
    if next_heading is None:
        before = text[:body_start]
        body = text[body_start:]
        after = ""
    else:
        before = text[:body_start]
        body = text[body_start : next_heading.start()]
        after = text[next_heading.start() :]

    entries = body.strip()
    if entries:
        replacement = f"\n\n## {version}\n\n{entries}\n\n"
        promoted = True
    else:
        replacement = f"\n\n## {version}\n\n"
        promoted = False

    CHANGELOG_PATH.write_text(before + replacement + after.lstrip("\n"), encoding="utf-8")
    return promoted


if __name__ == "__main__":
    raise SystemExit(main())
