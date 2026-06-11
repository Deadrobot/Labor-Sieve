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
    assert "Next steps:" in output
    assert "labor-sieve validate-config -c config.yaml" in output


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
