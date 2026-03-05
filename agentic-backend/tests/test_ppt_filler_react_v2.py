from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from agentic_backend.agents.v2.production.ppt_filler_react import (
    PptFillerReActV2Definition,
)
from agentic_backend.core.agents.agent_factory import AgentFactory
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2 import (
    BoundRuntimeContext,
    ExecutionConfig,
    PortableContext,
    PortableEnvironment,
    RuntimeServices,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from agentic_backend.core.agents.v2.catalog import definition_to_agent_settings
from agentic_backend.core.agents.v2.react_runtime import (
    ReActInput,
    ReActMessage,
    ReActMessageRole,
    ReActRuntime,
)
from agentic_backend.core.agents.v2.runtime import ChatModelFactoryPort, ToolInvokerPort
from agentic_backend.core.agents.v2.toolset_registry import (
    ToolsetRuntimePorts,
    get_registered_tool_spec,
)
from agentic_backend.integrations.v2_runtime.adapters import CompositeToolInvoker


class ToolFriendlyFakeChatModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # type: ignore[override]
        return self


class StaticChatModelFactory(ChatModelFactoryPort):
    def __init__(self, model: ToolFriendlyFakeChatModel) -> None:
        self.model = model

    def build(self, definition, binding):  # type: ignore[override]
        del definition, binding
        return self.model


class RecordingToolInvoker(ToolInvokerPort):
    def __init__(self) -> None:
        self.calls: list[ToolInvocationRequest] = []

    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        self.calls.append(request)
        return ToolInvocationResult(
            tool_ref=request.tool_ref,
            blocks=(
                ToolContentBlock(
                    kind=ToolContentKind.JSON,
                    data={"ok": True, "tool_ref": request.tool_ref},
                ),
            ),
        )


def _binding(agent_id: str) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id="ppt-session",
            user_id="user-1",
            language="fr-FR",
        ),
        portable_context=PortableContext(
            request_id="req-ppt-session",
            correlation_id="corr-ppt-session",
            actor="user:demo",
            tenant="fred",
            environment=PortableEnvironment.DEV,
            session_id="ppt-session",
            agent_id=agent_id,
        ),
    )


def _user_input(text: str) -> ReActInput:
    return ReActInput(
        messages=(ReActMessage(role=ReActMessageRole.USER, content=text),)
    )


def test_ppt_filler_react_definition_is_declarative() -> None:
    definition = PptFillerReActV2Definition()
    inspection = definition.inspect()

    assert inspection.agent_id == "ppt.filler.react.v2"
    assert inspection.execution_category.value == "react"
    assert definition.toolset_key.startswith("authored.")
    assert definition.fields[0].key == "system_prompt_template"
    assert "extract_enjeux_besoins" in definition.system_prompt_template
    assert [requirement.tool_ref for requirement in definition.tool_requirements] == [
        "ppt.extract_enjeux_besoins",
        "ppt.extract_cv",
        "ppt.extract_prestation_financiere",
        "ppt.fill_template",
    ]


def test_ppt_toolset_registers_typed_tool_specs() -> None:
    definition = PptFillerReActV2Definition()

    enjeux_spec = get_registered_tool_spec(
        toolset_key=definition.toolset_key,
        tool_ref="ppt.extract_enjeux_besoins",
    )
    fill_spec = get_registered_tool_spec(
        toolset_key=definition.toolset_key,
        tool_ref="ppt.fill_template",
    )

    assert enjeux_spec is not None
    assert enjeux_spec.runtime_name == "extract_enjeux_besoins"
    assert fill_spec is not None
    assert fill_spec.runtime_name == "fill_template"


def test_agent_factory_builds_composite_invoker_for_registered_toolset() -> None:
    factory = object.__new__(AgentFactory)
    definition = PptFillerReActV2Definition()
    binding = _binding(definition.agent_id)

    effective_settings = definition_to_agent_settings(
        definition,
        class_path="agentic_backend.agents.v2.production.ppt_filler_react.PptFillerReActV2Definition",
    )
    base_tool_invoker = RecordingToolInvoker()
    invoker = AgentFactory._build_v2_tool_invoker(
        factory,
        definition=definition,
        binding=binding,
        effective_settings=effective_settings,
        base_tool_invoker=base_tool_invoker,
        ports=ToolsetRuntimePorts(
            chat_model_factory=StaticChatModelFactory(
                ToolFriendlyFakeChatModel(responses=[AIMessage(content="ok")])
            ),
            fallback_tool_invoker=base_tool_invoker,
        ),
    )

    assert isinstance(invoker, CompositeToolInvoker)


@pytest.mark.asyncio
async def test_react_runtime_uses_registered_tool_runtime_name_and_payload() -> None:
    base_definition = PptFillerReActV2Definition()
    definition = base_definition.model_copy(
        update={"tool_requirements": base_definition.tool_requirements[:1]}
    )
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-1",
                        "name": "extract_enjeux_besoins",
                        "args": {"context_hint": "Projet Atlas"},
                    }
                ],
            ),
            AIMessage(content="Analyse terminée."),
        ]
    )
    tool_invoker = RecordingToolInvoker()
    runtime = ReActRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=StaticChatModelFactory(model),
            tool_invoker=tool_invoker,
        ),
    )
    runtime.bind(_binding(definition.agent_id))

    executor = await runtime.get_executor()
    output = await executor.invoke(
        _user_input("Lance l'extraction du contexte projet."),
        ExecutionConfig(),
    )
    assert output.final_message.content == "Analyse terminée."

    assert len(tool_invoker.calls) == 1
    assert tool_invoker.calls[0].tool_ref == "ppt.extract_enjeux_besoins"
    assert tool_invoker.calls[0].payload == {"context_hint": "Projet Atlas"}
