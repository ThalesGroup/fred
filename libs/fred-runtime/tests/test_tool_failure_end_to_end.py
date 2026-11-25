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

"""A downstream HTTP 500 is one failure in the live event, the history and the logs.

The 2026-11-10 incident: Knowledge Flow answered `read_document` with a 500 and
the user saw "no further diagnostic". Both producer paths are proven here: a
capability-native tool and a Knowledge Flow MCP tool, whose server answers with
the envelope `mcp_mount._ToolErrorPolicy` emits.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.tools import ToolResult
from fred_core.history.history_schema import (
    ChatMessage,
    FailureOrigin,
    FailureReason,
    ToolResultPart,
)
from fred_runtime.app.agent_app import _event_payload, _write_turn_history
from fred_runtime.common.context_aware_tool import ContextAwareTool
from fred_runtime.common.mcp_utils import (
    MCP_DELEGATED_METADATA_KEY,
    MCP_SERVICE_METADATA_KEY,
)
from fred_runtime.runtime_support.authority import AuthorityLostError
from fred_runtime.runtime_support.tool_execution import describe_failure
from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolFailure,
    ToolFailureCode,
    ToolInvocationResult,
)
from fred_sdk.contracts.models import AgentTuning, MCPServerRef
from fred_sdk.contracts.runtime import (
    HistoryStorePort,
    RuntimeEvent,
    ToolResultRuntimeEvent,
)
from fred_sdk.contracts.services import FredService
from langchain.mcp import MCPAdapter
from langchain_core.tools import BaseTool
from langchain_core.tools import tool as lc_tool
from test_graph_capability_bridge import _binding, _node_context
from weaver_fixtures import in_turn

_SERVICE_ERROR = ToolFailure(code=ToolFailureCode.service_error, status=500)
_DOCUMENT_UID = "doc-canary-uid"


class _AgentSettings:
    id = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


async def _capability_tool() -> BaseTool:
    @lc_tool("read_document", response_format="content_and_artifact")
    async def read_document(document_uid: str) -> tuple[str, ToolInvocationResult]:
        """Read one document."""
        message = f"Could not read {document_uid}: the service returned HTTP 500."
        return message, ToolInvocationResult(
            tool_ref="read_document",
            failure=ToolFailure.from_http_status(500),
            blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
        )

    return read_document


async def _knowledge_flow_mcp_tool(
    envelope: str, service: FredService | None = FredService.KNOWLEDGE_FLOW
) -> BaseTool:
    server = FastMCP("Knowledge Flow")

    @server.tool(name="read_document")
    async def read_document(document_uid: str) -> ToolResult:
        del document_uid
        return ToolResult(content=envelope, is_error=True)

    provider = (await MCPAdapter(Client(server)).list_tools())[0]
    provider.metadata = {
        **(provider.metadata or {}),
        MCP_DELEGATED_METADATA_KEY: True,
        MCP_SERVICE_METADATA_KEY: service,
    }
    return ContextAwareTool(
        base_tool=provider,
        context_provider=lambda: None,
        agent_settings_provider=_AgentSettings,
    )


async def _mcp_500() -> BaseTool:
    return await _knowledge_flow_mcp_tool(
        "Error calling read_document. Status code: 500. Response: {}"
    )


async def _run(tool: BaseTool) -> list[RuntimeEvent]:
    events: list[RuntimeEvent] = []
    ctx = _node_context({tool.name: tool}, events=events)
    await in_turn(
        _binding(),
        ctx.invoke_runtime_tool("read_document", {"document_uid": _DOCUMENT_UID}),
    )
    return events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "build", [_capability_tool, _mcp_500], ids=["capability", "knowledge-flow-mcp"]
)
async def test_a_downstream_500_is_one_failure_in_event_history_and_logs(
    build: Callable[[], Awaitable[BaseTool]], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        events = await _run(await build())

    (event,) = [e for e in events if isinstance(e, ToolResultRuntimeEvent)]
    assert event.failure == _SERVICE_ERROR

    history = AsyncMock(spec=HistoryStorePort)
    history.next_rank.return_value = 0
    await _write_turn_history(
        session_id="session-1",
        user_id="alice",
        request_message="Read the attached file",
        exchange_id="exchange-1",
        payloads=[e.model_dump(mode="json") for e in events],
        history_store=history,
    )
    saved = history.save.call_args.kwargs["messages"]
    reloaded = [ChatMessage.model_validate_json(m.model_dump_json()) for m in saved]
    (part,) = [p for m in reloaded for p in m.parts if isinstance(p, ToolResultPart)]
    assert part.failure == _SERVICE_ERROR

    (warning,) = [
        r for r in caplog.records if r.getMessage() == "Tool invocation failed"
    ]
    assert warning.levelno == logging.WARNING
    # `extra` fields are set on the record at runtime, invisible to the checker.
    assert (
        getattr(warning, "failure_code"),
        getattr(warning, "failure_status"),
    ) == ("service_error", 500)
    # The cause, never the arguments or the tool's text.
    assert _DOCUMENT_UID not in repr(warning.__dict__)
    assert "HTTP 500" not in repr(warning.__dict__)


@pytest.mark.asyncio
async def test_an_mcp_failure_without_the_status_envelope_is_unexpected() -> None:
    events = await _run(await _knowledge_flow_mcp_tool("Tool request failed."))

    (event,) = [e for e in events if isinstance(e, ToolResultRuntimeEvent)]
    assert event.failure == ToolFailure(code=ToolFailureCode.unexpected)


@pytest.mark.asyncio
async def test_a_lost_authority_is_still_read_from_the_refusal_text() -> None:
    # The MCP adapter drops `structured_content` on `isError`: the text is the signal.
    tool = await _knowledge_flow_mcp_tool("Tool access was refused.")
    with pytest.raises(AuthorityLostError):
        await tool.ainvoke({"document_uid": _DOCUMENT_UID})


_REFUSED_KEY_ENVELOPE = (
    "Error calling read_document. Status code: 502. Response: "
    '{"failure": {"code": "misconfigured", "origin": "object_storage", '
    '"setting": "KF_ARTIFACT_ACCESS_KEY"}}'
)


@pytest.mark.asyncio
async def test_knowledge_flow_reported_failure_is_kept_and_told_to_the_model() -> None:
    tool = await _knowledge_flow_mcp_tool(_REFUSED_KEY_ENVELOPE)
    events = await _run(tool)

    (event,) = [e for e in events if isinstance(e, ToolResultRuntimeEvent)]
    assert event.failure == ToolFailure(
        code=ToolFailureCode.misconfigured,
        status=502,
        origin=FailureOrigin.object_storage,
        setting="KF_ARTIFACT_ACCESS_KEY",
    )
    content, _ = await tool._arun(document_uid=_DOCUMENT_UID)
    assert "PLATFORM_MISCONFIGURED" in content
    assert "document storage" in content
    assert "KF_ARTIFACT_ACCESS_KEY" in content


@pytest.mark.asyncio
async def test_another_servers_failure_report_is_ignored() -> None:
    events = await _run(await _knowledge_flow_mcp_tool(_REFUSED_KEY_ENVELOPE, None))

    (event,) = [e for e in events if isinstance(e, ToolResultRuntimeEvent)]
    assert event.failure == ToolFailure(code=ToolFailureCode.service_error, status=502)


@pytest.mark.parametrize("code", list(ToolFailureCode))
def test_every_code_has_a_sentence_in_english_and_french(code: ToolFailureCode) -> None:
    failure = ToolFailure(code=code)
    english = describe_failure(failure, None).message
    french = describe_failure(failure, "fr-FR").message

    assert english and french and english != french
    assert describe_failure(failure, "de").message == english


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        ("en", "The requested document or resource could not be found or read."),
        ("fr", "Le document ou la ressource demandés sont introuvables ou illisibles."),
    ],
)
def test_an_unknown_identifier_claims_no_refusal(language: str, sentence: str) -> None:
    # A folder id given as a document uid is a 404: nothing was refused.
    failure = ToolFailure.from_http_status(404)
    assert describe_failure(failure, language).message == sentence


def test_a_platform_failure_names_its_origin_and_replaces_a_reported_message() -> None:
    reported = ToolFailure(
        code=ToolFailureCode.service_busy,
        origin=FailureOrigin.search_index,
        message="upstream text",
    )

    assert describe_failure(reported, "fr").message == (
        "L'index de recherche est injoignable. C'est un problème de "
        "disponibilité de la plateforme, pas de votre demande : réessayez plus "
        "tard ; si le problème persiste, un administrateur doit vérifier ce "
        "service."
    )


@pytest.mark.parametrize(
    ("language", "sentence"),
    [
        (
            None,
            "The agent gave a file name or another invalid value instead of a "
            "document identifier.",
        ),
        (
            "fr-FR",
            "L'agent a fourni un nom de fichier ou une autre valeur invalide au "
            "lieu d'un identifiant de document.",
        ),
    ],
)
def test_a_reason_makes_the_refusal_precise_and_replaces_a_tool_message(
    language: str | None, sentence: str
) -> None:
    # The tool picks a closed reason; the sentence stays the runtime's own.
    refused = ToolFailure(
        code=ToolFailureCode.invalid_arguments,
        reason=FailureReason.not_a_document_uid,
        message="tool text",
    )
    assert describe_failure(refused, language).message == sentence


def test_a_reason_refines_only_a_refused_call() -> None:
    with pytest.raises(ValueError, match="refines a refused call"):
        ToolFailure(
            code=ToolFailureCode.resource_unavailable,
            reason=FailureReason.not_a_document_uid,
        )


@pytest.mark.asyncio
async def test_the_sentence_reaches_the_live_event_and_survives_the_history() -> None:
    event = ToolResultRuntimeEvent(
        call_id="c1",
        content="Could not read the document: no readable document matches.",
        tool_name="read_document",
        failure=ToolFailure.from_http_status(404),
    )
    payload = _event_payload(event, "fr")
    sentence = "Le document ou la ressource demandés sont introuvables ou illisibles."
    assert payload["failure"]["message"] == sentence
    assert payload["content"] == event.content

    history = AsyncMock(spec=HistoryStorePort)
    history.next_rank.return_value = 0
    await _write_turn_history(
        session_id="session-1",
        user_id="alice",
        request_message="Read the folder",
        exchange_id="exchange-1",
        payloads=[payload],
        history_store=history,
    )
    saved = history.save.call_args.kwargs["messages"]
    reloaded = [ChatMessage.model_validate_json(m.model_dump_json()) for m in saved]
    (part,) = [p for m in reloaded for p in m.parts if isinstance(p, ToolResultPart)]
    assert part.failure == ToolFailure(
        code=ToolFailureCode.resource_unavailable, status=404, message=sentence
    )
