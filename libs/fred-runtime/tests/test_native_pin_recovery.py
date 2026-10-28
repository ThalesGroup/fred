# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Real native context recovery observes physical skill pins exactly once."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fred_core.kpi import BaseKPIWriter
from fred_runtime.skills.catalog import PlatformSkills
from fred_sdk.contracts.runtime import StatusRuntimeEvent
from langchain_core.exceptions import ContextOverflowError
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Overwrite
from test_platform_skills import Model, binding, compiled
from test_skill_eligibility import publish


@pytest.mark.asyncio
@pytest.mark.parametrize("names", [("example",), ("first", "second")])
async def test_native_overflow_recovery_observes_each_physical_pin_once(
    tmp_path: Path, names: tuple[str, ...]
) -> None:
    for name in names:
        publish(tmp_path, name)
    skills = PlatformSkills.from_directory(str(tmp_path))
    physical = AsyncMock(wraps=skills.filesystem_backend.adownload_files)
    skills.filesystem_backend.adownload_files = physical
    kpi = Mock(spec=BaseKPIWriter)

    class OverflowModel(Model):
        def _generate(
            self,
            messages: list[BaseMessage],
            stop: list[str] | None = None,
            run_manager: Any = None,
            **kwargs: Any,
        ) -> ChatResult:
            self.calls.append(list(messages))
            if len(self.calls) == 1:
                # Every pin must already be visible before the first inference.
                assert len(physical.call_args_list) == 1
                assert len(
                    [
                        call
                        for call in kpi.count.call_args_list
                        if call.args[0] == "agent.skill_loaded_total"
                    ]
                ) == len(names)
                raise ContextOverflowError("synthetic context overflow")
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="Recovered"))]
            )

    model = OverflowModel()
    graph = compiled(model, skills, binding(), True, kpi=kpi)
    messages: list[BaseMessage] = []
    for index in range(10):
        messages.extend(
            [
                HumanMessage(content=f"Previous question {index}: " + "x " * 300),
                AIMessage(content=f"Previous answer {index}: " + "x " * 300),
            ]
        )
    messages.append(HumanMessage(content="Apply the selected procedures"))
    config = {"configurable": {"thread_id": "native-pin-recovery"}}
    events = [
        event
        async for event in graph.astream(
            {"messages": messages, "pinned_skills": list(names)},
            config,
            stream_mode=["updates", "custom"],
        )
    ]

    # The failed inference, native summarization and recovered inference all use
    # the actual compiled Deep path. Recovery must not redownload the bodies.
    assert len(model.calls) == 3
    physical.assert_awaited_once_with([f"/{name}/SKILL.md" for name in names])
    loads = [
        payload.skill_load
        for mode, payload in events
        if mode == "custom"
        and isinstance(payload, StatusRuntimeEvent)
        and payload.skill_load
    ]
    assert [load.name for load in loads] == list(names)
    counts = [
        call
        for call in kpi.count.call_args_list
        if call.args[0] == "agent.skill_loaded_total"
    ]
    assert [call.kwargs["dims"]["skill_name"] for call in counts] == list(names)
    for inference in (model.calls[0], model.calls[-1]):
        assert [
            message.additional_kwargs["skill"]["name"]
            for message in inference
            if message.additional_kwargs.get("lc_source") == "pinned_skill"
        ] == list(names)
    state = await graph.aget_state(config)
    assert state.values["fred_pending_skill_names"] == []
    assert state.values["fred_observed_pin_ids"] == []
    pins = [
        message
        for message in state.values["messages"]
        if message.additional_kwargs.get("lc_source") == "pinned_skill"
    ]
    assert len(pins) == len(names)
    assert all(message.additional_kwargs["fred_skill_observed"] for message in pins)

    # Selecting the same name again is a genuinely new native pin/read, even in
    # the same thread after its earlier model invocation recovered.
    later = [
        payload.skill_load
        async for mode, payload in graph.astream(
            {
                "messages": [HumanMessage(content="Apply the procedure again")],
                "pinned_skills": [names[-1]],
            },
            config,
            stream_mode=["updates", "custom"],
        )
        if mode == "custom"
        and isinstance(payload, StatusRuntimeEvent)
        and payload.skill_load
    ]
    assert len(later) == 1 and later[0].name == names[-1]
    assert later[0].load_id not in {load.load_id for load in loads}
    assert physical.await_count == 2


@pytest.mark.asyncio
async def test_failed_model_keeps_transient_observation_out_of_checkpoint(
    tmp_path: Path,
) -> None:
    publish(tmp_path, "example")
    skills = PlatformSkills.from_directory(str(tmp_path))
    physical = AsyncMock(wraps=skills.filesystem_backend.adownload_files)
    skills.filesystem_backend.adownload_files = physical
    kpi = Mock(spec=BaseKPIWriter)
    saver = InMemorySaver()

    class FailedModel(Model):
        def _generate(
            self,
            messages: list[BaseMessage],
            stop: list[str] | None = None,
            run_manager: Any = None,
            **kwargs: Any,
        ) -> ChatResult:
            self.calls.append(list(messages))
            raise RuntimeError("synthetic provider failure")

    graph = compiled(
        FailedModel(), skills, binding(), True, checkpointer=saver, kpi=kpi
    )
    config = {"configurable": {"thread_id": "failed-native-pin"}}
    events: list[object] = []
    with pytest.raises(RuntimeError, match="synthetic provider failure"):
        async for mode, payload in graph.astream(
            {
                "messages": [HumanMessage(content="Use the procedure")],
                "pinned_skills": ["example"],
            },
            config,
            stream_mode=["updates", "custom"],
        ):
            if mode == "custom" and isinstance(payload, StatusRuntimeEvent):
                events.append(payload)
    assert len(events) == 1
    physical.assert_awaited_once_with(["/example/SKILL.md"])
    state = await graph.aget_state(config)
    pins = [
        message
        for message in state.values["messages"]
        if message.additional_kwargs.get("lc_source") == "pinned_skill"
    ]
    assert len(pins) == 1
    # Native before_model committed the actual pin. The failed model node did
    # not commit its Command or its invocation-local observation identities.
    assert not pins[0].additional_kwargs.get("fred_skill_observed")
    assert state.values["fred_observed_pin_ids"] == []
    assert state.values["pinned_skills"] == []

    physical.reset_mock()
    continued = compiled(Model(), skills, binding(), True, checkpointer=saver, kpi=kpi)
    later = [
        payload
        async for mode, payload in continued.astream(
            {
                "messages": [HumanMessage(content="Continue")],
                "pinned_skills": Overwrite([]),
            },
            config,
            stream_mode=["updates", "custom"],
        )
        if mode == "custom" and isinstance(payload, StatusRuntimeEvent)
    ]
    assert later == []
    physical.assert_not_awaited()
    assert (
        len(
            [
                call
                for call in kpi.count.call_args_list
                if call.args[0] == "agent.skill_loaded_total"
            ]
        )
        == 1
    )
