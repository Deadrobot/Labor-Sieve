"""Helpers for turning source-specific job records into Job objects."""

from __future__ import annotations

import hashlib
import html
import re
from html.parser import HTMLParser
from typing import Any

from labor_sieve.models import Job
from labor_sieve.taxonomy import ROLE_FAMILIES, SENIORITY_LEVELS


class _TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return " ".join(self.parts)


def normalize_job_record(
    record: dict[str, Any],
    *,
    source_name: str,
    index: int,
    company_default: str = "Unknown company",
) -> Job:
    title = first_string(record, "title", "job_title", "name", "text") or "Untitled job"
    company = first_string(record, "company", "company_name") or company_default
    location = normalize_location(record.get("location")) or first_string(record, "location_name") or "Unknown"
    description = clean_text(
        first_string(record, "description", "content", "body", "summary", "details") or ""
    )
    url = first_string(
        record,
        "url",
        "absolute_url",
        "apply_url",
        "job_url",
        "hostedUrl",
        "applyUrl",
        "hosted_url",
        "apply_url",
    ) or ""
    tags = normalize_tags(record.get("tags"))

    categories = normalize_category_tags(record.get("categories"))
    tags.extend(categories)

    departments = normalize_name_list(record.get("departments"))
    offices = normalize_name_list(record.get("offices"))
    tags.extend(departments)
    tags.extend(offices)

    tag_text = " ".join(tags)
    text_for_inference = " ".join([title, company, location, description, tag_text])
    location_text_for_inference = " ".join([location, tag_text])
    seniority = first_string(record, "seniority", "level") or infer_seniority(text_for_inference)
    if seniority not in SENIORITY_LEVELS:
        seniority = infer_seniority(text_for_inference)

    role_family = first_string(record, "role_family", "family") or infer_role_family(title, text_for_inference)
    if role_family not in ROLE_FAMILIES and not _is_snake_case(role_family):
        role_family = "unknown"

    remote = first_bool(record, "remote")
    if remote is None:
        remote = infer_remote(location_text_for_inference)
    hybrid = first_bool(record, "hybrid")
    if hybrid is None:
        hybrid = infer_hybrid(location_text_for_inference)
    remote, hybrid = resolve_workplace_flags(remote, hybrid)

    job_id = first_string(record, "id", "job_id", "requisition_id", "internal_job_id")
    if not job_id:
        stable = "|".join([source_name, title, company, location, url, str(index)])
        job_id = f"{source_name}-{hashlib.sha1(stable.encode('utf-8')).hexdigest()[:12]}"

    return Job(
        id=str(job_id),
        title=title,
        company=company,
        location=location,
        remote=remote,
        hybrid=hybrid,
        seniority=seniority,
        role_family=role_family,
        compensation_base_min=parse_money(
            first_value(
                record,
                "compensation_base_min",
                "base_min",
                "salary_min",
                "minimum_base",
                "salaryRange",
            )
        ),
        url=url,
        description=description,
        tags=dedupe_preserve_order(tags),
        source=source_name,
        source_id=str(job_id),
    )


