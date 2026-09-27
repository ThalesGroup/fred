# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Operational authentication metrics. No identities, URLs or credentials as labels."""

from prometheus_client import Counter, Histogram

M2M_CACHE = Counter(
    "fred_auth_m2m_cache", "Workload token cache decisions", ["outcome"]
)
M2M_REQUEST = Histogram(
    "fred_auth_m2m_request_seconds",
    "IAM workload token request latency",
    ["operation", "outcome"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 15),
)
M2M_ACQUIRE = Histogram(
    "fred_auth_m2m_acquire_seconds",
    "Caller token wait including lock and IAM",
    ["outcome"],
    buckets=(0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 15),
)
DELEGATION = Counter(
    "fred_auth_delegation_decisions",
    "Delegation grant validation decisions",
    ["outcome", "reason"],
)


def observe_m2m(event: str, outcome: str, seconds: float) -> None:
    if event == "cache" and outcome in {"hit", "miss", "shared_refresh"}:
        M2M_CACHE.labels(outcome).inc()
    elif outcome in {"success", "error", "cancelled"}:
        if event in {"request_initial", "request_renewal"}:
            M2M_REQUEST.labels(event.removeprefix("request_"), outcome).observe(seconds)
        elif event == "acquire":
            M2M_ACQUIRE.labels(outcome).observe(seconds)


# Known finite series exist at zero before traffic. Absence then indicates missing
# instrumentation/scraping, rather than being indistinguishable from no failures.
for operation in ("initial", "renewal"):
    for outcome in ("success", "error", "cancelled"):
        M2M_REQUEST.labels(operation, outcome)
for outcome in ("success", "error", "cancelled"):
    M2M_ACQUIRE.labels(outcome)
for outcome in ("hit", "miss", "shared_refresh"):
    M2M_CACHE.labels(outcome)
for outcome, reason in (
    ("accepted", "grant_validated"),
    ("rejected", "invalid_parameters"),
    ("rejected", "caller_not_allowed"),
    ("rejected", "caller_not_trusted"),
):
    DELEGATION.labels(outcome, reason)
