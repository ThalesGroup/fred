# Copyright Thales 2025
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

import logging
from typing import List, Literal, Union

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fred_core import (
    KeycloakUser,
    RBACProvider,
    UserSecurity,
    VectorSearchHit,
    decode_jwt,
    get_current_user,
)
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketState

from app.application_context import get_configuration
from app.common.structures import AgentSettings, FrontendSettings
from app.common.utils import log_exception
from app.core.agents.agent_manager import AgentManager
from app.core.agents.runtime_context import RuntimeContext
from app.core.chatbot.chat_schema import (
    ChatAskInput,
    ChatMessage,
    ErrorEvent,
    FinalEvent,
    SessionSchema,
    SessionWithFiles,
    StreamEvent,
)
from app.core.chatbot.metric_structures import MetricsBucket, MetricsResponse
from app.core.chatbot.session_orchestrator import SessionOrchestrator

logger = logging.getLogger(__name__)

# ---------------- Echo types for UI OpenAPI ----------------

EchoPayload = Union[
    ChatMessage,
    ChatAskInput,
    StreamEvent,
    FinalEvent,
    ErrorEvent,
    SessionSchema,
    SessionWithFiles,
    MetricsResponse,
    MetricsBucket,
    VectorSearchHit,
    RuntimeContext,
]


class EchoEnvelope(BaseModel):
    kind: Literal[
        "ChatMessage",
        "StreamEvent",
        "FinalEvent",
        "ErrorEvent",
        "SessionSchema",
        "SessionWithFiles",
        "MetricsResponse",
        "MetricsBucket",
        "VectorSearchHit",
        "RuntimeContext",
    ]
    payload: EchoPayload = Field(..., description="Schema payload being echoed")


class FrontendConfigDTO(BaseModel):
    frontend_settings: FrontendSettings
    user_auth: UserSecurity


def get_agent_manager(request: Request) -> AgentManager:
    """Dependency to get the agent_manager from app.state."""
    return request.app.state.agent_manager


def get_session_orchestrator(request: Request) -> SessionOrchestrator:
    """Dependency to get the session_orchestrator from app.state."""
    return request.app.state.session_orchestrator


def get_agent_manager_ws(websocket: WebSocket) -> AgentManager:
    """Dependency to get the agent_manager from app.state for WebSocket."""
    return websocket.app.state.agent_manager


def get_session_orchestrator_ws(websocket: WebSocket) -> SessionOrchestrator:
    """Dependency to get the session_orchestrator from app.state for WebSocket."""
    return websocket.app.state.session_orchestrator


# Create a RBAC provider object to retrieve user permissions in the config/permissions route
rbac_provider = RBACProvider()

# Create an APIRouter instance here
router = APIRouter(tags=["Frontend"])


@router.post(
    "/schemas/echo",
    tags=["Schemas"],
    summary="Ignore. Not a real endpoint.",
    description="Ignore. This endpoint is only used to include some types (mainly one used in websocket) in the OpenAPI spec, so they can be generated as typescript types for the UI. This endpoint is not really used, this is just a code generation hack.",
)
def echo_schema(envelope: EchoEnvelope) -> None:
    pass


@router.get(
    "/config/frontend_settings",
    summary="Get the frontend dynamic configuration",
)
def get_frontend_config() -> FrontendConfigDTO:
    cfg = get_configuration()
    return FrontendConfigDTO(
        frontend_settings=cfg.frontend_settings,
        user_auth=UserSecurity(
            enabled=cfg.security.user.enabled,
            realm_url=cfg.security.user.realm_url,
            client_id=cfg.security.user.client_id,
        ),
    )


@router.get(
    "/config/permissions",
    summary="Get the current user's permissions",
    response_model=list[str],
)
def get_user_permissions(
    current_user: KeycloakUser = Depends(get_current_user),
) -> list[str]:
    """
    Return a flat list of 'resource:action' strings the user is allowed to perform.:
    """
    return rbac_provider.list_permissions_for_user(current_user)


@router.get(
    "/chatbot/agenticflows",
    description="Get the list of available agentic flows",
    summary="Get the list of available agentic flows",
)
def get_agentic_flows(
    user: KeycloakUser = Depends(get_current_user),
    agent_manager: AgentManager = Depends(get_agent_manager),  # Inject the dependency
) -> List[AgentSettings]:
    return agent_manager.get_agentic_flows()


