"""Native child artifacts contribute to the parent without exposing child turns."""

from collections.abc import AsyncIterator, Sequence
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from fred_core.store.vector_search import VectorSearchHit
from fred_runtime.app.agent_app import _write_turn_history
from fred_runtime.react.react_runtime import _TransportBackedReActExecutor
from fred_sdk.contracts.context import (
    LinkKind,
    LinkPart,
    ToolFailure,
    ToolFailureCode,
    ToolInvocationResult,
)
from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_sdk.contracts.runtime import (
    AssistantDeltaRuntimeEvent,
    AwaitingHumanRuntimeEvent,
    ExecutionConfig,
    FinalRuntimeEvent,
    RuntimeServices,
    ToolResultRuntimeEvent,
)
from fred_sdk.contracts.skills import SkillsPort
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from test_platform_skills import binding


def _source(uid: str) -> VectorSearchHit:
    return VectorSearchHit(uid=uid, title=uid, content="evidence", score=0.8)


def _tool_result(
    call_id: str,
    *,
    sources: tuple[VectorSearchHit, ...] = (),
    parts: tuple[LinkPart, ...] = (),
    error: bool = False,
) -> ToolMessage:
    return ToolMessage(
        content="child-private" if error else "result",
        tool_call_id=call_id,
        name="research" if call_id != "parent" else "publish_file",
        status="error" if error else "success",
        artifact=ToolInvocationResult(
            tool_ref="research" if call_id != "parent" else "publish_file",
            sources=sources,
            ui_parts=parts,
            failure=ToolFailure(code=ToolFailureCode.unexpected) if error else None,
        ),
    )


class _ScriptedAgent:
    def __init__(self, events: Sequence[object]) -> None:
        self.events = events
        self.subgraphs: list[bool] = []

    async def astream(self, _: object, **kwargs: Any) -> AsyncIterator[object]:
        self.subgraphs.append(kwargs.get("subgraphs", False))
        for event in self.events:
            yield event


@pytest.mark.asyncio
@pytest.mark.parametrize("skills_enabled", [False, True])
async def test_child_evidence_is_folded_into_parent_final_without_child_events(
    skills_enabled: bool,
) -> None:
    shared_source = _source("shared")
    other_source = _source("other")
    citation = LinkPart(href="https://example.test/source", kind=LinkKind.citation)
    download = LinkPart(href="https://example.test/report", kind=LinkKind.download)
    agent = _ScriptedAgent(
        [
            (("task:first",), "messages", (AIMessageChunk(content="child-secret"), {})),
            (
                ("task:first",),
                "updates",
                {
                    "tools": {
                        "messages": [
                            _tool_result(
                                "child-1", sources=(shared_source,), parts=(citation,)
                            )
                        ]
                    }
                },
            ),
            (
                ("task:second",),
                "updates",
                {
                    "tools": {
                        "messages": [
                            _tool_result(
                                "child-2",
                                sources=(shared_source, other_source),
                                parts=(citation, download),
                                error=True,
                            )
                        ]
                    }
                },
            ),
            (
                ("task:second",),
                "updates",
                {"model": {"messages": [AIMessage(content="child-secret answer")]}},
            ),
            (
                "updates",
                {"tools": {"messages": [_tool_result("parent", parts=(download,))]}},
            ),
            ("updates", {"model": {"messages": [AIMessage(content="parent answer")]}}),
        ]
    )
    executor = _TransportBackedReActExecutor(
        compiled_agent=cast(Any, agent),
        binding=binding(),
        services=RuntimeServices(
            skills=cast(SkillsPort, object()) if skills_enabled else None
        ),
        runtime_class_name="DeepAgentRuntime",
        preload_selected_skill=False,
        collect_subgraph_artifacts=True,
    )
    input_model = ReActInput(
        messages=(ReActMessage(role=ReActMessageRole.USER, content="report"),)
    )

    events = [
        event
        async for event in executor.stream(
            input_model, ExecutionConfig(session_id="child-results")
        )
    ]
    finals = [event for event in events if isinstance(event, FinalRuntimeEvent)]
    assert len(finals) == 1
    final = finals[0]
    assert final.content == "parent answer"
    assert [source.uid for source in final.sources] == ["shared", "other"]
    assert list(final.ui_parts) == [citation, download]
    assert final.model_dump(mode="json")["sources"][0]["uid"] == "shared"
    assert [
        event.call_id for event in events if isinstance(event, ToolResultRuntimeEvent)
    ] == ["parent"]
    assert all(
        "child-secret" not in event.delta
        for event in events
        if isinstance(event, AssistantDeltaRuntimeEvent)
    )
    history = AsyncMock()
    history.next_rank.return_value = 0
    await _write_turn_history(
        session_id="child-results",
        user_id="user",
        request_message=None,
        payloads=[event.model_dump(mode="json") for event in events],
        history_store=history,
    )
    saved = history.save.call_args.kwargs["messages"]
    assert [source.uid for source in saved[-1].metadata.sources] == [
        "shared",
        "other",
    ]
    assert saved[-1].metadata.ui_parts == [
        citation.model_dump(mode="json"),
        download.model_dump(mode="json"),
    ]
    assert agent.subgraphs == [True]


