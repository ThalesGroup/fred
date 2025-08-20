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


import logging
from enum import Enum
from typing import Dict, List, Literal, Union

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Query,
    UploadFile, WebSocket, WebSocketDisconnect,
)
from starlette.websockets import WebSocketState

from pydantic import BaseModel, Field
from fred_core import KeycloakUser, get_current_user, VectorSearchHit

from app.application_context import get_configuration
from app.common.utils import log_exception
from app.core.agents.agent_manager import AgentManager
from app.core.agents.runtime_context import RuntimeContext
from app.core.agents.structures import AgenticFlow
from app.core.chatbot.chat_schema import ChatAskInput, ChatMessage, ErrorEvent, FinalEvent, SessionSchema, SessionWithFiles, StreamEvent
from app.core.chatbot.metric_structures import MetricsBucket, MetricsResponse
from app.core.session.session_manager import SessionManager

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
    def __init__(
        self,
        app: APIRouter,
        session_manager: SessionManager,
        agent_manager: AgentManager,
    ):
        self.agent_manager = agent_manager
        self.session_manager = session_manager
        fastapi_tags: list[str | Enum] = ["Frontend"]

        @app.post(
            "/schemas/echo",
            tags=["Schemas"],
            summary="Echo a schema (schema anchor for codegen)",
            response_model=EchoEnvelope,
        )
        def echo_schema(envelope: EchoEnvelope) -> EchoEnvelope:
            return envelope

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
            return self.agent_manager.get_agentic_flows()

        @app.websocket("/chatbot/query/ws")
        async def websocket_chatbot_question(websocket: WebSocket):
            await websocket.accept()
            try:

                while True:
                    client_request = None
                    try:
                        client_request = await websocket.receive_json()
                        ask = ChatAskInput(**client_request)

                        async def ws_callback(msg_dict: dict):
                            event = StreamEvent(type="stream", message=ChatMessage(**msg_dict))
                            await websocket.send_text(event.model_dump_json())

                        session, final_messages = await self.session_manager.chat_ask_websocket(
                            callback=ws_callback,
                            user_id=ask.user_id,
                            session_id=ask.session_id or "unknown-session",
                            message=ask.message,
                            agent_name=ask.agent_name,
                            runtime_context=ask.runtime_context,
                            client_exchange_id=ask.client_exchange_id,
                        )

                        await websocket.send_text(
                            FinalEvent(type="final", messages=final_messages, session=session).model_dump_json()
                        )

                    except WebSocketDisconnect:
                        logger.debug("Client disconnected from chatbot WebSocket")
                        break
                    except Exception as e:
                        summary = log_exception(e, "INTERNAL Error processing chatbot client query")
                        session_id = (client_request.get("session_id", "unknown-session") if client_request else "unknown-session")
                        if websocket.client_state == WebSocketState.CONNECTED:
                            await websocket.send_text(
                                ErrorEvent(type="error", content=summary, session_id=session_id).model_dump_json()
                            )
                        else:
                            logger.error("[🔌 WebSocket] Connection closed by client.")
                            break
            except Exception as e:
                summary = log_exception(e, "EXTERNAL Error processing chatbot client query")
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text(
                        ErrorEvent(type="error", content=summary, session_id="unknown-session").model_dump_json()
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
            return self.session_manager.get_sessions(user.uid)

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
            return self.session_manager.get_session_history(session_id, user.uid)

        @app.delete(
            "/chatbot/session/{session_id}",
            description="Delete a chatbot session.",
            summary="Delete a chatbot session.",
            tags=fastapi_tags,
        )
        def delete_session(
            session_id: str, user: KeycloakUser = Depends(get_current_user)
        ) -> bool:
            self.session_manager.delete_session(session_id, user.uid)
            return True

        @app.post(
            "/chatbot/upload",
            description="Upload a file to be attached to a chatbot conversation",
            summary="Upload a file",
            tags=fastapi_tags,
        )
        async def upload_file(
            user_id: str = Form(...),
            session_id: str = Form(...),
            agent_name: str = Form(...),
            file: UploadFile = File(...),
        ) -> dict:
            return await self.session_manager.upload_file(user_id, session_id, agent_name, file)

        @app.get(
            "/metrics/chatbot/numerical",
            summary="Get aggregated numerical chatbot metrics",
            tags=fastapi_tags,
            response_model=MetricsResponse,
        )
        def get_node_numerical_metrics(
            start: str,
            end: str,
            precision: str = "hour",
            agg: List[str] = Query(default=[]),
            groupby: List[str] = Query(default=[]),
            user: KeycloakUser = Depends(get_current_user),
        ) -> MetricsResponse:
            SUPPORTED_OPS = {"mean", "sum", "min", "max", "values"}
            agg_mapping: Dict[str, List[str]] = {}
            for item in agg:
                if ":" not in item:
                    raise HTTPException(400, detail=f"Invalid agg parameter format: {item}")
                field, op = item.split(":")
                if op not in SUPPORTED_OPS:
                    raise HTTPException(400, detail=f"Unsupported aggregation op: {op}")
                agg_mapping.setdefault(field, []).append(op)
            return self.session_manager.get_metrics(
                start=start, end=end, precision=precision,
                groupby=groupby, agg_mapping=agg_mapping, user_id=user.uid,
            )
