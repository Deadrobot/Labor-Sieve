from pathlib import Path

import yaml

from labor_sieve.config import config_from_data, init_config, upgrade_config, validate_config_data


ROOT = Path(__file__).resolve().parents[1]


def load_example():
    return yaml.safe_load((ROOT / "config.example.yaml").read_text(encoding="utf-8"))


def test_example_config_is_valid():
    data = load_example()

    errors = validate_config_data(data)

    assert errors == []
    config = config_from_data(data)
    assert config.seniority.min == "mid"
    assert config.seniority.max == "senior"
    assert config.sources.sample.enabled is False
    assert config.sources.local_file.enabled is False
    assert config.sources.remoteok.enabled is True
    assert config.sources.remoteok.max_jobs == 250
    assert config.sources.arbeitnow.enabled is False
    assert config.sources.arbeitnow.max_pages == 1
    assert config.sources.greenhouse.enabled is True
    assert config.sources.lever.enabled is True
    assert config.sources.ashby.enabled is True
    assert config.sources.workday.enabled is True
    assert config.sources.greenhouse.board_tokens == [
        "cloudflare",
        "canonical",
        "coreweave",
        "samsara",
        "nebius",
    ]
    assert config.sources.lever.companies == ["waabi"]
    assert config.sources.ashby.organizations == ["Lambda", "Crusoe", "Modal", "openai"]
    assert [site.company for site in config.sources.workday.sites] == ["NVIDIA", "Equinix", "Micron"]
    assert config.sources.workday.max_jobs_per_site == 100
    assert config.exclusions.companies == []
    assert config.exclusions.urls == []
    assert config.exclusions.source_ids == []
    assert config.role_family_weights["networking"] == 0.25
    assert config.locations.local_region.center == "Richmond, VA"
    assert config.locations.local_region.radius_miles == 40
    assert "Richmond, VA" in config.locations.accepted_locations
    assert "Petersburg, VA" in config.locations.accepted_locations
    assert "United States" in config.locations.accepted_remote_locations
    assert config.output.terminal_p0_limit == 10
    assert config.output.terminal_p1_limit == 15
    assert config.sources.ashby.timeout_seconds == 30
    assert config.language_requirements.accepted == ["english"]
    assert config.language_requirements.boost == []
    assert config.language_requirements.penalty == 8
    assert config.language_requirements.boost_points == 6
    assert config.compensation.minimum_base == 85000
    assert config.compensation.minimum_base_by_seniority["entry"] == 85000
    assert config.compensation.minimum_base_by_seniority["mid"] == 95000
    assert config.compensation.minimum_base_by_seniority["senior"] == 105000


def test_validation_reports_seniority_order_error():
    data = load_example()
    data["seniority"]["min"] = "staff"
    data["seniority"]["max"] = "mid"

    errors = validate_config_data(data)

    assert "seniority.min must not be higher than seniority.max." in errors


def test_validation_allows_custom_role_family_weights():
    data = load_example()
    data["role_family_weights"]["field_enablement"] = 0.72
    data["role_family_weights"]["networking"] = 0.4

    errors = validate_config_data(data)

    assert errors == []


def test_validation_accepts_configured_sources():
    data = load_example()
    data["sources"]["sample"]["enabled"] = False
    data["sources"]["local_file"]["enabled"] = True
    data["sources"]["local_file"]["paths"] = ["jobs.csv"]
    data["sources"]["remoteok"]["enabled"] = True
    data["sources"]["remoteok"]["timeout_seconds"] = 10
    data["sources"]["remoteok"]["max_jobs"] = 50
    data["sources"]["remoteok"]["base_url"] = "https://remoteok.com/api"
    data["sources"]["arbeitnow"]["enabled"] = True
    data["sources"]["arbeitnow"]["timeout_seconds"] = 10
    data["sources"]["arbeitnow"]["max_pages"] = 2
    data["sources"]["arbeitnow"]["max_jobs"] = 50
    data["sources"]["arbeitnow"]["base_url"] = "https://www.arbeitnow.com/api/job-board-api"
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
    data["exclusions"]["companies"] = ["Example Co"]
    data["exclusions"]["urls"] = ["https://example.invalid/jobs/1"]
    data["exclusions"]["source_ids"] = ["ashby:abc"]

    errors = validate_config_data(data)
    config = config_from_data(data)

    assert errors == []
    assert config.sources.sample.enabled is False
    assert config.sources.local_file.paths == ["jobs.csv"]
    assert config.sources.remoteok.max_jobs == 50
    assert config.sources.arbeitnow.max_pages == 2
    assert config.sources.greenhouse.board_tokens == ["example"]
    assert config.sources.lever.companies == ["example"]
    assert config.sources.ashby.organizations == ["example"]
    assert config.sources.workday.sites[0].company == "Example Company"
    assert config.sources.workday.page_size == 10
    assert config.sources.workday.max_jobs_per_site == 100
    assert config.exclusions.companies == ["Example Co"]
    assert config.exclusions.urls == ["https://example.invalid/jobs/1"]
    assert config.exclusions.source_ids == ["ashby:abc"]


def test_validation_accepts_language_requirement_preferences():
    data = load_example()
    data["language_requirements"] = {
        "accepted": ["english", "spanish"],
        "boost": ["korean"],
        "penalty": 5,
        "boost_points": 7,
    }

    errors = validate_config_data(data)
    config = config_from_data(data)

    assert errors == []
    assert config.language_requirements.accepted == ["english", "spanish"]
    assert config.language_requirements.boost == ["korean"]
    assert config.language_requirements.penalty == 5
    assert config.language_requirements.boost_points == 7


