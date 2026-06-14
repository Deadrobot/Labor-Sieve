import io
import json

from labor_sieve.update_check import (
    SKIP_ENV_VAR,
    is_version_newer,
    maybe_print_update_notice,
)


def test_update_notice_prints_when_pypi_has_newer_version(tmp_path, monkeypatch):
    monkeypatch.delenv(SKIP_ENV_VAR, raising=False)
    state_path = tmp_path / "update-check.json"
    stream = io.StringIO()

    printed = maybe_print_update_notice(
        installed_version="0.1.15",
        enabled=True,
        interval_days=7,
        stream=stream,
        state_path=state_path,
        now=1000,
        fetch_latest_version=lambda: "0.1.16",
    )

    assert printed is True
    assert "LaborSieve 0.1.16 is available. Installed version: 0.1.15." in stream.getvalue()
    assert "pipx upgrade labor-sieve" in stream.getvalue()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["checked_at"] == 1000
    assert state["latest_version"] == "0.1.16"


def test_update_check_skips_until_interval_elapsed(tmp_path, monkeypatch):
    monkeypatch.delenv(SKIP_ENV_VAR, raising=False)
    state_path = tmp_path / "update-check.json"
    state_path.write_text(json.dumps({"checked_at": 1000}), encoding="utf-8")
    stream = io.StringIO()

    printed = maybe_print_update_notice(
        installed_version="0.1.15",
        enabled=True,
        interval_days=7,
        stream=stream,
        state_path=state_path,
        now=1000 + 6 * 24 * 60 * 60,
        fetch_latest_version=lambda: "0.1.16",
    )

    assert printed is False
    assert stream.getvalue() == ""


def test_update_check_is_quiet_when_fetch_fails(tmp_path, monkeypatch):
    monkeypatch.delenv(SKIP_ENV_VAR, raising=False)
    state_path = tmp_path / "update-check.json"
    stream = io.StringIO()

    def fail():
        raise OSError("network unavailable")

    printed = maybe_print_update_notice(
        installed_version="0.1.15",
        enabled=True,
        interval_days=7,
        stream=stream,
        state_path=state_path,
        now=1000,
        fetch_latest_version=fail,
    )

    assert printed is False
    assert stream.getvalue() == ""
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["checked_at"] == 1000
    assert state["latest_version"] is None


def test_update_check_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv(SKIP_ENV_VAR, raising=False)
    stream = io.StringIO()

    printed = maybe_print_update_notice(
        installed_version="0.1.15",
        enabled=False,
        interval_days=7,
        stream=stream,
        state_path=tmp_path / "update-check.json",
        fetch_latest_version=lambda: "0.1.16",
    )

    assert printed is False
    assert stream.getvalue() == ""


def test_version_comparison_handles_multi_digit_releases():
    assert is_version_newer("0.1.16", "0.1.15")
    assert is_version_newer("0.1.10", "0.1.9")
    assert not is_version_newer("0.1.15", "0.1.15")
