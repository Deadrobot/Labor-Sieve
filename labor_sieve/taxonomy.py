"""Shared taxonomy values for LaborSieve."""

SENIORITY_LEVELS = (
    "entry",
    "junior",
    "mid",
    "senior",
    "staff",
    "principal",
    "executive",
)

ROLE_FAMILIES = (
    "sre_infra_ops",
    "data_center_ops",
    "fleet_reliability",
    "platform_ops",
    "implementation_support",
    "logistics_process",
    "customer_operations",
    "networking",
    "software_engineering",
    "architect",
    "management",
    "unknown",
)

PRIORITY_BUCKETS = ("P0", "P1", "P2", "P3", "rejected")


def seniority_index(value: str) -> int:
    """Return the ordered index for a seniority value."""
    return SENIORITY_LEVELS.index(value)
