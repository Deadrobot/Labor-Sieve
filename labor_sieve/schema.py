"""JSON Schema for LaborSieve config files."""

from __future__ import annotations

import json

from .config import MAX_LOCAL_FILE_PATHS, MAX_SOURCE_TARGETS, MAX_TIMEOUT_SECONDS, MAX_WORKDAY_SITES
from .taxonomy import ROLE_FAMILIES, SENIORITY_LEVELS


def config_schema() -> dict[str, object]:
    role_family_properties = {role: number_schema(0, 1) for role in ROLE_FAMILIES}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "LaborSieve config.yaml",
        "type": "object",
        "additionalProperties": True,
        "required": ["seniority", "role_family_weights", "keywords", "locations", "compensation", "output", "sources"],
        "properties": {
            "seniority": {
                "type": "object",
                "required": ["min", "max", "allow_principal", "allow_executive"],
                "properties": {
                    "min": {"enum": SENIORITY_LEVELS},
                    "max": {"enum": SENIORITY_LEVELS},
                    "allow_principal": {"type": "boolean"},
                    "allow_executive": {"type": "boolean"},
                },
            },
            "role_family_weights": {
                "type": "object",
                "properties": role_family_properties,
                "additionalProperties": number_schema(0, 1),
            },
            "keywords": {
                "type": "object",
                "required": ["boost", "penalize"],
                "properties": {
                    "boost": string_array_schema(),
                    "penalize": string_array_schema(),
                },
            },
            "language_requirements": {
                "type": "object",
                "properties": {
                    "accepted": string_array_schema(),
                    "boost": string_array_schema(),
                    "penalty": integer_schema(0),
                    "boost_points": integer_schema(0),
                },
            },
            "locations": {
                "type": "object",
                "required": ["remote"],
                "properties": {
                    "remote": {"type": "boolean"},
                    "local_region": {
                        "type": "object",
                        "properties": {
                            "center": {"type": "string", "minLength": 1},
                            "radius_miles": integer_schema(1),
                        },
                    },
                    "accepted_locations": string_array_schema(),
                    "hybrid_locations": string_array_schema(),
                    "accepted_remote_locations": string_array_schema(),
                },
            },
            "compensation": {
                "type": "object",
                "properties": {
                    "minimum_base": nullable_number_schema(0),
                    "minimum_base_by_seniority": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {level: nullable_number_schema(0) for level in SENIORITY_LEVELS},
                    },
                },
            },
            "exclusions": {
                "type": "object",
                "properties": {
                    "companies": string_array_schema(),
                    "urls": string_array_schema(),
                    "source_ids": string_array_schema(),
                },
            },
            "output": {
                "type": "object",
                "required": ["directory", "txt", "csv", "json", "html"],
                "properties": {
                    "directory": {"type": "string", "minLength": 1},
                    "txt": {"type": "boolean"},
                    "csv": {"type": "boolean"},
                    "json": {"type": "boolean"},
                    "html": {"type": "boolean"},
                    "terminal_p0_limit": integer_schema(0),
                    "terminal_p1_limit": integer_schema(0),
                },
            },
            "update_check": {
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean"},
                    "interval_days": integer_schema(1, 365),
                },
            },
            "sources": sources_schema(),
        },
    }


def render_config_schema() -> str:
    return json.dumps(config_schema(), indent=2, sort_keys=True) + "\n"


def sources_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "sample": enabled_source_schema({}),
            "local_file": enabled_source_schema({"paths": string_array_schema(MAX_LOCAL_FILE_PATHS)}),
            "remoteok": enabled_source_schema(
                {
                    "timeout_seconds": integer_schema(1, MAX_TIMEOUT_SECONDS),
                    "max_jobs": integer_schema(1, 5000),
                    "base_url": {"const": "https://remoteok.com/api"},
                }
            ),
            "arbeitnow": enabled_source_schema(
                {
                    "timeout_seconds": integer_schema(1, MAX_TIMEOUT_SECONDS),
                    "max_pages": integer_schema(1, 20),
                    "max_jobs": integer_schema(1, 5000),
                    "base_url": {"const": "https://www.arbeitnow.com/api/job-board-api"},
                }
            ),
            "greenhouse": enabled_source_schema(
                {
                    "board_tokens": string_array_schema(MAX_SOURCE_TARGETS),
                    "timeout_seconds": integer_schema(1, MAX_TIMEOUT_SECONDS),
                }
            ),
            "lever": enabled_source_schema(
                {
                    "companies": string_array_schema(MAX_SOURCE_TARGETS),
                    "timeout_seconds": integer_schema(1, MAX_TIMEOUT_SECONDS),
                    "base_url": {"const": "https://api.lever.co/v0/postings"},
                }
            ),
            "ashby": enabled_source_schema(
                {
                    "organizations": string_array_schema(MAX_SOURCE_TARGETS),
                    "timeout_seconds": integer_schema(1, MAX_TIMEOUT_SECONDS),
                    "base_url": {"const": "https://api.ashbyhq.com/posting-api/job-board"},
                }
            ),
            "workday": enabled_source_schema(
                {
                    "sites": {
                        "type": "array",
                        "maxItems": MAX_WORKDAY_SITES,
                        "items": {
                            "type": "object",
                            "required": ["company", "url"],
                            "properties": {
                                "company": {"type": "string", "minLength": 1},
                                "url": {
                                    "type": "string",
                                    "pattern": r"^https://[^/]+\.myworkdayjobs\.com/.+",
                                },
                            },
                        },
                    },
                    "timeout_seconds": integer_schema(1, MAX_TIMEOUT_SECONDS),
                    "page_size": integer_schema(1, 100),
                    "max_jobs_per_site": integer_schema(1, 5000),
                }
            ),
        },
    }


def enabled_source_schema(properties: dict[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {"enabled": {"type": "boolean"}, **properties},
    }


def string_array_schema(max_items: int | None = None) -> dict[str, object]:
    schema: dict[str, object] = {
        "type": "array",
        "items": {"type": "string"},
    }
    if max_items is not None:
        schema["maxItems"] = max_items
    return schema


def integer_schema(minimum: int, maximum: int | None = None) -> dict[str, object]:
    schema: dict[str, object] = {"type": "integer", "minimum": minimum}
    if maximum is not None:
        schema["maximum"] = maximum
    return schema


def number_schema(minimum: int, maximum: int | None = None) -> dict[str, object]:
    schema: dict[str, object] = {"type": "number", "minimum": minimum}
    if maximum is not None:
        schema["maximum"] = maximum
    return schema


def nullable_number_schema(minimum: int) -> dict[str, object]:
    return {"anyOf": [number_schema(minimum), {"type": "null"}]}
