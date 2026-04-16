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
"""
OpenAI-compatible /v1 router for Fred agent pods.

Why this module exists:
- lets any OpenAI-protocol frontend (Open WebUI, openai-python SDK, etc.)
  talk directly to a Fred agent pod without a proxy layer
- mounted only when `app.openai_compat: true` in configuration.yaml
- zero impact on existing /agents/execute* endpoints

How to use:
- this module is called automatically from `create_agent_app()` when the flag
  is set; pod authors do not need to touch it directly
- the router exposes two endpoints:
    GET  /v1/models                — list registered agents as OpenAI models
    POST /v1/chat/completions      — streaming chat completions (SSE)

Fred extensions over the OpenAI protocol:
- X-Fred-Session-Id request header: optional session_id for multi-turn
  continuity via the LangGraph SQL checkpointer
- X-Fred-Team-Id request header: optional team_id for scoped tool/knowledge
  access
- `fred` top-level key on each SSE chunk: carries sources, citations, HITL
  prompts, and error context (silently ignored by standard OpenAI clients)

Example curl:
    curl -N -X POST http://localhost:8000/v1/chat/completions \\
      -H "Content-Type: application/json" \\
      -d '{"model":"my-agent","messages":[{"role":"user","content":"hello"}],"stream":true}'
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Mapping
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from fred_sdk.contracts.models import GraphAgentDefinition, ReActAgentDefinition
from fred_sdk.contracts.openai_compat import (
    OpenAIChatRequest,
    fred_event_to_openai_chunk,
)

from fred_runtime.runtime_context import get_runtime_context

from .agent_app import (
    _AgentExecuteRequest,
    _iterate_runtime_event_payloads,
    _resolve_agent_instance,
)

logger = logging.getLogger(__name__)


def create_openai_compat_router(
    registry: Mapping[str, ReActAgentDefinition | GraphAgentDefinition],
    security_enabled: bool,
) -> APIRouter:
    """
    Build the FastAPI router that exposes the OpenAI chat completions protocol.

    Why this is a factory function:
    - the agent registry is only available at app-creation time, not import time
    - mirrors the pattern used by `_build_agent_router()` in agent_app.py

    How to use:
    - called from `create_agent_app()` and included with prefix="/v1"
    - do not call directly from pod code

    Example:
    - `router = create_openai_compat_router(registry, security_enabled=False)`
    """
    from fred_core.security.oidc import get_current_user

    router = APIRouter(tags=["OpenAI Compat"])
    _auth_deps = [Depends(get_current_user)] if security_enabled else []

    @router.get("/models")
    async def list_models() -> dict[str, Any]:
        """
        Return registered agents in OpenAI model-list format.

        GET /v1/models
        Response: {"object": "list", "data": [{"id": "<agent_id>", "object": "model"}, ...]}

        Why this endpoint exists:
        - Open WebUI and other OpenAI-compatible frontends call /v1/models to
          populate the model selector; each Fred agent_id appears as a model
        """
        now = int(time.time())
        return {
            "object": "list",
            "data": [
                {
                    "id": agent_id,
                    "object": "model",
                    "created": now,
                    "owned_by": "fred",
                }
                for agent_id, definition in registry.items()
                if definition.public
            ],
        }

    @router.post("/chat/completions", dependencies=_auth_deps)
    async def chat_completions(
        request: OpenAIChatRequest, http_request: Request
    ) -> StreamingResponse:
        """
        Execute one agent turn over the OpenAI chat completions SSE protocol.

        POST /v1/chat/completions
        Authorization: Bearer <user JWT> (when security is enabled)
        Body: {"model": "<agent_id>", "messages": [...], "stream": true}
        Response: text/event-stream of chat.completion.chunk JSON objects

        The last user message in `messages` is forwarded to the agent as the
        turn input.  System messages in the request are currently ignored —
        the agent prompt is defined by its pod registration.

        Fred extensions via request headers:
        - X-Fred-Session-Id: session_id for multi-turn continuity
        - X-Fred-Team-Id: team_id for scoped tool and knowledge access

        Fred-specific metadata on each SSE chunk:
        - `fred.sources`: knowledge citations
        - `fred.awaiting_human`: HITL pause payload (finish_reason="stop")
        - `fred.node_error`: graph node error message (finish_reason="stop")
        - `fred.token_usage`: input/output token counts (on the final chunk)
        """
        if request.model not in registry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Unknown model/agent_id: {request.model!r}. "
                    f"Known: {list(registry.keys())}"
                ),
            )

        user_messages = [m for m in request.messages if m.role == "user"]
        if not user_messages:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Request must contain at least one user message.",
            )
        message = user_messages[-1].content

        session_id = http_request.headers.get("X-Fred-Session-Id") or uuid4().hex
        team_id = http_request.headers.get("X-Fred-Team-Id")
        auth = http_request.headers.get("Authorization", "")
        access_token = auth.removeprefix("Bearer ").strip() or None

        context: dict[str, Any] = {"session_id": session_id}
        if team_id:
            context["team_id"] = team_id

        fred_request = _AgentExecuteRequest(
            agent_id=request.model,
            message=message,
            context=context or None,
        )

        target = await _resolve_agent_instance(
            request=fred_request,
            registry=registry,
            access_token=access_token,
            control_plane_url=get_runtime_context().config.control_plane_url,
        )

        completion_id = f"chatcmpl-{uuid4().hex}"
        created = int(time.time())
        model = request.model

        async def openai_stream() -> AsyncIterator[str]:
            try:
                async for event in _iterate_runtime_event_payloads(
                    target.definition,
                    fred_request,
                    access_token=access_token,
                    team_id=target.team_id,
                    registry=registry,
                ):
                    chunk = fred_event_to_openai_chunk(
                        event, completion_id, model, created
                    )
                    if chunk is not None:
                        yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"
            except Exception:
                logger.exception("[openai-compat] streaming error for model=%s", model)
            finally:
                yield "data: [DONE]\n\n"

        return StreamingResponse(openai_stream(), media_type="text/event-stream")

    return router
