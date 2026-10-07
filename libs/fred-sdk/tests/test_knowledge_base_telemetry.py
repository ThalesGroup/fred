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

"""A pod is measured without its author writing a line of it.

What matters most here: every run is counted exactly once whatever way it ends,
a handler that raises is told apart from one that reported failure, no series
carries anything more specific than the pod and its definition, and an author's issue codes
cannot grow the series without bound.
"""

from __future__ import annotations

import asyncio
import secrets
from typing import Any

import httpx
import pytest
from fred_sdk.knowledge_base import KnowledgeBase, telemetry
from fred_sdk.knowledge_base.configuration import PodConfiguration
from fred_sdk.knowledge_base.models import (
    KnowledgeBaseIssue,
    KnowledgeBaseReconciliation,
    KnowledgeBaseRunOutcome,
    KnowledgeBaseSyncResult,
)
from prometheus_client import REGISTRY


# The pod every test is bound as; the definition label alone keeps tests apart.
SERVICE = "acme-kb"


@pytest.fixture
def kb(monkeypatch: pytest.MonkeyPatch) -> str:
    """A definition label of its own, so tests never read each other's counts."""
    name = f"acme.kb.t{secrets.token_hex(4)}"
    monkeypatch.setattr(telemetry, "_service", SERVICE)
    monkeypatch.setattr(telemetry, "_knowledge_base", name)
    return name


def _value(metric: str, **labels: str) -> float:
    """A sample under this pod's `service`, which every series carries."""
    return REGISTRY.get_sample_value(metric, {"service": SERVICE, **labels}) or 0.0


def _result(**fields: Any) -> KnowledgeBaseSyncResult:
    return KnowledgeBaseSyncResult(
        **{
            "outcome": KnowledgeBaseRunOutcome.succeeded,
            "reconciliation": "complete",
            **fields,
        }
    )


def test_a_reported_run_is_counted_with_what_it_did(kb):
    with telemetry.observing_run() as run:
        run.result = _result(
            discovered=10,
            created=2,
            updated=1,
            unchanged=7,
            warnings=[KnowledgeBaseIssue(code="too_large", subject="a.bin")],
        )

    assert (
        _value(
            "fred_kb_runs_total",
            knowledge_base=kb,
            outcome="succeeded",
            reconciliation="complete",
        )
        == 1
    )
    assert _value("fred_kb_items_total", knowledge_base=kb, change="discovered") == 10
    assert _value("fred_kb_items_total", knowledge_base=kb, change="created") == 2
    assert _value("fred_kb_items_total", knowledge_base=kb, change="removed") == 0
    assert (
        _value(
            "fred_kb_issues_total",
            knowledge_base=kb,
            severity="warning",
            code="too_large",
        )
        == 1
    )
    assert (
        _value(
            "fred_kb_run_duration_seconds_count", knowledge_base=kb, outcome="succeeded"
        )
        == 1
    )
    assert _value("fred_kb_runs_in_progress", knowledge_base=kb) == 0
    assert (
        _value(
            "fred_kb_last_run_timestamp_seconds", knowledge_base=kb, outcome="succeeded"
        )
        > 0
    )


def test_a_reported_failure_and_a_partial_pass_are_their_own_series(kb):
    with telemetry.observing_run() as run:
        run.result = _result(
            outcome=KnowledgeBaseRunOutcome.failed,
            reconciliation=KnowledgeBaseReconciliation.partial,
            errors=[KnowledgeBaseIssue(code="source_unavailable")],
        )

    assert (
        _value(
            "fred_kb_runs_total",
            knowledge_base=kb,
            outcome="failed",
            reconciliation="partial",
        )
        == 1
    )
    assert (
        _value(
            "fred_kb_issues_total",
            knowledge_base=kb,
            severity="error",
            code="source_unavailable",
        )
        == 1
    )
    # Reported, not raised: nothing escaped.
    assert (
        _value(
            "fred_kb_run_errors_total",
            knowledge_base=kb,
            stage="handler",
            exception_type="RuntimeError",
        )
        == 0
    )


def test_a_raise_is_counted_once_under_its_stage_and_still_raised(kb):
    with pytest.raises(RuntimeError, match="boom"):
        with telemetry.observing_run() as run:
            run.stage = "handler"
            raise RuntimeError("boom")

    assert (
        _value(
            "fred_kb_runs_total",
            knowledge_base=kb,
            outcome="error",
            reconciliation="none",
        )
        == 1
    )
    assert (
        _value(
            "fred_kb_run_errors_total",
            knowledge_base=kb,
            stage="handler",
            exception_type="RuntimeError",
        )
        == 1
    )
    assert _value("fred_kb_runs_in_progress", knowledge_base=kb) == 0


