import pytest


@pytest.fixture(autouse=True)
def skip_update_check(monkeypatch):
    monkeypatch.setenv("LABOR_SIEVE_SKIP_UPDATE_CHECK", "1")
    monkeypatch.setenv("LABOR_SIEVE_SKIP_RUN_HISTORY", "1")
