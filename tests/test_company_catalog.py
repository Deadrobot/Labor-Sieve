from pathlib import Path

import pytest

from labor_sieve.company_catalog import (
    add_catalog_entries_to_config_data,
    catalog_from_data,
    filter_company_catalog,
    format_company_entry,
    load_company_catalog,
)
from labor_sieve.config import ConfigError


def test_packaged_catalog_loads_and_filters_by_source():
    entries = load_company_catalog()

    greenhouse = filter_company_catalog(entries, source="greenhouse")

    assert {entry.key for entry in greenhouse} >= {"cloudflare", "coreweave", "samsara"}
    assert all("greenhouse" in entry.sources for entry in greenhouse)


def test_catalog_filters_by_tag_and_search():
    entries = catalog_from_data(
        {
            "companies": {
                "example": {
                    "name": "Example Cloud",
                    "tags": ["Data_Center", "GPU"],
                    "sources": {"greenhouse": {"board_token": "example"}},
                },
                "other": {
                    "name": "Other Systems",
                    "tags": ["networking"],
                    "sources": {"lever": {"company": "other"}},
                },
            }
        }
    )

    assert [entry.key for entry in filter_company_catalog(entries, tag="data_center")] == ["example"]
    assert [entry.key for entry in filter_company_catalog(entries, search="systems")] == ["other"]
    assert [entry.key for entry in filter_company_catalog(entries, source="lever")] == ["other"]
    assert [entry.key for entry in filter_company_catalog(entries, stale_days=1)] == ["example", "other"]


def test_format_company_entry_includes_tags_and_source_values():
    entry = catalog_from_data(
        {
            "companies": {
                "coreweave": {
                    "name": "CoreWeave",
                    "tags": ["data_center"],
                    "sources": {"greenhouse": {"board_token": "coreweave"}},
                }
            }
        }
    )[0]

    text = format_company_entry(entry)

    assert "coreweave - CoreWeave [data_center]" in text
    assert "verified:" in text
    assert "greenhouse: board_token=coreweave" in text


def test_add_catalog_entries_to_config_data_enables_sources_without_duplicates():
    entries = catalog_from_data(
        {
            "companies": {
                "coreweave": {
                    "name": "CoreWeave",
                    "tags": ["data_center"],
                    "sources": {"greenhouse": {"board_token": "coreweave"}},
                },
                "nvidia": {
                    "name": "NVIDIA",
                    "tags": ["hardware"],
                    "sources": {
                        "workday": {
                            "url": "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
                        }
                    },
                },
            }
        }
    )
    data = {
        "sources": {
            "greenhouse": {"enabled": False, "board_tokens": ["coreweave"]},
            "workday": {"enabled": False, "sites": []},
        }
    }

    changed = add_catalog_entries_to_config_data(data, entries)

    assert changed == ["nvidia: workday url=https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"]
    assert data["sources"]["greenhouse"]["enabled"] is True
    assert data["sources"]["greenhouse"]["board_tokens"] == ["coreweave"]
    assert data["sources"]["workday"]["enabled"] is True
    assert data["sources"]["workday"]["sites"][0]["company"] == "NVIDIA"


def test_catalog_validation_reports_bad_source_shape(tmp_path):
    path = Path(tmp_path) / "companies.yaml"
    path.write_text(
        """
companies:
  bad:
    name: Bad
    sources:
      greenhouse:
        token: missing-board-token
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError) as exc:
        load_company_catalog(path)

    assert "companies.bad.sources.greenhouse.board_token must be a non-empty string." in exc.value.errors
    assert "companies.bad.sources.greenhouse.token is not supported." in exc.value.errors
