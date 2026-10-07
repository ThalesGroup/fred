# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The Python SDK against the Knowledge Base pod metrics contract.

The contract is openspec/specs/knowledge-base-pod-metrics/spec.md, shared with
every other SDK implementation. `CONTRACT` below is that spec's tables, written
once more as data: a series renamed, a label added or a value outside a closed
set fails here before a dashboard finds out.
"""

from __future__ import annotations

import ast
import asyncio
import re
import secrets
from pathlib import Path

import httpx
import pytest
from fred_sdk.knowledge_base import KnowledgeBase, telemetry
from fred_sdk.knowledge_base.models import (
    KnowledgeBaseIssue,
    KnowledgeBaseReconciliation,
    KnowledgeBaseRunOutcome,
    KnowledgeBaseSyncResult,
)
from prometheus_client import REGISTRY

IDENTITY = {"service", "knowledge_base"}

OPERATIONS = {
    "control_plane": {"publish", "run_context"},
    "knowledge_flow": {
        "declare_synchronized",
        "publish",
        "task_status",
        "list",
        "retract",
        "source_version_get",
        "source_version_put",
    },
}

# Closed value sets; `status` is checked by pattern instead.
CLOSED = {
    "outcome": {"succeeded", "failed", "cancelled", "error", "interrupted"},
    "reconciliation": {"complete", "partial", "up_to_date", "none"},
    "stage": {"context", "declare", "handler"},
    "change": {"discovered", "created", "updated", "removed", "unchanged"},
    "severity": {"warning", "error"},
    "target": set(OPERATIONS),
    "operation": set().union(*OPERATIONS.values()),
    "state": {"succeeded", "failed", "cancelled", "timeout"},
    "sdk": {"fred-sdk-python"},
}
STATUS = re.compile(r"^([1-5]xx|transport_error|error)$")

# Family name (as the client library reports it) -> type, labels beyond identity.
CONTRACT = {
    "fred_kb_info": ("gauge", {"version", "sdk", "sdk_version"}),
    "fred_kb_runs_in_progress": ("gauge", set()),
    "fred_kb_runs": ("counter", {"outcome", "reconciliation"}),
    "fred_kb_run_duration_seconds": ("histogram", {"outcome"}),
    "fred_kb_last_run_timestamp_seconds": ("gauge", {"outcome"}),
    "fred_kb_run_errors": ("counter", {"stage", "exception_type"}),
    "fred_kb_items": ("counter", {"change"}),
    "fred_kb_issues": ("counter", {"severity", "code"}),
    "fred_kb_requests": ("counter", {"target", "operation", "status"}),
    "fred_kb_request_duration_seconds": ("histogram", {"target", "operation"}),
    "fred_kb_ingestion_wait_seconds": ("histogram", {"state"}),
}

_SOURCES = Path(__file__).resolve().parents[1] / "fred_sdk" / "knowledge_base"


def _measured_operations() -> dict[str, set[str]]:
    """Every operation name the SDK's clients actually pass, read from source.

    Read rather than driven: a call nobody exercises in a test is still a label
    value in production, and this finds it.
    """
    found: dict[str, set[str]] = {target: set() for target in OPERATIONS}
    for module, target, helper in (
        ("client.py", "control_plane", "_request"),
        ("documents.py", "knowledge_flow", "_send"),
    ):
        for node in ast.walk(ast.parse((_SOURCES / module).read_text())):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = getattr(node.func, "attr", getattr(node.func, "id", None))
            if name == helper:
                literal = node.args[0]
            elif name == "observing_request" and len(node.args) == 2:
                literal = node.args[1]
            else:
                continue
            if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
                found[target].add(literal.value)
    return found


def test_the_clients_measure_exactly_the_operations_the_contract_lists():
    assert _measured_operations() == OPERATIONS


@pytest.fixture
def bound(monkeypatch: pytest.MonkeyPatch) -> str:
    definition = KnowledgeBase(
        id=f"acme.kb.c{secrets.token_hex(4)}",
        version="1.0.0",
        name="Contract",
        description="Every series once",
    )
    monkeypatch.setattr(telemetry, "_service", telemetry._UNBOUND)
    monkeypatch.setattr(telemetry, "_knowledge_base", telemetry._UNBOUND)
    telemetry.bind(definition, "contract-kb")
    return definition.id


def _drive_every_path() -> None:
    issue = KnowledgeBaseIssue(code="read_failed", message="m")
    with telemetry.observing_run() as run:
        run.result = KnowledgeBaseSyncResult(
            outcome=KnowledgeBaseRunOutcome.succeeded,
            reconciliation=KnowledgeBaseReconciliation.complete,
            discovered=5,
            created=1,
            updated=1,
            removed=1,
            unchanged=2,
            warnings=[issue],
            errors=[issue],
        )
    with telemetry.observing_run() as run:
        run.result = KnowledgeBaseSyncResult(
            outcome=KnowledgeBaseRunOutcome.succeeded,
            reconciliation=KnowledgeBaseReconciliation.up_to_date,
        )
    for outcome in (KnowledgeBaseRunOutcome.failed, KnowledgeBaseRunOutcome.cancelled):
        with telemetry.observing_run() as run:
            run.result = KnowledgeBaseSyncResult(
                outcome=outcome, reconciliation=KnowledgeBaseReconciliation.partial
            )
    for stage in ("context", "declare", "handler"):
        with pytest.raises(RuntimeError):
            with telemetry.observing_run() as run:
                run.stage = stage
                raise RuntimeError("boom")
    with pytest.raises(asyncio.CancelledError):
        with telemetry.observing_run():
            raise asyncio.CancelledError

    for target, operations in OPERATIONS.items():
        for operation in operations:
            with telemetry.observing_request(target, operation) as answered:
                answered(200)
    with telemetry.observing_request("knowledge_flow", "publish") as answered:
        answered(503)
    with pytest.raises(httpx.ConnectError):
        with telemetry.observing_request("knowledge_flow", "publish"):
            raise httpx.ConnectError("refused")
    with pytest.raises(ValueError):
        with telemetry.observing_request("control_plane", "run_context"):
            raise ValueError("unexpected")

    for state in ("succeeded", "failed", "cancelled", "timeout"):
        telemetry.observe_ingestion_wait(state, 1.0)


def _families(knowledge_base: str) -> dict[str, tuple[str, list[dict[str, str]]]]:
    """This definition's `fred_kb_*` families: type and every sample's labels."""
    families: dict[str, tuple[str, list[dict[str, str]]]] = {}
    for family in REGISTRY.collect():
        if not family.name.startswith("fred_kb_"):
            continue
        samples = [
            {k: v for k, v in sample.labels.items() if k != "le"}
            for sample in family.samples
            if sample.labels.get("knowledge_base") == knowledge_base
        ]
        if samples:
            families[family.name] = (family.type, samples)
    return families


def test_every_series_matches_the_contract(bound):
    _drive_every_path()
    families = _families(bound)

    assert set(families) == set(CONTRACT)
    for name, (kind, samples) in families.items():
        expected_kind, labels = CONTRACT[name]
        assert kind == expected_kind, name
        for sample in samples:
            assert set(sample) == IDENTITY | labels, (name, sample)
            assert sample["service"] == "contract-kb"
            for label, value in sample.items():
                if label in CLOSED:
                    assert value in CLOSED[label], (name, label, value)
                if label == "status":
                    assert STATUS.match(value), (name, value)


def test_every_closed_value_the_paths_reach_is_seen(bound):
    """The drive above is complete: each closed set is reached, not just allowed."""
    _drive_every_path()
    seen: dict[str, set[str]] = {}
    for _, samples in _families(bound).values():
        for sample in samples:
            for label, value in sample.items():
                seen.setdefault(label, set()).add(value)

    for label in (
        "outcome",
        "reconciliation",
        "stage",
        "change",
        "severity",
        "target",
        "state",
    ):
        assert seen[label] == CLOSED[label], label
    assert seen["operation"] == CLOSED["operation"]
    assert {"2xx", "5xx", "transport_error", "error"} <= seen["status"]