def test_validation_accepts_seniority_compensation_floors():
    data = load_example()
    data["compensation"]["minimum_base"] = 80000
    data["compensation"]["minimum_base_by_seniority"] = {
        "entry": 70000,
        "mid": 90000,
        "senior": 100000,
        "staff": None,
    }

    errors = validate_config_data(data)
    config = config_from_data(data)

    assert errors == []
    assert config.compensation.minimum_base == 80000
    assert config.compensation.minimum_base_by_seniority == {
        "entry": 70000,
        "mid": 90000,
        "senior": 100000,
        "staff": None,
    }


def test_validation_reports_invalid_seniority_compensation_floors():
    data = load_example()
    data["compensation"]["minimum_base_by_seniority"] = {
        "mid": -1,
        "expert": 100000,
        "senior": "high",
    }

    errors = validate_config_data(data)

    assert "compensation.minimum_base_by_seniority keys must be seniority levels (got 'expert')." in errors
    assert (
        "compensation.minimum_base_by_seniority.mid must be a non-negative number or null."
        in errors
    )
    assert (
        "compensation.minimum_base_by_seniority.senior must be a non-negative number or null."
        in errors
    )


def test_validation_reports_invalid_language_requirement_points():
    data = load_example()
    data["language_requirements"]["penalty"] = -1
    data["language_requirements"]["boost_points"] = "high"

    errors = validate_config_data(data)

    assert "language_requirements.penalty must be a non-negative integer." in errors
    assert "language_requirements.boost_points must be a non-negative integer." in errors


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


def test_init_config_force_backs_up_and_replaces_existing_file(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("existing: true\n", encoding="utf-8")

    message = init_config(config_path, overwrite=True)

    assert "Replaced" in message
    assert "Backup written to" in message
    assert (tmp_path / "config.yaml.bak").read_text(encoding="utf-8") == "existing: true\n"
    assert config_path.read_text(encoding="utf-8").startswith("# LaborSieve configuration.")


def test_upgrade_config_adds_missing_defaults_without_changing_existing_values(tmp_path):
    config_path = tmp_path / "config.yaml"
    data = load_example()
    data["sources"]["sample"]["enabled"] = True
    data["sources"]["greenhouse"]["board_tokens"] = ["custom-board"]
    data["sources"].pop("remoteok")
    data["sources"].pop("arbeitnow")
    data["sources"].pop("ashby")
    data["sources"].pop("workday")
    data.pop("language_requirements")
    data["compensation"].pop("minimum_base_by_seniority")
    data["locations"].pop("local_region")
    data["locations"].pop("accepted_remote_locations")
    data.pop("exclusions")
    data["output"].pop("terminal_p0_limit")
    data["output"].pop("terminal_p1_limit")
    data["locations"]["accepted_locations"] = ["Custom, VA"]
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    result = upgrade_config(config_path)

    upgraded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert result.changed is True
    assert result.added_paths == [
        "language_requirements",
        "locations.local_region",
        "locations.accepted_remote_locations",
        "compensation.minimum_base_by_seniority",
        "exclusions",
        "output.terminal_p0_limit",
        "output.terminal_p1_limit",
        "sources.remoteok",
        "sources.arbeitnow",
        "sources.ashby",
        "sources.workday",
    ]
    assert result.backup_path == tmp_path / "config.yaml.bak"
    assert (tmp_path / "config.yaml.bak").exists()
    assert upgraded["sources"]["sample"]["enabled"] is True
    assert upgraded["sources"]["greenhouse"]["board_tokens"] == ["custom-board"]
    assert upgraded["locations"]["accepted_locations"] == ["Custom, VA"]
    assert upgraded["language_requirements"]["accepted"] == ["english"]
    assert upgraded["language_requirements"]["boost"] == []
    assert upgraded["compensation"]["minimum_base_by_seniority"]["mid"] == 95000
    assert upgraded["locations"]["local_region"]["center"] == "Richmond, VA"
    assert "United States" in upgraded["locations"]["accepted_remote_locations"]
    assert upgraded["output"]["terminal_p0_limit"] == 10
    assert upgraded["sources"]["remoteok"]["enabled"] is True
    assert upgraded["sources"]["arbeitnow"]["enabled"] is False
    assert upgraded["sources"]["ashby"]["enabled"] is True
    assert upgraded["sources"]["workday"]["enabled"] is True
    assert "# Public Workday candidate experience source." in config_path.read_text(encoding="utf-8")


def test_upgrade_config_is_noop_when_config_is_current(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text((ROOT / "config.example.yaml").read_text(encoding="utf-8"), encoding="utf-8")

    result = upgrade_config(config_path)

    assert result.changed is False
    assert result.backup_path is None
    assert result.added_paths == []
    assert not (tmp_path / "config.yaml.bak").exists()


def test_init_config_uses_packaged_example_not_current_directory(tmp_path, monkeypatch):
    (tmp_path / "config.example.yaml").write_text("wrong: true\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"

    init_config(config_path)

    text = config_path.read_text(encoding="utf-8")
    assert text.startswith("# LaborSieve configuration.")
    assert "wrong: true" not in text
