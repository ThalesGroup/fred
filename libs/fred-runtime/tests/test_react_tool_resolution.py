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

from __future__ import annotations

import pytest
from fred_core.store import VectorSearchHit
from fred_runtime.react.react_tool_rendering import GENERIC_TOOL_FAILURE_MESSAGE
from fred_runtime.react.react_tool_resolution import ReActRuntimeToolResolver
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    LinkPart,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.runtime import RuntimeServices
from langchain_core.tools import StructuredTool


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(session_id="session-1"),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="user-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


def _resolver() -> ReActRuntimeToolResolver:
    return ReActRuntimeToolResolver(
        declared_tool_refs=(),
        toolset_key=None,
        services=RuntimeServices(),
        binding=_binding(),
    )


def _provider_error_artifact() -> ToolInvocationResult:
    # Synthetic bait, not a credential: this test exists to prove the classifier
    # never lets such a string reach a user-visible artifact.
    secret = (
        "sk-live-PROVIDER-SECRET /srv/private/report.docx"  # pragma: allowlist secret
    )
    return ToolInvocationResult(
        tool_ref="provider.error",
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=secret),),
        sources=(
            VectorSearchHit(
                uid="secret-source",
                title="Private diagnostic",
                content=secret,
                score=1.0,
            ),
        ),
        ui_parts=(LinkPart(href=f"https://provider.invalid/?token={secret}"),),
        is_error=True,
    )


@pytest.mark.asyncio
async def test_runtime_provider_tuple_error_is_sanitized_before_binding() -> None:
    async def _provider_error() -> tuple[str, ToolInvocationResult]:
        return ("safe provider summary", _provider_error_artifact())

    runtime_tool = StructuredTool.from_function(
        coroutine=_provider_error,
        name="provider_error",
        description="Return one provider-controlled error.",
    )
    spec = _resolver()._resolve_runtime_provider_tool(
        runtime_tool=runtime_tool,
        tool_name=runtime_tool.name,
        description=runtime_tool.description,
    )

    content, artifact = await spec.invoke({})

    assert content == f"Tool error:\n{GENERIC_TOOL_FAILURE_MESSAGE}"
    assert artifact is not None
    assert artifact.is_error is True
    assert [block.text for block in artifact.blocks] == [GENERIC_TOOL_FAILURE_MESSAGE]
    assert artifact.sources == ()
    assert artifact.ui_parts == ()


@pytest.mark.asyncio
async def test_runtime_provider_bare_error_is_sanitized_before_binding() -> None:
    async def _provider_error() -> ToolInvocationResult:
        return _provider_error_artifact()

    runtime_tool = StructuredTool.from_function(
        coroutine=_provider_error,
        name="provider_error",
        description="Return one provider-controlled error.",
    )
    spec = _resolver()._resolve_runtime_provider_tool(
        runtime_tool=runtime_tool,
        tool_name=runtime_tool.name,
        description=runtime_tool.description,
    )

    content, artifact = await spec.invoke({})

    assert content == f"Tool error:\n{GENERIC_TOOL_FAILURE_MESSAGE}"
    assert artifact is not None
    assert artifact.is_error is True
    assert [block.text for block in artifact.blocks] == [GENERIC_TOOL_FAILURE_MESSAGE]
    assert artifact.sources == ()
    assert artifact.ui_parts == ()
