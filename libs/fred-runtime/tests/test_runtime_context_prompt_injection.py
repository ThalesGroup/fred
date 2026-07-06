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
"""Runtime-level regression tests for issue #1915.

The composer unit tests (``test_react_prompting.py``) prove that
``compose_system_prompt`` folds ``context_prompt_text`` into the prompt. These
tests close the remaining gap: that each *runtime* actually hands a final
``system_prompt`` containing that text to the compiled agent it builds.

They drive ``build_executor`` for both ReAct and Deep and capture the
``system_prompt`` passed into the (stubbed) compile step, so the compiled-agent
call is observed directly without pulling in the real model/tool machinery. The
tool pipeline, the executor, and the compile call are stubbed; nothing about the
runtime's own prompt assembly is patched.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import ReActAgentDefinition
from fred_sdk.contracts.runtime import RuntimeServices
from langchain_core.language_models.chat_models import BaseChatModel

import fred_runtime.deep.deep_runtime as deep_mod
import fred_runtime.react.react_runtime as react_mod

_CTX_MARKER = "CTXPROMPT-always-respond-in-spanish"


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(context_prompt_text=_CTX_MARKER),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="user-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


class _FakePolicy:
    """Just the policy surface ``build_executor`` reads for prompt assembly."""

    def __init__(self) -> None:
        self.system_prompt_template = "BASE-TEMPLATE"
        self.guardrails: list[object] = []
        self.tool_approval = SimpleNamespace(enabled=False)
        self.tool_selection = SimpleNamespace(
            max_tool_calls_per_turn=None, allow_parallel_calls=False
        )


class _FakeDefinition:
    agent_id = "agent-1"
    declared_tool_refs: tuple[object, ...] = ()
    tuning_values: dict[str, str] = {}

    def policy(self) -> _FakePolicy:
        return _FakePolicy()


class _FakeResolver:
    def __init__(self, **_: object) -> None:
        pass

    def resolve_tools(self) -> list[object]:
        return []


class _FakeBinder:
    def __init__(self, **_: object) -> None:
        pass

    def build_tools(self) -> list[object]:
        return []


class _FakeExecutor:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


def _stub_tool_pipeline(monkeypatch: pytest.MonkeyPatch, module: object) -> None:
    # Replace only the collaborators around prompt assembly, never the assembly
    # itself, so the captured system_prompt is the runtime's genuine output.
    monkeypatch.setattr(module, "ReActRuntimeToolResolver", _FakeResolver)
    monkeypatch.setattr(module, "ReActToolBinder", _FakeBinder)
    monkeypatch.setattr(module, "_TransportBackedReActExecutor", _FakeExecutor)


def _fake_definition() -> ReActAgentDefinition:
    return cast(ReActAgentDefinition, _FakeDefinition())


@pytest.mark.asyncio
async def test_react_build_executor_injects_context_prompt_into_compiled_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def _fake_compile(**kwargs: object) -> object:
        captured["system_prompt"] = str(kwargs["system_prompt"])
        return object()

    _stub_tool_pipeline(monkeypatch, react_mod)
    monkeypatch.setattr(react_mod, "_create_compiled_react_agent", _fake_compile)

    runtime = react_mod.ReActRuntime(
        definition=_fake_definition(), services=RuntimeServices()
    )
    runtime._model = cast(BaseChatModel, SimpleNamespace())

    await runtime.build_executor(_binding())

    # #1915: the selected chat-context prompt must reach the compiled agent, not
    # just the agent binding.
    assert _CTX_MARKER in captured["system_prompt"]
    assert captured["system_prompt"].startswith("BASE-TEMPLATE")


@pytest.mark.asyncio
async def test_deep_build_executor_injects_context_prompt_into_compiled_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def _fake_compile(**kwargs: object) -> object:
        captured["system_prompt"] = str(kwargs["system_prompt"])
        return object()

    _stub_tool_pipeline(monkeypatch, deep_mod)
    monkeypatch.setattr(deep_mod, "_create_compiled_deep_agent", _fake_compile)

    runtime = deep_mod.DeepAgentRuntime(
        definition=_fake_definition(), services=RuntimeServices()
    )
    runtime._model = cast(BaseChatModel, SimpleNamespace())

    await runtime.build_executor(_binding())

    # The Deep runtime shares the canonical composer, so the same guarantee holds.
    assert _CTX_MARKER in captured["system_prompt"]
    assert captured["system_prompt"].startswith("BASE-TEMPLATE")
