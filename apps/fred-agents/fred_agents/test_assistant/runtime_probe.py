# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Deterministic checks through privately bound runtime ports."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Literal

from fred_runtime.app import load_agent_pod_config
from fred_sdk import GraphNodeContext, StepResult, typed_node
from fred_sdk.contracts.context import ToolContentKind, ToolInvocationResult
from fred_sdk.contracts.web_research import (
    WebResearchError,
    WebResearchPort,
    WebResearchRequest,
    WebResearchResult,
)
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import column, select, table
from sqlalchemy.sql import quoted_name

from .graph_state import TestState
from .web_probes import BYPASS_PROBES, ProbeReport, run_probes


class ProbeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["retrieval", "expiry", "web", "tabular"]
    query: str = Field(
        default="runtime diagnostic fixture", min_length=1, max_length=256
    )
    marker: str = Field(default="", max_length=256)
    hold_seconds: int = Field(default=0, ge=0, le=900)


def _tabular_payload(raw: object, tool_name: str) -> object:
    result = ToolInvocationResult.model_validate(raw)
    if result.tool_ref != tool_name or result.is_error:
        raise RuntimeError("tabular tool failed")
    blocks = [block for block in result.blocks if block.kind == ToolContentKind.JSON]
    if len(blocks) != 1 or blocks[0].data is None:
        raise RuntimeError("invalid tabular tool response")
    payload = blocks[0].data
    return payload["result"] if set(payload) == {"result"} else payload


async def _tabular_call(
    context: GraphNodeContext, name: str, values: dict[str, object]
) -> object:
    provider = context.services.tool_provider
    tools = provider.get_tools() if provider else ()
    tool = next(
        (tool for tool in tools if isinstance(tool, BaseTool) and tool.name == name),
        None,
    )
    if tool is None:
        raise RuntimeError("required tabular tool unavailable")
    properties = tool.args
    arguments: dict[str, object] = values
    if not set(values).issubset(properties):
        if len(properties) != 1:
            raise RuntimeError("unsupported tabular tool contract")
        arguments = {next(iter(properties)): values}
    return _tabular_payload(await context.invoke_runtime_tool(name, arguments), name)


class _ProbeToolsUnavailable(RuntimeError):
    pass


class _ApprovedWebTools(WebResearchPort):
    def __init__(self, context: GraphNodeContext) -> None:
        self.context = context

    async def check_ready(self) -> None:
        return None

    async def execute(self, request: WebResearchRequest) -> WebResearchResult:
        try:
            type(request).model_validate(request.model_dump())
        except ValueError:
            raise WebResearchError("rejected") from None
        try:
            raw = await self.context.invoke_runtime_tool(
                request.operation,
                request.model_dump(exclude={"operation"}),
            )
        except RuntimeError:
            raise _ProbeToolsUnavailable(
                "Approved web tools are unavailable."
            ) from None
        result = ToolInvocationResult.model_validate(raw)
        text = "\n".join(
            block.text
            for block in result.blocks
            if block.kind == ToolContentKind.TEXT and block.text
        )
        try:
            data = json.loads(text)
        except ValueError:
            raise RuntimeError("invalid approved web tool response") from None
        if result.is_error:
            if not isinstance(data, dict) or not data.get("error_code"):
                raise _ProbeToolsUnavailable("The web tool was not approved.")
            raise WebResearchError(str(data["error_code"]))
        return WebResearchResult.model_validate(data)


def _unsupported_engine_probe(report: ProbeReport) -> None:
    if report.id in {probe[0] for probe in BYPASS_PROBES}:
        report.verdict = "skipped"
        report.observed = "tool schema enforced"
        report.detail = "Engine-only bypass probes are unavailable through approved capability tools."


