from pathlib import Path

import yaml

from labor_sieve.config import config_from_data, init_config, validate_config_data


ROOT = Path(__file__).resolve().parents[1]


def load_example():
    return yaml.safe_load((ROOT / "config.example.yaml").read_text(encoding="utf-8"))


def test_example_config_is_valid():
    data = load_example()

    errors = validate_config_data(data)

    assert errors == []
    config = config_from_data(data)
    assert config.seniority.min == "mid"
    assert config.sources.sample.enabled is False
    assert config.sources.local_file.enabled is False
    assert config.sources.greenhouse.enabled is True
    assert config.sources.lever.enabled is True
    assert config.sources.ashby.enabled is True
    assert config.sources.workday.enabled is True
    assert config.sources.greenhouse.board_tokens == ["cloudflare", "canonical", "coreweave", "samsara"]
    assert config.sources.lever.companies == ["palantir"]
    assert config.sources.ashby.organizations == ["Lambda", "Crusoe", "Modal", "openai"]
    assert [site.company for site in config.sources.workday.sites] == ["NVIDIA", "Equinix", "Micron"]
    assert config.sources.workday.max_jobs_per_site == 100
    assert config.locations.local_region.center == "Richmond, VA"
    assert config.locations.local_region.radius_miles == 40
    assert "Richmond, VA" in config.locations.accepted_locations
    assert "Petersburg, VA" in config.locations.accepted_locations


def test_validation_reports_seniority_order_error():
    data = load_example()
    data["seniority"]["min"] = "staff"
    data["seniority"]["max"] = "mid"

    errors = validate_config_data(data)

    assert "seniority.min must not be higher than seniority.max." in errors


def test_validation_allows_custom_role_family_weights():
    data = load_example()
    data["role_family_weights"]["field_enablement"] = 0.72

    errors = validate_config_data(data)

    assert errors == []


def test_validation_accepts_configured_sources():
    data = load_example()
    data["sources"]["sample"]["enabled"] = False
    data["sources"]["local_file"]["enabled"] = True
    data["sources"]["local_file"]["paths"] = ["jobs.csv"]
    data["sources"]["greenhouse"]["enabled"] = True
    data["sources"]["greenhouse"]["board_tokens"] = ["example"]
    data["sources"]["greenhouse"]["timeout_seconds"] = 10
    data["sources"]["lever"]["enabled"] = True
    data["sources"]["lever"]["companies"] = ["example"]
    data["sources"]["lever"]["timeout_seconds"] = 10
    data["sources"]["ashby"]["enabled"] = True
    data["sources"]["ashby"]["organizations"] = ["example"]
    data["sources"]["ashby"]["timeout_seconds"] = 10
    data["sources"]["workday"]["enabled"] = True
    data["sources"]["workday"]["sites"] = [
        {
            "company": "Example Company",
            "url": "https://example.wd5.myworkdayjobs.com/ExampleExternalCareerSite",
        }
    ]
    data["sources"]["workday"]["timeout_seconds"] = 10
    data["sources"]["workday"]["page_size"] = 10
    data["sources"]["workday"]["max_jobs_per_site"] = 100

    errors = validate_config_data(data)
    config = config_from_data(data)

    assert errors == []
    assert config.sources.sample.enabled is False
    assert config.sources.local_file.paths == ["jobs.csv"]
    assert config.sources.greenhouse.board_tokens == ["example"]
    assert config.sources.lever.companies == ["example"]
    assert config.sources.ashby.organizations == ["example"]
    assert config.sources.workday.sites[0].company == "Example Company"
    assert config.sources.workday.page_size == 10
    assert config.sources.workday.max_jobs_per_site == 100


def test_validation_requires_https_for_lever_base_url():
    data = load_example()
    data["sources"]["lever"]["base_url"] = "http://api.lever.co/v0/postings"

    errors = validate_config_data(data)

    assert "sources.lever.base_url must start with https://." in errors


def test_validation_requires_https_for_ashby_base_url():
    data = load_example()
    data["sources"]["ashby"]["base_url"] = "http://api.ashbyhq.com/posting-api/job-board"

    errors = validate_config_data(data)

    assert "sources.ashby.base_url must start with https://." in errors


def test_validation_requires_workday_site_url():
    data = load_example()
    data["sources"]["workday"]["sites"] = [
        {
            "company": "Example Company",
            "url": "https://example.invalid/ExampleExternalCareerSite",
        }
    ]

    errors = validate_config_data(data)

    assert "sources.workday.sites[0].url must be an https://*.myworkdayjobs.com URL." in errors


def test_validation_accepts_legacy_hybrid_locations():
    data = load_example()
    data["locations"].pop("accepted_locations")
    data["locations"]["hybrid_locations"] = ["Richmond, VA"]

    errors = validate_config_data(data)
    config = config_from_data(data)

    assert errors == []
    assert config.locations.accepted_locations == ["Richmond, VA"]


def test_validation_reports_invalid_local_region_radius():
    data = load_example()
    data["locations"]["local_region"]["radius_miles"] = 0

    errors = validate_config_data(data)

    assert "locations.local_region.radius_miles must be a positive integer." in errors


def test_init_config_does_not_overwrite_existing_file(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("existing: true\n", encoding="utf-8")

    message = init_config(config_path)

    assert "already exists" in message
    assert str(config_path) in message
    assert config_path.read_text(encoding="utf-8") == "existing: true\n"


def test_init_config_uses_packaged_example_not_current_directory(tmp_path, monkeypatch):
    (tmp_path / "config.example.yaml").write_text("wrong: true\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"

    init_config(config_path)

    text = config_path.read_text(encoding="utf-8")
    assert text.startswith("# LaborSieve configuration.")
    assert "wrong: true" not in text