def test_fred_out_of_reach_before_the_handler_names_that_stage(kb):
    with pytest.raises(httpx.ConnectError):
        with telemetry.observing_run():
            raise httpx.ConnectError("control plane down")

    assert (
        _value(
            "fred_kb_run_errors_total",
            knowledge_base=kb,
            stage="context",
            exception_type="ConnectError",
        )
        == 1
    )


def test_a_stopped_worker_is_an_interruption_not_an_error(kb):
    with pytest.raises(asyncio.CancelledError):
        with telemetry.observing_run() as run:
            run.stage = "handler"
            raise asyncio.CancelledError

    assert (
        _value(
            "fred_kb_runs_total",
            knowledge_base=kb,
            outcome="interrupted",
            reconciliation="none",
        )
        == 1
    )
    assert (
        _value(
            "fred_kb_run_errors_total",
            knowledge_base=kb,
            stage="handler",
            exception_type="CancelledError",
        )
        == 0
    )


def test_issue_codes_past_the_bound_are_counted_as_other(kb, monkeypatch):
    monkeypatch.setattr(telemetry, "MAX_ISSUE_CODES", 1)
    monkeypatch.setattr(telemetry, "_issue_codes", set())

    with telemetry.observing_run() as run:
        run.result = _result(
            warnings=[
                KnowledgeBaseIssue(code="first"),
                KnowledgeBaseIssue(code="second"),
                KnowledgeBaseIssue(code="first"),
            ]
        )

    def issues(code: str) -> float:
        return _value(
            "fred_kb_issues_total", knowledge_base=kb, severity="warning", code=code
        )

    assert (issues("first"), issues("second"), issues("other")) == (2, 0, 1)


def test_no_series_carries_a_team_an_instance_or_a_run(kb):
    """Stream 1 is read by everyone with Grafana; ownership stays inside Fred."""
    with telemetry.observing_run() as run:
        run.result = _result(discovered=1)
    with telemetry.observing_request("knowledge_flow", "list") as answered:
        answered(200)

    forbidden = {"team_id", "instance_id", "library_id", "run_id", "user_id", "subject"}
    for family in REGISTRY.collect():
        if not family.name.startswith("fred_kb_"):
            continue
        for sample in family.samples:
            assert not forbidden & set(sample.labels), (family.name, sample.labels)


def test_a_call_is_counted_by_status_class(kb):
    with telemetry.observing_request("control_plane", "run_context") as answered:
        answered(503)

    assert (
        _value(
            "fred_kb_requests_total",
            knowledge_base=kb,
            target="control_plane",
            operation="run_context",
            status="5xx",
        )
        == 1
    )


def test_a_call_lost_on_the_network_is_a_transport_error(kb):
    with pytest.raises(httpx.ConnectError):
        with telemetry.observing_request("knowledge_flow", "publish"):
            raise httpx.ConnectError("refused")

    assert (
        _value(
            "fred_kb_requests_total",
            knowledge_base=kb,
            target="knowledge_flow",
            operation="publish",
            status="transport_error",
        )
        == 1
    )
    assert (
        _value(
            "fred_kb_request_duration_seconds_count",
            knowledge_base=kb,
            target="knowledge_flow",
            operation="publish",
        )
        == 1
    )


def test_bind_names_the_pod_the_definition_and_the_sdk(monkeypatch):
    monkeypatch.setattr(telemetry, "_service", telemetry._UNBOUND)
    monkeypatch.setattr(telemetry, "_knowledge_base", telemetry._UNBOUND)
    definition = KnowledgeBase(
        id=f"acme.kb.b{secrets.token_hex(4)}",
        version="2.3.0",
        name="Bound",
        description="A definition to bind",
    )

    telemetry.bind(definition, "webdav-kb")

    assert telemetry._service == "webdav-kb"
    assert telemetry._knowledge_base == definition.id
    samples = [
        sample
        for family in REGISTRY.collect()
        if family.name == "fred_kb_info"
        for sample in family.samples
        if sample.labels["knowledge_base"] == definition.id
    ]
    assert [
        (s.labels["service"], s.labels["version"], s.labels["sdk"], s.value)
        for s in samples
    ] == [("webdav-kb", "2.3.0", "fred-sdk-python", 1)]
    assert samples[0].labels["sdk_version"] == telemetry._sdk_version()


