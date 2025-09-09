# app/core/chatbot/chatbot_controller.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

import logging
from enum import Enum
from typing import List, Literal, Union

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fred_core import (
    TODO_PASS_REAL_USER,
    KeycloakUser,
    VectorSearchHit,
    get_current_user,
)
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketState

from app.application_context import get_configuration
from app.common.utils import log_exception
from app.core.agents.agent_manager import AgentManager
from app.core.agents.agentic_flow import AgenticFlow
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


class ChatbotController:
    """
    Why this controller stays thin:
      - It exposes HTTP/WS endpoints and delegates *all* chat orchestration
        (session lifecycle, KPI, persistence, streaming) to SessionOrchestrator.
      - This keeps transport concerns (WS/HTTP) separate from agent/runtime logic.
    """

    def __init__(
        self,
        app: APIRouter,
        session_orchestrator: SessionOrchestrator,
        agent_manager: AgentManager,
    ):
        self.agent_manager = agent_manager
        self.session_orchestrator = session_orchestrator
        fastapi_tags: list[str | Enum] = ["Frontend"]

        @app.post(
            "/schemas/echo",
            tags=["Schemas"],
            summary="Ignore. Not a real endpoint.",
            description="Ignore. This endpoint is only used to include some types (mainly one used in websocket) in the OpenAPI spec, so they can be generated as typescript types for the UI. This endpoint is not really used, this is just a code generation hack.",
        )
        def echo_schema(envelope: EchoEnvelope) -> None: ...

        @app.get(
            "/config/frontend_settings",
            summary="Get the frontend dynamic configuration",
            tags=fastapi_tags,
        )
        def get_frontend_config():
            return get_configuration().frontend_settings

        @app.get(
            "/chatbot/agenticflows",
            description="Get the list of available agentic flows",
            summary="Get the list of available agentic flows",
            tags=fastapi_tags,
        )
        def get_agentic_flows(
            user: KeycloakUser = Depends(get_current_user),
        ) -> List[AgenticFlow]:
            return self.agent_manager.get_agentic_flows(user)

        @app.websocket("/chatbot/query/ws")
        async def websocket_chatbot_question(websocket: WebSocket):
            """
            Transport-only:
              - Accept WS
              - Parse ChatAskInput
              - Provide a callback that forwards StreamEvents
              - Send FinalEvent or ErrorEvent
              - All heavy lifting is in SessionOrchestrator.chat_ask_websocket()
            """
            await websocket.accept()
            try:
                while True:
                    client_request = None
                    try:
                        client_request = await websocket.receive_json()
                        ask = ChatAskInput(**client_request)

                        async def ws_callback(msg_dict: dict):
                            # Stream every ChatMessage as a StreamEvent over WS
                            event = StreamEvent(
                                type="stream", message=ChatMessage(**msg_dict)
                            )
                            await websocket.send_text(event.model_dump_json())

                        # Delegate the whole exchange to the orchestrator
                        (
                            session,
                            final_messages,
                        ) = await self.session_orchestrator.chat_ask_websocket(
                            user=TODO_PASS_REAL_USER,  # TODO: add authentication to WS and pass real user here
                            callback=ws_callback,
                            user_id=ask.user_id,
                            session_id=ask.session_id or "unknown-session",
                            message=ask.message,
                            agent_name=ask.agent_name,
                            runtime_context=ask.runtime_context,
                            client_exchange_id=ask.client_exchange_id,
                        )

                        # Send final “bundle”
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
                summary = log_exception(
                    e, "EXTERNAL Error processing chatbot client query"
                )
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text(
                        ErrorEvent(
                            type="error", content=summary, session_id="unknown-session"
                        ).model_dump_json()
                    )

        @app.get(
            "/chatbot/sessions",
            tags=fastapi_tags,
            description="Get the list of active chatbot sessions.",
            summary="Get the list of active chatbot sessions.",
        )
        def get_sessions(
            user: KeycloakUser = Depends(get_current_user),
        ) -> list[SessionWithFiles]:
            # Orchestrator owns session lifecycle surface
            return self.session_orchestrator.get_sessions(user)

        @app.get(
            "/chatbot/session/{session_id}/history",
            description="Get the history of a chatbot session.",
            summary="Get the history of a chatbot session.",
            tags=fastapi_tags,
            response_model=List[ChatMessage],
        )
        def get_session_history(
            session_id: str, user: KeycloakUser = Depends(get_current_user)
        ) -> list[ChatMessage]:
            return self.session_orchestrator.get_session_history(session_id, user)

        @app.delete(
            "/chatbot/session/{session_id}",
            description="Delete a chatbot session.",
            summary="Delete a chatbot session.",
            tags=fastapi_tags,
        )
        def delete_session(
            session_id: str, user: KeycloakUser = Depends(get_current_user)
        ) -> bool:
            self.session_orchestrator.delete_session(session_id, user)
            return True

        @app.post(
            "/chatbot/upload",
            description="Upload a file to be attached to a chatbot conversation",
            summary="Upload a file",
            tags=fastapi_tags,
        )
        async def upload_file(
            session_id: str = Form(...),
            agent_name: str = Form(...),
            file: UploadFile = File(...),
            user: KeycloakUser = Depends(get_current_user),
        ) -> dict:
            return await self.session_orchestrator.upload_file(
                user, session_id, agent_name, file
            )
