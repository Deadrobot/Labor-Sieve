#!/usr/bin/env python3
"""Build a remote preset index for labor-sieve update-presets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


DEFAULT_PRESET_DIR = Path("presets")
DEFAULT_OUTPUT = DEFAULT_PRESET_DIR / "index.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate presets/index.json.")
    parser.add_argument("--preset-dir", default=str(DEFAULT_PRESET_DIR), help="Directory containing preset YAML files.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Index JSON path to write.")
    parser.add_argument(
        "--base-url",
        required=True,
        help="Public HTTPS base URL where preset YAML files are hosted.",
    )
    args = parser.parse_args()

    preset_dir = Path(args.preset_dir)
    output = Path(args.output)
    base_url = str(args.base_url).rstrip("/")
    if not base_url.startswith("https://"):
        raise SystemExit("--base-url must start with https://")

    entries = []
    for path in sorted(preset_dir.glob("*.yaml")):
        content = path.read_bytes()
        metadata = read_top_level_metadata(content.decode("utf-8"), path.stem)
        entry = {
            "name": metadata["name"],
            "url": f"{base_url}/{path.name}",
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        if metadata.get("version"):
            entry["version"] = metadata["version"]
        if metadata.get("description"):
            entry["description"] = metadata["description"]
        entries.append(entry)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"presets": entries}, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output} with {len(entries)} presets.")
    return 0


def read_top_level_metadata(text: str, fallback_name: str) -> dict[str, str]:
    metadata = {"name": fallback_name, "description": "", "version": ""}
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.startswith("#"):
            continue
        if raw_line.startswith((" ", "\t")):
            continue
        key, separator, value = raw_line.partition(":")
        if separator and key in metadata:
            metadata[key] = value.strip().strip("'\"")
    return metadata


if __name__ == "__main__":
    raise SystemExit(main())
