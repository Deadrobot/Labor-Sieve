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


def test_quickstart_prints_first_run_steps(capsys):
    assert main(["quickstart"]) == 0

    output = capsys.readouterr().out
    expected_config = Path.home() / "labor-sieve" / "config.yaml"
    assert "Next steps:" in output
    assert f"Config file: {expected_config}" in output
    assert "labor-sieve init -c config.yaml" in output
    assert "labor-sieve validate-config -c config.yaml" in output
    assert str(Path.home() / "labor-sieve" / "output" / "latest.txt") in output


def test_quickstart_accepts_explicit_config_path(tmp_path, capsys):
    config_path = tmp_path / "custom" / "config.yaml"

    assert main(["quickstart", "-c", str(config_path)]) == 0

    output = capsys.readouterr().out
    assert f"Config file: {config_path}" in output
    assert f"mkdir -p {config_path.parent}" in output
    assert str(config_path.parent / "output" / "latest.txt") in output


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