@router.websocket("/chatbot/query/ws")
async def websocket_chatbot_question(
    websocket: WebSocket,
    agent_manager: AgentManager = Depends(
        get_agent_manager_ws
    ),  # Use WebSocket-specific dependency
    session_orchestrator: SessionOrchestrator = Depends(
        get_session_orchestrator_ws
    ),  # Use WebSocket-specific dependency
):
    """
    Transport-only:
      - Accept WS
      - Parse ChatAskInput
      - Provide a callback that forwards StreamEvents
      - Send FinalEvent or ErrorEvent
      - All heavy lifting is in SessionOrchestrator.chat_ask_websocket()
    """
    # All other code is the same, but it now uses the injected dependencies
    # `agent_manager` and `session_orchestrator` which are guaranteed to be
    # the correct, lifespan-managed instances.
    await websocket.accept()
    auth = websocket.headers.get("authorization") or ""
    token = (
        auth.split(" ", 1)[1]
        if auth.lower().startswith("bearer ")
        else websocket.query_params.get("token")
    )
    if not token:
        await websocket.close(code=4401)
        return

    try:
        user = decode_jwt(token)
    except HTTPException:
        await websocket.close(code=4401)
        return

    try:
        while True:
            client_request = None
            try:
                client_request = await websocket.receive_json()
                ask = ChatAskInput(**client_request)

                async def ws_callback(msg_dict: dict):
                    event = StreamEvent(type="stream", message=ChatMessage(**msg_dict))
                    await websocket.send_text(event.model_dump_json())

                (
                    session,
                    final_messages,
                ) = await session_orchestrator.chat_ask_websocket(  # Use injected object
                    user=user,
                    callback=ws_callback,
                    session_id=ask.session_id,
                    message=ask.message,
                    agent_name=ask.agent_name,
                    runtime_context=ask.runtime_context,
                    client_exchange_id=ask.client_exchange_id,
                )

                await websocket.send_text(
                    FinalEvent(
                        type="final", messages=final_messages, session=session
                    ).model_dump_json()
                )

            except WebSocketDisconnect:
                logger.debug("Client disconnected from chatbot WebSocket")
                break
            except Exception as e:
                summary = log_exception(
                    e, "INTERNAL Error processing chatbot client query"
                )
                session_id = (
                    client_request.get("session_id", "unknown-session")
                    if client_request
                    else "unknown-session"
                )
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text(
                        ErrorEvent(
                            type="error", content=summary, session_id=session_id
                        ).model_dump_json()
                    )
                else:
                    logger.error("[🔌 WebSocket] Connection closed by client.")
                    break
    except Exception as e:
        summary = log_exception(e, "EXTERNAL Error processing chatbot client query")
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_text(
                ErrorEvent(
                    type="error", content=summary, session_id="unknown-session"
                ).model_dump_json()
            )


@router.get(
    "/chatbot/sessions",
    description="Get the list of active chatbot sessions.",
    summary="Get the list of active chatbot sessions.",
)
def get_sessions(
    user: KeycloakUser = Depends(get_current_user),
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> list[SessionWithFiles]:
    return session_orchestrator.get_sessions(user)


@router.get(
    "/chatbot/session/{session_id}/history",
    description="Get the history of a chatbot session.",
    summary="Get the history of a chatbot session.",
    response_model=List[ChatMessage],
)
def get_session_history(
    session_id: str,
    user: KeycloakUser = Depends(get_current_user),
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> list[ChatMessage]:
    return session_orchestrator.get_session_history(session_id, user)


@router.delete(
    "/chatbot/session/{session_id}",
    description="Delete a chatbot session.",
    summary="Delete a chatbot session.",
)
def delete_session(
    session_id: str,
    user: KeycloakUser = Depends(get_current_user),
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> bool:
    session_orchestrator.delete_session(session_id, user)
    return True


@router.post(
    "/chatbot/upload",
    description="Upload a file to be attached to a chatbot conversation",
    summary="Upload a file",
)
async def upload_file(
    session_id: str = Form(...),
    agent_name: str = Form(...),
    file: UploadFile = File(...),
    user: KeycloakUser = Depends(get_current_user),
    session_orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> dict:
    return await session_orchestrator.upload_file(user, session_id, agent_name, file)