@typed_node(TestState)
async def runtime_probe_step(state: TestState, context: GraphNodeContext) -> StepResult:
    request = ProbeInput.model_validate_json(state.latest_user_text.split(" ", 2)[2])
    result: dict[str, object] = {"mode": request.mode}
    if request.mode == "tabular":
        selected = context.binding.runtime_context.selected_document_uids
        if not selected or len(selected) != 1 or not request.marker:
            raise ValueError("one selected fixture and an expected marker are required")
        uid = selected[0]
        inventory = await _tabular_call(context, "list_tabular_documents", {})
        if (
            not isinstance(inventory, list)
            or len(inventory) != 1
            or not isinstance(inventory[0], dict)
            or inventory[0].get("document_uid") != uid
        ):
            raise RuntimeError("tabular inventory scope mismatch")
        descriptions = await _tabular_call(
            context, "describe_tabular_documents", {"document_uids": [uid]}
        )
        if not isinstance(descriptions, list) or len(descriptions) != 1:
            raise RuntimeError("invalid tabular fixture description")
        description = descriptions[0]
        if not isinstance(description, dict) or description.get("document_uid") != uid:
            raise RuntimeError("tabular fixture description scope mismatch")
        tables = description.get("tables")
        if (
            not isinstance(tables, list)
            or len(tables) != 1
            or not isinstance(tables[0], dict)
        ):
            raise RuntimeError("one fixture table is required")
        alias = tables[0].get("query_alias")
        if not isinstance(alias, str) or not alias or len(alias) > 256:
            raise RuntimeError("invalid tabular fixture alias")
        statement = (
            select(column("label"))
            .select_from(table(quoted_name(alias, True)))
            .where(column("code") == 1)
        )
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        output = await _tabular_call(
            context,
            "query_tabular_documents",
            {
                "sql": sql,
                "dataset_uids": [uid],
                "max_rows": 10,
            },
        )
        if not isinstance(output, dict) or output.get("error"):
            raise RuntimeError("tabular fixture query failed")
        if output.get("dataset_uids") != [uid] or output.get("query_aliases") != [
            alias
        ]:
            raise RuntimeError("tabular fixture query scope mismatch")
        rows = output.get("rows")
        if not isinstance(rows, list) or len(rows) > 10:
            raise RuntimeError("invalid tabular fixture rows")
        result["tabular"] = any(
            isinstance(row, dict) and row.get("label") == request.marker for row in rows
        )
    elif request.mode == "web":
        try:
            probes = await run_probes(
                _ApprovedWebTools(context), _unsupported_engine_probe
            )
        except _ProbeToolsUnavailable:
            return StepResult(
                state_update={
                    "final_text": 'RUNTIME-PROBE {"mode":"web","unavailable":true,"enabled":false,"ready":false,"reason":null,"probes":[]}',
                    "done_reason": "runtime_probe_unavailable",
                }
            )
        result["enabled"] = True
        result["ready"] = True
        result["reason"] = None
        result["probes"] = [probe.model_dump() for probe in probes]
        result["search_live"] = (
            load_agent_pod_config().web_research.provider != "fixture"
        )
    else:

        async def search() -> bool:
            found = ToolInvocationResult.model_validate(
                await context.invoke_runtime_tool(
                    "search_documents", {"question": request.query, "top_k": 8}
                )
            )
            if found.is_error:
                raise RuntimeError("The approved document search failed.")
            return (
                any(request.marker in hit.content for hit in found.sources)
                if request.marker
                else bool(found.sources)
            )

        result["before"] = await search()
        result["before_at"] = time.time()
        if result["before"]:
            context.emit_status("runtime_probe_baseline", "Protected search completed.")
        if request.mode == "expiry":
            if not request.hold_seconds:
                raise ValueError("positive hold required")
            await asyncio.sleep(request.hold_seconds)
            result["after_at"] = time.time()
            result["after"] = await search()
            if result["after"]:
                context.emit_status(
                    "runtime_probe_after", "Protected search completed after the wait."
                )
    return StepResult(
        state_update={
            "final_text": "RUNTIME-PROBE " + json.dumps(result),
            "done_reason": "runtime_probe_complete",
        }
    )
