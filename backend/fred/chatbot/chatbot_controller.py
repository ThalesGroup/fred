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

import json
import logging
from typing import List
from uuid import uuid4

from chatbot.agent_manager import AgentManager
from services.chatbot_session.in_memory_session_backend import InMemorySessionStorage
from fred.services.chatbot_session.session_manager import SessionManager
from services.chatbot_session.structure.chat_schema import ChatMessagePayload, ErrorEvent, FinalEvent, SessionSchema, SessionWithFiles, StreamEvent
from chatbot.structures.chatbot_error import ChatBotError
from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)

from fastapi.responses import JSONResponse, StreamingResponse
from starlette.websockets import WebSocketState

from chatbot.structures.agentic_flow import AgenticFlow
from chatbot.structures.chatbot_message import ChatAskInput
from common.connectors.file_dao import FileDAO
from common.structure import (
    DAOTypeEnum,
)
from fred.application_context import get_configuration
from common.utils import log_exception
from security.keycloak import KeycloakUser, get_current_user
from services.ai.ai_service import AIService
from services.cluster_consumption.cluster_consumption_service import (
    ClusterConsumptionService,
)
from services.chatbot_session.session_manager import CallbackType

logger = logging.getLogger(__name__)

class ChatbotController:
    """
    This controller is responsible for handling the UI HTTP endpoints and
    WebSocket endpoints. 
    """

    def __init__(self, app: APIRouter, ai_service: AIService):
        self.ai_service = ai_service
        self.cluster_consumption_service = ClusterConsumptionService()
        self.agent_manager = AgentManager()
        self.session_manager = SessionManager(InMemorySessionStorage(), self.agent_manager)

        # For import-export operations
        match get_configuration().dao.type:
            case DAOTypeEnum.file:
                self.dao = FileDAO(get_configuration().dao)
            case dao_type:
                raise NotImplementedError(f"DAO type {dao_type}")

        fastapi_tags = ["Chatbot service"]

        @app.get(
            "/chatbot/agenticflows",
            description="Get the list of available agentic flows",
            summary="Get the list of available agentic flows",
        )
        def get_agentic_flows(user: KeycloakUser = Depends(get_current_user)) -> list[AgenticFlow]:
            return self.agent_manager.get_agentic_flows()


        @app.post(
            "/chatbot/query",
            description="Send a chatbot query via REST (testing or fallback)",
            summary="Chatbot query via REST",
            tags=fastapi_tags,
            response_model=FinalEvent
        )
        @app.post("/chatbot/query", response_model=FinalEvent)
        async def chatbot_query(
            event: ChatAskInput = Body(...),
            user: KeycloakUser = Depends(get_current_user)
        ):
            try:
                streamed_messages = []

                async def capture_callback(msg: dict):
                    streamed_messages.append(ChatMessagePayload(**msg))

                session, messages = await self.session_manager.chat_ask_websocket(
                    callback=capture_callback,
                    user_id=user.email,
                    session_id=event.session_id,
                    message=event.message,
                    agent_name=event.agent_name
                )

                return FinalEvent(
                    type="final",
                    messages=streamed_messages,
                    session=session
                )
            except Exception as e:
                summary = log_exception(e, "Error processing chatbot REST query")
                return JSONResponse(
                    status_code=500,
                    content=ChatBotError(
                        content=summary,
                        session_id=event.session_id or "unknown-session"
                    ).model_dump()
                )

        @app.post("/chatbot/query/stream", response_class=StreamingResponse)
        async def chatbot_query_stream(
            event: ChatAskInput = Body(...),
            user: KeycloakUser = Depends(get_current_user)
        ):
            
            async def event_stream():
                try:
                    streamed_messages: List[ChatMessagePayload] = []

                    async def callback(msg: dict):
                        payload = ChatMessagePayload(**msg)
                        streamed_messages.append(payload)
                        yield json.dumps(StreamEvent(type="stream", message=payload).model_dump()) + "\n"

                    session, final_messages = await self.session_manager.chat_ask_websocket(
                        callback=callback,
                        user_id=user.email,
                        session_id=event.session_id,
                        message=event.message,
                        agent_name=event.agent_name
                    )

                    yield json.dumps(
                        FinalEvent(type="final", messages=final_messages, session=session).model_dump()
                    ) + "\n"

                except Exception as e:
                    error = ErrorEvent(
                        type="error",
                        content=str(e),
                        session_id=event.session_id or "unknown-session"
                    )
                    yield json.dumps(error.model_dump()) + "\n"

            return StreamingResponse(event_stream(), media_type="application/json")

        @app.websocket("/chatbot/query/ws")
        async def websocket_chatbot_question(websocket: WebSocket):
            """
            WebSocket endpoint to handle chatbot queries.
            """
            await websocket.accept()
            try:
                while True:
                    client_request = None
                    try:
                        # Receive the prompt from the client
                        client_request = await websocket.receive_json()
                        client_event = ChatAskInput(**client_request)
                        async def websocket_callback(msg: dict):
                            await websocket.send_json(
                                StreamEvent(
                                    type="stream",
                                    message=ChatMessagePayload(**msg)
                             ).model_dump()
                            )

                        session, messages = await self.session_manager.chat_ask_websocket(
                            callback=websocket_callback,
                            user_id=client_event.user_id,
                            session_id=client_event.session_id,
                            message=client_event.message,
                            agent_name=client_event.agent_name
                        )
                        await websocket.send_text(
                            FinalEvent(
                                type="final",
                                messages=messages,
                                session=session
                            ).model_dump_json()
                        )
                    except Exception as e:
                        summary = log_exception(e, "Error processing chatbot client query")
                        session_id = client_request.get("session_id", "unknown-session")
                        if websocket.client_state == WebSocketState.CONNECTED:
                            await websocket.send_text(
                                ErrorEvent(
                                   type="error",
                                    content=summary,
                                    session_id=session_id
                                ).model_dump()
                            )
                        else:
                            logger.error("[🔌 WebSocket] Connection closed by client.")
                            break
            except WebSocketDisconnect:
                logger.info("Client disconnected from chatbot WebSocket")

        @app.get(
            "/chatbot/sessions",
            description="Get the list of active chatbot sessions.",
            summary="Get the list of active chatbot sessions.",
        )
        def get_sessions(user: KeycloakUser = Depends(get_current_user)) -> list[SessionWithFiles]:
            return self.session_manager.get_sessions(user.email)
        
        @app.get(
            "/chatbot/session/{session_id}/history",
            description="Get the history of a chatbot session.",
            summary="Get the history of a chatbot session.",
            tags=fastapi_tags,
            response_model=List[ChatMessagePayload]
        )
        def get_session_history(session_id: str, user: KeycloakUser = Depends(get_current_user)) -> list[ChatMessagePayload]:
            return self.session_manager.get_session_history(session_id)

        @app.delete(
            "/chatbot/session/{session_id}",
            description="Delete a chatbot session.",
            summary="Delete a chatbot session.",
            tags=fastapi_tags,
        )
        def delete_session(session_id: str, user: KeycloakUser = Depends(get_current_user)) -> bool:
            return self.session_manager.delete_session(session_id)


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
            file: UploadFile = File(...)
        ) -> dict:
            """
            Upload a file to be attached to a chatbot conversation.

            Args:
                user_id (str): User ID.
                session_id (str): Session ID.
                agent_name (str): Agent name.
                file (UploadFile): File to upload.

            Returns:
                dict: Response message.
            """
            return await self.session_manager.upload_file(user_id, session_id, agent_name, file)
            