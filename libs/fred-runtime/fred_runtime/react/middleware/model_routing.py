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

"""ModelRoutingMiddleware — per-operation model selection (#1972)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import cast

from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.models import ReActAgentDefinition
from fred_sdk.contracts.runtime import ChatModelFactoryPort
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel

from .shared import state_messages


class ModelRoutingMiddleware(AgentMiddleware):
    """
    Per-operation model selection (legacy `_model_for_state`).

    Why this exists:
    - routed model factories may choose different model configs for `routing`
      (fresh user turn) vs `planning` (tool-driven follow-up) inside one turn
    - the operation is inferred from the RAW state history, and resolved models
      are cached per operation for the lifetime of the compiled agent — both
      exactly as the legacy closure did

    How to use:
    - placed before TracingKpiMiddleware so spans/KPI record the routed model
    """

    def __init__(
        self,
        *,
        chat_model_factory: ChatModelFactoryPort | None,
        definition: ReActAgentDefinition,
        binding: BoundRuntimeContext,
        infer_operation_from_messages: Callable[[Sequence[object]], str],
        default_operation: str,
    ) -> None:
        super().__init__()
        self._chat_model_factory = chat_model_factory
        self._definition = definition
        self._binding = binding
        self._infer_operation_from_messages = infer_operation_from_messages
        self._default_operation = default_operation
        self._models_by_operation: dict[str, BaseChatModel] = {}

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        resolved = self._resolve_model(request)
        if resolved is not None:
            request = request.override(model=resolved)
        return await handler(request)

    def _resolve_model(self, request: ModelRequest) -> BaseChatModel | None:
        messages = state_messages(request.state)
        operation = (
            self._infer_operation_from_messages(messages)
            if messages
            else self._default_operation
        )
        cached = self._models_by_operation.get(operation)
        if cached is not None:
            return cached
        if self._chat_model_factory is None:
            return None
        resolved = self._chat_model_factory.build_for_operation(
            definition=self._definition,
            binding=self._binding,
            purpose="chat",
            operation=operation,
        )
        if resolved is None:
            return None
        model = cast(BaseChatModel, resolved)
        self._models_by_operation[operation] = model
        return model