def first_value(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def first_string(record: dict[str, Any], *keys: str) -> str | None:
    value = first_value(record, *keys)
    if value is None:
        return None
    if isinstance(value, dict):
        return normalize_location(value)
    return str(value).strip() or None


def first_bool(record: dict[str, Any], *keys: str) -> bool | None:
    value = first_value(record, *keys)
    if value is None:
        return None
    return parse_bool(value)


def normalize_location(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        name = value.get("name") or value.get("location")
        return str(name).strip() if name else None
    return str(value).strip() or None


def normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        tags = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("name") or item.get("title") or item.get("value")
                if name:
                    tags.append(str(name).strip())
            elif item not in (None, ""):
                tags.append(str(item).strip())
        return [tag for tag in tags if tag]
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[;,]", value) if part.strip()]
    return [str(value).strip()]


def normalize_name_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names = []
    for item in value:
        if isinstance(item, dict):
            name = item.get("name") or item.get("title")
            if name:
                names.append(str(name).strip())
        elif item not in (None, ""):
            names.append(str(item).strip())
    return [name for name in names if name]


def normalize_category_tags(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    tags = []
    for key in ("team", "department", "location", "commitment", "level"):
        item = value.get(key)
        if item not in (None, ""):
            tags.append(str(item).strip())
    return [tag for tag in tags if tag]


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    text = str(value).strip().casefold()
    return text in {"1", "yes", "y", "true", "remote"}


def parse_money(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, dict):
        for key in ("min", "minimum", "minimum_base", "base_min", "minAmount", "amount"):
            parsed = parse_money(value.get(key))
            if parsed is not None:
                return parsed
        return None
    if isinstance(value, int | float) and not isinstance(value, bool):
        return int(value)
    text = str(value).strip().casefold().replace(",", "")
    matches = list(re.finditer(r"(?P<dollar>\$)?\s*(?P<number>\d+(?:\.\d+)?)\s*(?P<suffix>k)?\b", text))
    if not matches:
        return None
    has_k_range = any(match.group("suffix") == "k" for match in matches)
    has_money_context = any(term in text for term in ("$", "salary", "base", "compensation"))
    amounts = []
    for match in matches:
        number = float(match.group("number"))
        if number < 1000 and (
            match.group("suffix") == "k"
            or match.group("dollar")
            or has_k_range
            or has_money_context
        ):
            number *= 1000
        amounts.append(int(number))
    return min(amounts)


def clean_text(value: str) -> str:
    text = html.unescape(value)
    parser = _TextHTMLParser()
    parser.feed(text)
    parsed = parser.text()
    if parsed:
        text = parsed
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def infer_remote(text: str) -> bool:
    normalized = text.casefold()
    return "remote" in normalized or "work from home" in normalized or "wfh" in normalized


def infer_hybrid(text: str) -> bool:
    return "hybrid" in text.casefold()


def resolve_workplace_flags(remote: bool, hybrid: bool) -> tuple[bool, bool]:
    if remote and hybrid:
        return False, True
    return remote, hybrid


def infer_seniority(text: str) -> str:
    normalized = text.casefold()
    if re.search(r"\b(vp|vice president|chief|cxo|executive)\b", normalized):
        return "executive"
    if re.search(r"\bprincipal\b", normalized):
        return "principal"
    if re.search(r"\bstaff\b", normalized):
        return "staff"
    if re.search(r"\b(senior|sr\.?|lead)\b", normalized):
        return "senior"
    if re.search(r"\b(junior|jr\.?)\b", normalized):
        return "junior"
    if re.search(r"\b(entry|associate|technician i)\b", normalized):
        return "entry"
    return "mid"


def infer_role_family(title: str, text: str = "") -> str:
    normalized_title = title.casefold()
    normalized = " ".join([title, text]).casefold()
    if re.search(r"\bincident manager\b", normalized_title) and any(
        term in normalized for term in ("linux", "on-call", "incident response", "sre", "site reliability")
    ):
        return "sre_infra_ops"
    if re.search(r"\b(vp|vice president|chief|cxo|executive|director|head of|manager)\b", normalized_title):
        return "management"
    if re.search(
        r"\b(frontend|front-end|backend|full[- ]stack|mobile|ios|android|software engineer)\b",
        normalized_title,
    ) and not re.search(r"\b(site reliability|sre)\b", normalized_title):
        return "software_engineering"
    if re.search(r"\bsales engineer\b", normalized_title):
        return "customer_operations"
    if re.search(
        r"\b(applied scientist|data scientist|research scientist|machine learning scientist|ml scientist)\b",
        normalized_title,
    ):
        return "software_engineering"
    if re.search(
        r"\b(network engineer|network deployment|network operations|network technician|network administrator)\b",
        normalized_title,
    ):
        return "networking"
    if any(term in normalized_title for term in ("data center", "datacenter", "hardware", "rack", "diagnostic")):
        return "data_center_ops"
    if any(term in normalized_title for term in ("logistics", "process improvement", "workflow")):
        return "logistics_process"
    if any(term in normalized_title for term in ("implementation", "customer support", "support engineer")):
        return "implementation_support"
    if any(term in normalized_title for term in ("sre", "site reliability", "linux", "incident response")):
        return "sre_infra_ops"
    if any(term in normalized_title for term in ("platform", "terraform", "kubernetes", "infrastructure")):
        return "platform_ops"
    if re.search(r"\b(vp|vice president|chief|cxo|executive|director|head of)\b", normalized):
        return "management"
    if any(term in normalized for term in ("data center", "datacenter", "hardware", "rack", "diagnostic")):
        return "data_center_ops"
    if any(term in normalized for term in ("logistics", "process improvement", "workflow", "sop", "kpi")):
        return "logistics_process"
    if any(term in normalized for term in ("implementation", "customer support", "support escalation", "integration")):
        return "implementation_support"
    if any(term in normalized for term in ("sre", "site reliability", "linux", "incident response", "on-call")):
        return "sre_infra_ops"
    if any(term in normalized for term in ("platform", "terraform", "kubernetes", "infrastructure")):
        return "platform_ops"
    if any(term in normalized for term in ("customer operations", "support operations")):
        return "customer_operations"
    if any(term in normalized for term in ("frontend", "backend", "full-stack", "software engineer")):
        return "software_engineering"
    if "architect" in normalized:
        return "architect"
    if any(term in normalized for term in ("people management", "people manager", "manager of managers")):
        return "management"
    return "unknown"


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        normalized = value.strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            deduped.append(normalized)
    return deduped


def _is_snake_case(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*", value))
