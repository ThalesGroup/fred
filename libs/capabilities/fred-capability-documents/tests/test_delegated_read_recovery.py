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

"""Exercise the filename mistake through the real document tool and model loop."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fred_capability_documents.document_verbatim import DocumentVerbatimCapability
from fred_core.security.backend_to_backend_auth import M2MTokenProvider, TokenLease
from fred_core.security.delegation import DelegationConfig
from fred_runtime.capabilities import build_capability_context
from fred_runtime.common.outbound_credentials import DelegationRuntime, RunRecord
from fred_runtime.integrations.v2_runtime.adapters import DocumentMarkdownAdapter
from fred_runtime.react.react_tool_loop import build_tool_loop_compiled_react_agent
from fred_runtime.runtime_context import RuntimeConfig, set_runtime_context
from fred_runtime.runtime_context import RuntimeContext as FredRuntimeContext
from fred_sdk.contracts.capability import CapabilityIdentity
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import (
    AgentTuning,
    MCPServerRef,
    ReActAgentDefinition,
    ReActPolicy,
    ToolApprovalPolicy,
)
from fred_sdk.contracts.runtime import RuntimeServices
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class _Settings:
    id = "reader"
    team_id: str | None = None
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


class _Agent(ReActAgentDefinition):
    role: str = "Document reader"
    description: str = "Read a discovered document"

    def policy(self) -> ReActPolicy:
        return ReActPolicy(system_prompt_template="Read the discovered document.")


class _Model(BaseChatModel):
    """Make the observed mistake, then inspect its actual tool response."""

    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "document-read-recovery-test"

    def bind_tools(self, tools: Any, **kwargs: Any) -> _Model:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        if len(self.calls) == 1:
            uid = "02-technical-requirements.md"
        elif len(self.calls) == 2:
            result = next(m for m in reversed(messages) if isinstance(m, ToolMessage))
            assert result.artifact.is_error
            assert "exact opaque uid" in result.content
            uid = "test-document-uid"
        else:
            result = next(m for m in reversed(messages) if isinstance(m, ToolMessage))
            assert "Authorized source text" in result.content
            return ChatResult(
                generations=[
                    ChatGeneration(message=AIMessage(content="Read verified."))
                ]
            )
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "id": f"read-{len(self.calls)}",
                                "name": "read_document",
                                "args": {"document_uid": uid},
                            }
                        ],
                    )
                )
            ]
        )


@pytest.mark.asyncio
async def test_delegated_read_recovers_in_the_same_model_loop() -> None:
    set_runtime_context(
        FredRuntimeContext(RuntimeConfig(knowledge_flow_url="http://kf.invalid/kf/v1"))
    )
    try:
        tokens = Mock(spec=M2MTokenProvider)
        tokens.get_token_lease = AsyncMock(return_value=TokenLease("synthetic", 1))
        delegation = DelegationRuntime(
            config=DelegationConfig(act_for_people=True), token_provider=tokens
        )
        delegation.records.admit(
            RunRecord(run_id="run-1", person_id="alice", agent_id="reader")
        )
        binding = BoundRuntimeContext(
            runtime_context=RuntimeContext(user_id="alice", session_id="session-1"),
            portable_context=PortableContext(
                request_id="r-1",
                correlation_id="c-1",
                actor="alice",
                tenant="personal",
                environment=PortableEnvironment.DEV,
            ),
        )
        port = DocumentMarkdownAdapter(
            binding=binding,
            settings=_Settings(),
            credentials=delegation.provider_for(run_id="run-1", agent_id="reader"),
        )
        requests: list[httpx.Request] = []

        def receive(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/02-technical-requirements.md"):
                return httpx.Response(
                    403,
                    headers={"X-Fred-Denial-Cause": "permission_refused"},
                    text="private-upstream-body",
                )
            assert request.url.path.endswith("/test-document-uid")
            return httpx.Response(200, json={"content": "Authorized source text"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
            port._client.client = client
            capability = DocumentVerbatimCapability()
            context = build_capability_context(
                capability,
                identity=CapabilityIdentity(user_id="alice", session_id="session-1"),
                services=RuntimeServices(document_markdown=port),
                config={},
            )
            model = _Model()
            compiled = build_tool_loop_compiled_react_agent(
                model=model,
                tools=[],
                system_prompt=(
                    'Discovery returned {"uid":"test-document-uid",'
                    '"name":"02-technical-requirements.md"}. Read that document.'
                ),
                binding=binding,
                approval_policy=ToolApprovalPolicy(enabled=False),
                checkpointer=None,
                definition=_Agent(agent_id="reader"),
                available_tool_names={"read_document"},
                capability_middleware=capability.middleware(context),
            )
            # The builder returns the compiled LangGraph object.
            result = await cast(Any, compiled).ainvoke(
                {
                    "messages": [
                        {"role": "user", "content": "Read the discovered document."}
                    ]
                }
            )
        assert len(model.calls) == 3
        assert len(requests) == 2
        assert result["messages"][-1].content == "Read verified."
        assert "private-upstream-body" not in repr(model.calls)
        assert all(r.url.params["person"] == "alice" for r in requests)
    finally:
        set_runtime_context(None)