def test_without_prometheus_client_nothing_is_measured_and_nothing_breaks(
    monkeypatch,
):
    monkeypatch.setattr(telemetry, "_instruments", None)
    monkeypatch.setattr(telemetry, "_available", False)

    with telemetry.observing_run() as run:
        run.result = _result()
    with telemetry.observing_request("knowledge_flow", "list") as answered:
        answered(200)
    telemetry.observe_ingestion_wait("succeeded", 1.0)

    config = PodConfiguration.model_validate(_pod_payload()).observability
    assert telemetry.start_exporter(config.kpi.prometheus) is False


def _pod_payload(**extra: Any) -> dict[str, Any]:
    return {
        "app": {"runtime_id": "acme-kb"},
        "knowledge_base": {
            "prefix": "acme.kb",
            "control_plane_url": "http://example.invalid/control-plane/v1",
        },
        "security": {
            "m2m": {
                "realm_url": "http://keycloak.invalid/realms/app",
                "client_id": "kb",
                "secret_env_var": "ACME_KB_CLIENT_SECRET",  # pragma: allowlist secret
            }
        },
        **extra,
    }


def test_observability_reads_the_key_path_every_backend_uses():
    configuration = PodConfiguration.model_validate(
        _pod_payload(
            observability={
                "kpi": {"prometheus": {"address": "0.0.0.0", "port": 9100}},
                "temporal": {"prometheus": {"enabled": False}},
            }
        )
    )

    exporter = configuration.observability.kpi.prometheus
    assert (exporter.enabled, exporter.address, exporter.port) == (
        True,
        "0.0.0.0",
        9100,
    )
    assert configuration.observability.temporal.prometheus.enabled is False


def test_both_exporters_default_to_loopback_on_distinct_ports():
    observability = PodConfiguration.model_validate(_pod_payload()).observability

    assert observability.kpi.prometheus.address == "127.0.0.1"
    assert observability.temporal.prometheus.address == "127.0.0.1"
    assert observability.kpi.prometheus.port != observability.temporal.prometheus.port


def test_the_engine_runtime_exports_only_when_enabled():
    from fred_sdk.knowledge_base.worker import build_runtime

    definition = KnowledgeBase(
        id="acme.kb.runtime", version="1.0.0", name="R", description="Runtime"
    )
    disabled = PodConfiguration.model_validate(
        _pod_payload(observability={"temporal": {"prometheus": {"enabled": False}}})
    )

    assert build_runtime(definition, disabled) is None


def test_the_engine_series_carry_the_pod_and_the_definition(monkeypatch):
    from fred_sdk.knowledge_base import worker

    built: dict[str, Any] = {}
    monkeypatch.setattr(worker, "Runtime", lambda **kwargs: built.update(kwargs))
    definition = KnowledgeBase(
        id="acme.kb.runtime", version="1.0.0", name="R", description="Runtime"
    )

    worker.build_runtime(definition, PodConfiguration.model_validate(_pod_payload()))

    assert built["telemetry"].global_tags == {
        "service": "acme-kb",
        "knowledge_base": "acme.kb.runtime",
    }


def _free_port() -> int:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_an_authors_own_series_are_served_beside_the_sdks():
    """No metrics API in the SDK: an author uses the library's default registry."""
    from prometheus_client import Counter
    from prometheus_client.core import REGISTRY as default_registry

    name = f"acme_webdav_shares_scanned_{secrets.token_hex(3)}"
    Counter(name, "Shares an author chose to count.", registry=default_registry).inc()
    port = _free_port()
    config = PodConfiguration.model_validate(
        _pod_payload(observability={"kpi": {"prometheus": {"port": port}}})
    ).observability.kpi.prometheus

    assert telemetry.start_exporter(config) is True
    body = httpx.get(f"http://127.0.0.1:{port}/metrics").text

    assert f"{name}_total 1.0" in body
    assert "fred_kb_info" in body


def test_a_taken_metrics_port_stops_the_pod_naming_it():
    import socket

    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        config = PodConfiguration.model_validate(
            _pod_payload(observability={"kpi": {"prometheus": {"port": port}}})
        ).observability.kpi.prometheus

        with pytest.raises(telemetry.MetricsEndpointUnavailable, match=f":{port}"):
            telemetry.start_exporter(config)