@pytest.mark.asyncio
async def test_child_evidence_survives_human_pause_without_replaying_child() -> None:
    source = _source("before-pause")
    citation = LinkPart(href="https://example.test/source", kind=LinkKind.citation)
    agent = _ScriptedAgent(
        [
            (
                ("task:research",),
                "updates",
                {
                    "tools": {
                        "messages": [
                            _tool_result("child", sources=(source,), parts=(citation,))
                        ]
                    }
                },
            ),
            (
                "updates",
                {
                    "__interrupt__": {
                        "value": {
                            "stage": "agent_question",
                            "question": "Continue?",
                            "free_text": True,
                            "occurrence_id": "question",
                        },
                        "id": "interrupt-1",
                    }
                },
            ),
        ]
    )
    executor = _TransportBackedReActExecutor(
        compiled_agent=cast(Any, agent),
        binding=binding(),
        services=RuntimeServices(),
        runtime_class_name="DeepAgentRuntime",
        collect_subgraph_artifacts=True,
    )
    input_model = ReActInput(
        messages=(ReActMessage(role=ReActMessageRole.USER, content="report"),)
    )
    paused = [
        event
        async for event in executor.stream(
            input_model, ExecutionConfig(session_id="paused-child")
        )
    ]
    pause = next(
        event for event in paused if isinstance(event, AwaitingHumanRuntimeEvent)
    )
    assert pause.sources == (source,)
    assert pause.ui_parts == (citation,)
    assert not any(isinstance(event, FinalRuntimeEvent) for event in paused)

    history = AsyncMock()
    history.next_rank.return_value = 0
    await _write_turn_history(
        session_id="paused-child",
        user_id="user",
        exchange_id="same-exchange",
        request_message="report",
        payloads=[event.model_dump(mode="json") for event in paused],
        history_store=history,
    )
    pause_rows = history.save.call_args.kwargs["messages"]
    pause_metadata = next(
        row
        for row in pause_rows
        if getattr(row.metadata, "extras", {}).get("pause_metadata")
    )
    assert [item.uid for item in pause_metadata.metadata.sources] == ["before-pause"]
    assert pause_metadata.metadata.ui_parts == [citation.model_dump(mode="json")]

    agent.events = [("updates", {"model": {"messages": [AIMessage(content="Done")]}})]
    resumed = [
        event
        async for event in executor.stream(
            input_model,
            ExecutionConfig(
                session_id="paused-child",
                interrupt_id="interrupt-1",
                resume_payload={"choice_id": "proceed"},
            ),
        )
    ]
    final = next(event for event in resumed if isinstance(event, FinalRuntimeEvent))
    assert final.content == "Done"
    assert final.sources == ()
    assert final.ui_parts == ()
    assert not any(isinstance(event, ToolResultRuntimeEvent) for event in resumed)

    history.next_rank.return_value = 3
    await _write_turn_history(
        session_id="paused-child",
        user_id="user",
        exchange_id="same-exchange",
        request_message=None,
        resume_payload={"choice_id": "proceed"},
        payloads=[event.model_dump(mode="json") for event in resumed],
        history_store=history,
    )
    final_rows = history.save.call_args.kwargs["messages"]
    assert final_rows[-1].exchange_id == pause_metadata.exchange_id
    assert not final_rows[-1].metadata.sources
    assert not final_rows[-1].metadata.ui_parts
    assert agent.subgraphs == [True, True]


@pytest.mark.asyncio
async def test_child_artifact_collection_handles_bounded_fanout() -> None:
    events: list[object] = [
        (
            (f"task:{index}",),
            "updates",
            {
                "tools": {
                    "messages": [
                        _tool_result(
                            f"child-{index}", sources=(_source(f"source-{index}"),)
                        )
                    ]
                }
            },
        )
        for index in range(64)
    ]
    events.append(("updates", {"model": {"messages": [AIMessage(content="Done")]}}))
    agent = _ScriptedAgent(events)
    executor = _TransportBackedReActExecutor(
        compiled_agent=cast(Any, agent),
        binding=binding(),
        services=RuntimeServices(),
        runtime_class_name="DeepAgentRuntime",
        collect_subgraph_artifacts=True,
    )
    result = [
        event
        async for event in executor.stream(
            ReActInput(
                messages=(ReActMessage(role=ReActMessageRole.USER, content="x"),)
            ),
            ExecutionConfig(session_id="fanout"),
        )
    ]

    finals = [event for event in result if isinstance(event, FinalRuntimeEvent)]
    assert len(finals) == 1
    assert len(finals[0].sources) == 64
