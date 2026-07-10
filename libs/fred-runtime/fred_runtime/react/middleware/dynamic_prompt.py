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

"""DynamicPromptMiddleware — per-turn system-prompt suffix (#1972)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage

from fred_runtime.support.filesystem_context import render_filesystem_browsing_context

from .shared import state_messages


class DynamicPromptMiddleware(AgentMiddleware):
    """
    Per-turn dynamic system-prompt suffix (legacy `_system_builder`).

    Why this exists:
    - the model should not have to remember filesystem browsing continuation
      (current dir, prior `ls` results) across turns; the legacy loop rebuilt
      that suffix from the message state on every model call

    How to use:
    - the static composed system prompt is passed to `create_agent`; this
      middleware appends the per-turn suffix on top of it
    """

    def __init__(self, *, available_tool_names: set[str] | frozenset[str]) -> None:
        super().__init__()
        self._available_tool_names = available_tool_names

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        suffix = render_filesystem_browsing_context(
            state_messages(request.state),
            available_tool_names=self._available_tool_names,
        )
        if suffix:
            base = request.system_prompt or ""
            request = request.override(
                system_message=SystemMessage(content=f"{base}{suffix}")
            )
        return await handler(request)
