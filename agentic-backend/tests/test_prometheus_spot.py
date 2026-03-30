from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage, HumanMessage

from agentic_backend.agents.v1.production.prometheus.prometheus_expert import Spot
from agentic_backend.common.structures import AgentSettings


def test_spot_prefetches_full_metric_inventory_before_reasoning(
    monkeypatch,
) -> None:
    agent = Spot(agent_settings=AgentSettings(id="Spot", name="Spot"))
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_call_tool(tool_name: str, payload: dict[str, object] | None = None):
        calls.append((tool_name, payload or {}))
        if tool_name == "prometheus_metrics":
            return {
                "status": "success",
                "data": [
                    "container_cpu_usage_seconds_total",
                    "container_memory_working_set_bytes",
                ],
            }
        raise AssertionError(f"Unexpected tool call: {tool_name}")

    monkeypatch.setattr(agent, "_call_tool", fake_call_tool)

    state = {
        "messages": [HumanMessage(content="Peux-tu investiguer la CPU du cluster ?")]
    }

    context = asyncio.run(agent._ensure_prometheus_context(state))

    assert calls == [("prometheus_metrics", {"limit": 5000})]
    assert context["metrics"]["data"] == [
        "container_cpu_usage_seconds_total",
        "container_memory_working_set_bytes",
    ]
    assert list(context) == ["metrics"]


def test_spot_keeps_full_metric_inventory_out_of_prompt() -> None:
    agent = Spot(agent_settings=AgentSettings(id="Spot", name="Spot"))

    prompt_context = agent._format_context_for_prompt(
        {
            "metrics": {
                "data": [
                    "container_cpu_usage_seconds_total",
                    "container_memory_working_set_bytes",
                    "container_fs_usage_bytes",
                    "kube_pod_info",
                    "kube_node_status_condition",
                    "node_cpu_seconds_total",
                ]
            }
        }
    )

    assert (
        "Full metric inventory preloaded outside the prompt: 6 exact metric names."
        in prompt_context
    )
    assert (
        "The raw inventory is intentionally hidden to avoid polluting the LLM context."
        in prompt_context
    )
    assert (
        "Use prometheus_metrics(search=...) to inspect only the relevant subset"
        in prompt_context
    )
    assert "container_memory_working_set_bytes" not in prompt_context
    assert "kube_node_status_condition" not in prompt_context


def test_spot_rejects_fuzzy_metric_name_in_metadata_tool_call() -> None:
    agent = Spot(agent_settings=AgentSettings(id="Spot", name="Spot"))
    state = {
        "prometheus_context": {
            "metrics": {
                "data": [
                    "ingestion_document_duration_ms_bucket",
                    "ingestion_document_duration_ms_count",
                    "ingestion_document_duration_ms_sum",
                ]
            }
        },
        "messages": [],
    }
    response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "prometheus_metadata",
                "args": {"metric": "ingestion"},
                "id": "call-1",
            }
        ],
    )

    issue = agent._invalid_metric_usage_instruction(response, state)

    assert issue is not None
    assert "'ingestion' is not an exact metric name." in issue
    assert "ingestion_document_duration_ms_count" in issue


def test_spot_rejects_promql_without_exact_metric_name() -> None:
    agent = Spot(agent_settings=AgentSettings(id="Spot", name="Spot"))
    state = {
        "prometheus_context": {
            "metrics": {
                "data": [
                    "ingestion_document_duration_ms_count",
                    "ingestion_document_duration_ms_sum",
                ]
            }
        },
        "messages": [],
    }
    response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "prometheus_query",
                "args": {"query": "rate(ingestion[5m])"},
                "id": "call-1",
            }
        ],
    )

    issue = agent._invalid_metric_usage_instruction(response, state)

    assert issue is not None
    assert "does not reference any exact metric name from the inventory" in issue
