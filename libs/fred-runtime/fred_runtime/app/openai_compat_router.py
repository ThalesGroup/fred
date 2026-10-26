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
"""OpenAI metadata surface. Execution is closed until it carries Weaver authority."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fred_core import AssertedUser, KeycloakUser
from fred_sdk.contracts.models import GraphAgentDefinition, ReActAgentDefinition
from fred_sdk.contracts.openai_compat import (
    OpenAIChatRequest,
    OpenAIModelCard,
    OpenAIModelList,
)

logger = logging.getLogger(__name__)


def create_openai_compat_router(
    registry: Mapping[str, ReActAgentDefinition | GraphAgentDefinition],
    security_enabled: bool,
    max_chat_input_chars: int,
    authenticated_user_dep: Callable[..., Any] | None = None,
) -> APIRouter:
    """Expose metadata and authenticate the explicitly unsupported execution route."""
    from fred_core.security.oidc import get_current_user

    def _user_with_auth(
        user: KeycloakUser | AssertedUser = Depends(get_current_user),
    ) -> KeycloakUser | None:
        # This surface admits runs too, so it refuses an asserted person for the
        # same reason the execute routes do: a run needs the person's own token.
        if isinstance(user, AssertedUser):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="requires_own_credential",
            )
        return user

    def _user_noop() -> KeycloakUser | None:
        return None

    user_dep: Callable[..., Any] = authenticated_user_dep or (
        _user_with_auth if security_enabled else _user_noop
    )

    router = APIRouter(tags=["OpenAI Compat"])

    @router.get("/models", response_model=OpenAIModelList)
    async def list_models() -> OpenAIModelList:
        """
        Return registered agents in OpenAI model-list format.

        GET /v1/models
        Response: {"object": "list", "data": [{"id": "<agent_id>", "object": "model"}, ...]}

        Why this endpoint exists:
        - Open WebUI and other OpenAI-compatible frontends call /v1/models to
          populate the model selector; each Fred agent_id appears as a model
        """
        now = int(time.time())
        return OpenAIModelList(
            data=[
                OpenAIModelCard(
                    id=agent_id,
                    created=now,
                )
                for agent_id, definition in registry.items()
                if definition.public
            ]
        )

    @router.post(
        "/chat/completions",
    )
    async def chat_completions(
        request: OpenAIChatRequest,
        http_request: Request,
        authenticated_user: KeycloakUser | None = Depends(user_dep),
    ) -> Response:
        """This direct-template surface has no instance-scoped Weaver context."""
        raise HTTPException(
            status_code=503,
            detail="Direct-template OpenAI execution is not connected to Weaver authorization",
        )

    return router
