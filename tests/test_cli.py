from pathlib import Path

import pytest
import yaml

from labor_sieve import __version__
from labor_sieve.cli import fetch_source_with_status, main
from labor_sieve.sources.sample import SampleSource


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
    assert "Set location, seniority, remote/on-site, compensation, keywords, and sources." in output
    assert "Validate it: labor-sieve validate-config" in output
    assert "Run a scan: labor-sieve run" in output
    assert "Public remote and configured ATS sources are enabled by default; sample data is disabled." in output
    assert "locations.local_region" in output
    assert "locations.accepted_locations" in output
    assert "compensation.minimum_base" in output
    assert "Company and posting exclusions are under exclusions." in output
    assert "sources.workday.sites" in output
    assert "sources.remoteok" in output
    assert "sources.arbeitnow" in output
    assert "Review or edit the enabled RemoteOK, Greenhouse, Lever, Ashby, and Workday source lists." in output
    assert "Disable any source by setting that source's enabled field to false." in output
    assert f"labor-sieve validate-config -c {expected_config}" not in output
    assert str(expected_report) in output


def test_quickstart_accepts_explicit_config_path(tmp_path, capsys):
    config_path = tmp_path / "custom" / "config.yaml"

    assert main(["quickstart", "-c", str(config_path)]) == 0

    output = capsys.readouterr().out
    assert config_path.exists()
    assert f"Config file: {config_path}" in output
    assert "Create the config file" not in output
    assert f"labor-sieve validate-config -c {config_path}" in output
    assert f"labor-sieve run -c {config_path}" in output
    assert str(config_path.parent / "output" / "latest.txt") in output


def test_quickstart_skips_create_steps_when_config_exists(tmp_path, capsys):
    config_path = tmp_path / "labor-sieve" / "config.yaml"
    config_path.parent.mkdir()
    write_sample_only_config(config_path)

    assert main(["quickstart", "-c", str(config_path)]) == 0

    output = capsys.readouterr().out
    assert f"Config file: {config_path}" in output
    assert "Create the config file" not in output
    assert "labor-sieve init -c" not in output
    assert "now contains the default commented settings" not in output
    assert "Next steps:" in output
    assert "quickstart keeps existing values" in output
    assert "quickstart --reset-config" in output


def test_quickstart_reset_config_replaces_existing_config(tmp_path, capsys):
    config_path = tmp_path / "labor-sieve" / "config.yaml"
    config_path.parent.mkdir()
    config_path.write_text("existing: true\n", encoding="utf-8")

    assert main(["quickstart", "--reset-config", "-c", str(config_path)]) == 0

    output = capsys.readouterr().out
    assert "Replaced" in output
    assert (config_path.parent / "config.yaml.bak").read_text(encoding="utf-8") == "existing: true\n"
    assert "workday:" in config_path.read_text(encoding="utf-8")


def test_uninstall_data_requires_yes(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    config_dir = tmp_path / "labor-sieve"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("existing: true\n", encoding="utf-8")

    assert main(["uninstall-data"]) == 0

    output = capsys.readouterr().out
    assert "labor-sieve uninstall-data --yes" in output
    assert config_dir.exists()


def test_uninstall_data_removes_user_paths(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    paths = [
        tmp_path / "labor-sieve",
        tmp_path / ".config" / "labor-sieve",
        tmp_path / ".local" / "state" / "labor-sieve",
    ]
    for path in paths:
        path.mkdir(parents=True)
        (path / "marker.txt").write_text("data\n", encoding="utf-8")

    assert main(["uninstall-data", "--yes"]) == 0

    output = capsys.readouterr().out
    assert "Removed" in output
    assert all(not path.exists() for path in paths)


def test_config_upgrade_command_adds_missing_sections(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    write_legacy_sample_config(config_path)

    assert main(["config-upgrade", "-c", str(config_path)]) == 0

    output = capsys.readouterr().out
    upgraded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "Config updated:" in output
    assert "sources.workday" in output
    assert (tmp_path / "config.yaml.bak").exists()
    assert upgraded["sources"]["sample"]["enabled"] is True
    assert upgraded["sources"]["workday"]["enabled"] is True


def test_validate_config_upgrades_before_validation(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    write_legacy_sample_config(config_path)

    assert main(["validate-config", "-c", str(config_path)]) == 0

    output = capsys.readouterr().out
    assert "Config updated:" in output
    assert f"{config_path} is valid." in output
    assert (tmp_path / "config.yaml.bak").exists()


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
    write_sample_only_config(config_path)
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    assert main(["run", "-c", str(config_path)]) == 0

    assert (config_path.parent / "output" / "latest.txt").exists()
    assert not (other_dir / "output" / "latest.txt").exists()


def test_run_uses_home_config_when_no_local_config_exists(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    config_path = home / "labor-sieve" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    write_sample_only_config(config_path)

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    assert main(["run"]) == 0

    assert (home / "labor-sieve" / "output" / "latest.txt").exists()
    assert not (other_dir / "output" / "latest.txt").exists()


def test_run_upgrades_config_before_loading(tmp_path, capsys):
    config_path = tmp_path / "project" / "config.yaml"
    config_path.parent.mkdir()
    write_legacy_sample_config(config_path)

    assert main(["run", "-c", str(config_path)]) == 0

    captured = capsys.readouterr()
    assert "Config updated:" in captured.err
    assert "sources.workday" in captured.err
    assert (config_path.parent / "config.yaml.bak").exists()
    assert (config_path.parent / "output" / "latest.txt").exists()


def test_fetch_source_with_status_prints_progress(capsys):
    jobs = fetch_source_with_status(SampleSource())

    stderr = capsys.readouterr().err
    assert jobs
    assert "Fetching sample..." in stderr
    assert "Fetching sample finished" in stderr


def write_sample_only_config(path: Path) -> None:
    data = yaml.safe_load((ROOT / "config.example.yaml").read_text(encoding="utf-8"))
    for source_config in data["sources"].values():
        if isinstance(source_config, dict) and "enabled" in source_config:
            source_config["enabled"] = False
    data["sources"]["sample"]["enabled"] = True
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def write_legacy_sample_config(path: Path) -> None:
    data = yaml.safe_load((ROOT / "config.example.yaml").read_text(encoding="utf-8"))
    for source_config in data["sources"].values():
        if isinstance(source_config, dict) and "enabled" in source_config:
            source_config["enabled"] = False
    data["sources"]["sample"]["enabled"] = True
    data["sources"].pop("ashby")
    data["sources"].pop("workday")
    data["locations"].pop("local_region")
    data["locations"]["accepted_locations"] = ["Richmond, VA"]
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
