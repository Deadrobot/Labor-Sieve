import hashlib
import json
from pathlib import Path

import pytest
import yaml

from labor_sieve.config import read_yaml_file
from labor_sieve.presets import (
    PresetError,
    _download_bytes,
    apply_preset_to_config,
    deep_merge,
    list_presets,
    update_presets,
)


ROOT = Path(__file__).resolve().parents[1]


def test_list_presets_includes_bundled_presets(tmp_path):
    presets = list_presets(tmp_path / "downloaded")
    names = {preset.name for preset in presets}

    assert "linux-sre" in names
    assert "operations-engineer" in names


def test_deep_merge_preserves_unmentioned_config_keys():
    merged = deep_merge(
        {
            "role_family_weights": {"unknown": 0.05, "sre_infra_ops": 1.0},
            "keywords": {"boost": ["linux"], "penalize": ["frontend"]},
        },
        {
            "role_family_weights": {"custom_family": 0.8},
            "keywords": {"boost": ["implementation"]},
        },
    )

    assert merged["role_family_weights"]["unknown"] == 0.05
    assert merged["role_family_weights"]["custom_family"] == 0.8
    assert merged["keywords"]["boost"] == ["implementation"]
    assert merged["keywords"]["penalize"] == ["frontend"]


def test_apply_preset_to_config_writes_backup_and_valid_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text((ROOT / "config.example.yaml").read_text(encoding="utf-8"), encoding="utf-8")

    written_path, backup_path = apply_preset_to_config(
        "senior-infra-lead",
        config_path,
        preset_dir=tmp_path / "downloaded",
    )

    assert written_path == config_path
    assert backup_path.exists()
    data = read_yaml_file(config_path)
    assert data["seniority"]["min"] == "senior"
    assert data["seniority"]["allow_principal"] is True
    assert data["role_family_weights"]["unknown"] == 0.05


def test_update_presets_downloads_verified_file_index(tmp_path):
    remote_preset = tmp_path / "remote-field-enable.yaml"
    remote_preset.write_text(
        yaml.safe_dump(
            {
                "name": "field-enable",
                "description": "Field enablement test preset",
                "role_family_weights": {"field_enablement": 0.82},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(remote_preset.read_bytes()).hexdigest()
    index = tmp_path / "index.json"
    index.write_text(
        json.dumps(
            {
                "presets": [
                    {
                        "name": "field-enable",
                        "url": remote_preset.as_uri(),
                        "sha256": digest,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    destination = tmp_path / "downloaded"

    results = update_presets(index.as_uri(), preset_dir=destination)

    assert len(results) == 1
    assert results[0].name == "field-enable"
    assert results[0].verified is True
    assert results[0].skipped is False
    assert (destination / "field-enable.yaml").exists()
    assert (destination / "index.json").exists()


def test_preset_download_rejects_oversized_file_uri(tmp_path, monkeypatch):
    path = tmp_path / "large.yaml"
    path.write_text("name: large\n", encoding="utf-8")
    monkeypatch.setattr("labor_sieve.presets.MAX_PRESET_BYTES", 5)

    with pytest.raises(PresetError, match="larger than the 5 byte limit"):
        _download_bytes(path.as_uri(), timeout_seconds=20)


def test_preset_download_rejects_http_url():
    with pytest.raises(PresetError, match="Unsupported URL scheme 'http'"):
        _download_bytes("http://example.invalid/preset.yaml", timeout_seconds=20)


def test_update_presets_skips_http_preset_entry(tmp_path):
    index = tmp_path / "index.json"
    index.write_text(
        json.dumps(
            {
                "presets": [
                    {
                        "name": "field-enable",
                        "url": "http://example.invalid/field-enable.yaml",
                        "sha256": "0" * 64,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    results = update_presets(index.as_uri(), preset_dir=tmp_path / "downloaded")

    assert len(results) == 1
    assert results[0].skipped is True
    assert "Unsupported URL scheme 'http'" in results[0].message
