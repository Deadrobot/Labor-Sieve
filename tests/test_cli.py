from pathlib import Path

import pytest

from labor_sieve import __version__
from labor_sieve.cli import main


ROOT = Path(__file__).resolve().parents[1]


def test_version_flag_prints_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])

    assert exc.value.code == 0
    assert f"labor-sieve {__version__}" in capsys.readouterr().out


def test_quickstart_prints_first_run_steps(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))

    assert main(["quickstart"]) == 0

    output = capsys.readouterr().out
    expected_config = tmp_path / "labor-sieve" / "config.yaml"
    expected_report = tmp_path / "labor-sieve" / "output" / "latest.txt"
    assert expected_config.exists()
    assert "Next steps:" in output
    assert "Created" in output
    assert f"Config file: {expected_config}" in output
    assert "labor-sieve init -c" not in output
    assert f"labor-sieve validate-config -c {expected_config}" in output
    assert str(expected_report) in output


def test_quickstart_accepts_explicit_config_path(tmp_path, capsys):
    config_path = tmp_path / "custom" / "config.yaml"

    assert main(["quickstart", "-c", str(config_path)]) == 0

    output = capsys.readouterr().out
    assert config_path.exists()
    assert f"Config file: {config_path}" in output
    assert "Create the config file" not in output
    assert str(config_path.parent / "output" / "latest.txt") in output


def test_quickstart_skips_create_steps_when_config_exists(tmp_path, capsys):
    config_path = tmp_path / "labor-sieve" / "config.yaml"
    config_path.parent.mkdir()
    config_path.write_text("sources:\n  sample:\n    enabled: true\n", encoding="utf-8")

    assert main(["quickstart", "-c", str(config_path)]) == 0

    output = capsys.readouterr().out
    assert f"Config file: {config_path}" in output
    assert "Create the config file" not in output
    assert "labor-sieve init -c" not in output
    assert "now contains the default commented settings" not in output
    assert "Next steps:" in output


def test_doctor_passes_with_valid_config(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    config_path.write_text((ROOT / "config.example.yaml").read_text(encoding="utf-8"), encoding="utf-8")

    assert main(["doctor", "-c", str(config_path)]) == 0

    output = capsys.readouterr().out
    assert "LaborSieve" in output
    assert "[ok] Config file:" in output


def test_doctor_fails_when_config_is_missing(tmp_path, capsys):
    missing = tmp_path / "missing.yaml"

    assert main(["doctor", "-c", str(missing)]) == 1

    output = capsys.readouterr().out
    assert "[fail] Config file:" in output
    assert "labor-sieve init" in output


def test_run_writes_relative_output_next_to_config(tmp_path, monkeypatch):
    config_path = tmp_path / "project" / "config.yaml"
    config_path.parent.mkdir()
    config_path.write_text((ROOT / "config.example.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    assert main(["run", "-c", str(config_path)]) == 0

    assert (config_path.parent / "output" / "latest.txt").exists()
    assert not (other_dir / "output" / "latest.txt").exists()


def test_run_uses_home_config_when_no_local_config_exists(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    assert main(["quickstart"]) == 0
    capsys.readouterr()

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    assert main(["run"]) == 0

    assert (home / "labor-sieve" / "output" / "latest.txt").exists()
    assert not (other_dir / "output" / "latest.txt").exists()
