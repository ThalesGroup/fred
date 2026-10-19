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

"""Transient path-only context for one user exchange, never file bodies."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage

from fred_runtime.conversation_changes import ChangePublication

_MAX_PATHS = 10
_MAX_CHARACTERS = 2048


class ExternalChangesMiddleware(AgentMiddleware):
    def __init__(self, publication: ChangePublication, exchange_id: str) -> None:
        self._notification = _notification(publication, exchange_id)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        if self._notification:
            request = request.override(
                system_message=SystemMessage(
                    content=f"{request.system_prompt or ''}\n\n{self._notification}"
                )
            )
        return await handler(request)


def _notification(publication: ChangePublication, exchange_id: str) -> str:
    if not publication.file_count:
        return ""
    directory = f"/.deep/changes/{exchange_id}/"

    def render(paths: list[str], *, truncated: bool) -> str:
        data: dict[str, object] = {"files": publication.file_count, "diff_paths": paths}
        if truncated:
            data.update(truncated=True, directory=directory)
        return "External file changes: " + json.dumps(data, ensure_ascii=True)

    selected: list[str] = []
    for path in publication.paths[:_MAX_PATHS]:
        candidate = [*selected, path]
        if len(render(candidate, truncated=True)) > _MAX_CHARACTERS:
            break
        selected = candidate
    return render(selected, truncated=len(selected) < len(publication.paths))
