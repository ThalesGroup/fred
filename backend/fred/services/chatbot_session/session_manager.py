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

from datetime import datetime
import logging
from pathlib import Path
import secrets
import tempfile
from typing import List, Tuple, Dict, Any, Optional, Union, Callable, Awaitable
from uuid import uuid4

from fastapi import UploadFile
from collections import defaultdict

from chatbot.agent_manager import AgentManager
from flow import AgentFlow
from fred.services.chatbot_session.attachement_processing import AttachementProcessing
from services.chatbot_session.structure.chat_schema import ChatMessagePayload, ChatTokenUsage, SessionSchema, SessionWithFiles, clean_agent_metadata
from services.chatbot_session.abstract_session_backend import AbstractSessionStorage
from langchain_core.messages import (BaseMessage, HumanMessage, AIMessage)
from langgraph.graph.state import CompiledStateGraph
from fred.application_context import get_context_service, get_default_model

import asyncio

logger = logging.getLogger(__name__)

# Type for callback functions (synchronous or asynchronous)
CallbackType = Union[Callable[[Dict], None], Callable[[Dict], Awaitable[None]]]
_session_counter = 0


class SessionManager:
    """
    Manages user sessions and interactions with the chatbot.
    This class is responsible for creating, retrieving, and deleting sessions,
    as well as handling chat interactions.
    """ 
    def __init__(self, storage: AbstractSessionStorage, agent_manager: AgentManager = None):
        """
        Initializes the SessionManager with a storage backend and an optional agent manager.
        :param storage: An instance of AbstractSessionStorage for session management.
        :param agent_manager: An instance of AgentManager for managing agent instances.
        """
        self.storage = storage
        self.agent_manager = agent_manager
        self.context_service = get_context_service()
        self.context_cache = {}  # Cache for agent contexts
        self.temp_files: dict[str, list[str]] = defaultdict(list)
        self.attachement_processing = AttachementProcessing()

    def _get_or_create_session(self, 
                               user_id: str, 
                               query: str,
                               session_id: Optional[str]) -> Tuple[SessionSchema, bool]:
        """
        Retrieves an existing session or creates a new one if not found.

        Args:
            user_id: The user ID.
            session_id: Optional session ID. If provided, will attempt to load it.

        Returns:
            A tuple of (SessionSchema, is_new_session)
        """
        if session_id:
            session = self.storage.get_session(session_id)
            if session:
                logger.info(f"Resumed existing session {session_id} for user {user_id}")
                return session, False

        new_session_id = secrets.token_urlsafe(8)
        title: str = get_default_model().invoke(
            "Give a short, clear title for this conversation based on the user's question. Just a few keywords. Here's the question: " + query
        ).content


        session = SessionSchema(
            id=new_session_id,
            user_id=user_id,
            title=title,
            updated_at=datetime.now(),
        )
        self.storage.save_session(session)
        logger.warning(f"Created new session {new_session_id} for user {user_id}")
        return session, True

    async def chat_ask_websocket(
        self,
        callback: CallbackType,
        user_id: str,
        session_id: str,
        message: str,
        agent_name: str
    ) -> Tuple[SessionSchema, List[ChatMessagePayload]]:
        """
        Handles a chat request via WebSocket.
        This method prepares the session and message history, calls the agent,
        and streams the responses.
        :param callback: The callback to invoke for streaming responses.
        :param user_id: The ID of the user.
        :param session_id: The ID of the session.
        :param message: The message from the user.
        :param agent_name: The name of the agent to be used.
        :return: A tuple of (session, interaction).
        """
        logger.info(f"chat_ask_websocket called with user_id: {user_id}, session_id: {session_id}, message: {message}, agent_name: {agent_name}")
        # Step 1: Prepare session and history
        session, history, agent, is_new_session = self._prepare_session_and_history(
            user_id=user_id,
            session_id=session_id,
            message=message,
            agent_name=agent_name
        )
        assistant_id = str(uuid4())
        all_messages = await self._stream_agent_response(
            compiled_graph=agent.get_compiled_graph(),
            input_messages=history,
            session_id=session.id,
            callback=callback,
            assistant_id=assistant_id,
        )
        # Update session
        session.updated_at = datetime.now()
        self.storage.save_session(session)
           # Generate ChatMessagePayloads
           # Count only user messages in prior history
        user_turn_index = sum(1 for m in history if isinstance(m, HumanMessage))
        base_rank = user_turn_index * 10
        #user_turn_index = (len(history) - 1) // 2  # Human/AI alternating, so user turns index = floor(n / 2)
        #base_rank = user_turn_index * 10  # Leave room for multiple AI thoughts
        timestamp = datetime.now().isoformat()

        user_payload = ChatMessagePayload(
            id=assistant_id,
            type="human",
            sender="user",
            content=message,
            timestamp=timestamp,
            session_id=session.id,
            rank=base_rank,
        )
        # Create assistant/system payloads
        response_payloads = []
        for i, msg in enumerate(all_messages):
            msg_type = "ai" if isinstance(msg, AIMessage) else "system"
            payload = ChatMessagePayload(
                id=str(uuid4()),
                type=msg_type,
                sender="assistant" if isinstance(msg, AIMessage) else "system",
                content=msg.content,
                timestamp=timestamp,
                session_id=session.id,
                rank=base_rank  + 1 + i,  # you can adjust this as needed
            )
            metadata = clean_agent_metadata(
                getattr(msg, "response_metadata", getattr(msg, "metadata", {})) or {}
            )
            metadata["token_usage"] = ChatTokenUsage(input_tokens=0, output_tokens=0, total_tokens=0).model_dump()
            payload.metadata = metadata

            """ if isinstance(msg, AIMessage):
                payload = payload.with_metadata(
                model=msg.response_metadata.get("model_name"),
                sources=msg.response_metadata.get("sources", []),
                token_usage=ChatTokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
            )
            else:
                payload = payload.with_metadata(
                token_usage=ChatTokenUsage(input_tokens=0, output_tokens=0, total_tokens=0)
            ) """
            logger.info(f"[SAVING] type={msg_type} | content={msg.content[:60]} | thought={payload.metadata.get('thought')} | fred.task={payload.metadata.get('fred', {}).get('task')}")
            response_payloads.append(payload)
                
        # Save messages to storage
        all_payloads = [user_payload] + response_payloads
        self.storage.save_messages(session.id, all_payloads)
        return session, all_payloads

    def _prepare_session_and_history(
        self, user_id: str, session_id: str | None, message: str, agent_name: str
    ) -> Tuple[SessionSchema, List[BaseMessage], AgentFlow, bool]:
        """
        Prepares the session, message history, and agent instance.
        The agent is determined by the agent_name parameter.
        If session_id is None, a new session is created.
        Args:
            - user_id: the ID of the user
            - session_id: the ID of the session (None if a new session should be created)
            - message: the message from the user
            - agent_name: the name of the agent to be used

        Returns:
            - session: the resolved or created session
            - history: the list of BaseMessage to feed to the agent
            - agent: the LangGraph agent instance
            - is_new_session: whether this session was newly created
        """
       
        session, is_new_session = self._get_or_create_session(user_id, message, session_id)

        # Build up message history
        history: List[BaseMessage] = []
        if not is_new_session:
            messages = self.get_session_history(session.id)

            for msg in messages:
                logger.info(f"[RESTORED] id={msg.id} | type={msg.type} | thought={msg.metadata.get('thought')} | fred.task={msg.metadata.get('fred', {}).get('task')}")
                if msg.type == "human":
                    history.append(HumanMessage(content=msg.content))
                elif msg.type == "ai":
                        history.append(AIMessage(content=msg.content, response_metadata=msg.metadata or {}))
                elif msg.type == "system":
                    #history.append(SystemMessage(content=msg.content))
                    pass


        # Append the new question
        history.append(HumanMessage(message))

        agent = self.agent_manager.get_create_agent_instance(agent_name, session.id)

        return session, history, agent, is_new_session

    def delete_session(self, session_id: str) -> bool:
        return self.storage.delete_session(session_id)

    def get_sessions(self, user_id: str) -> List[SessionWithFiles]:
        """
        Retrieves all sessions for a user and enriches them with file names.
        The reason we enrich with file names is that the session storage does not
        store file names, but only the session ID.
        This is because the files are stored in a temporary directory they are meant to be 
        moderatively persistent.
        Args:
            user_id: The ID of the user.
        Returns:
            A list of SessionWithFiles objects, each containing session data and file names.
        """
        sessions = self.storage.get_sessions_for_user(user_id)
        enriched_sessions = []

        for session in sessions:
            session_folder = self.get_session_temp_folder(session.id)
            if session_folder.exists():
                file_names = [f.name for f in session_folder.iterdir() if f.is_file()]
            else:
                file_names = []

            enriched_sessions.append(
                SessionWithFiles(
                    **session.dict(),
                    file_names=file_names
                )
            )
        return enriched_sessions


    def get_session_history(self, session_id: str) -> List[ChatMessagePayload]:
        return self.storage.get_message_history(session_id)
    

    async def _stream_agent_response(
        self,
        compiled_graph: CompiledStateGraph,
        input_messages: List[BaseMessage],
        session_id: str,
        callback: CallbackType,
        assistant_id: str,
        config: Dict = None,
    ) -> List[BaseMessage]:
        """
        Executes the agentic flow and streams responses via the given callback.

        Args:
            compiled_graph: A compiled LangGraph graph.
            input_messages: List of Human/AI messages.
            session_id: Current session ID (used as thread ID).
            callback: A function that takes a `dict` and handles the streamed message.
            assistant_id:  ID for the assistant.
            config: Optional LangGraph config dict override.
            
        Returns:
            The final AIMessage.
        """
        config = config or {
            "configurable": {"thread_id": session_id},
            "recursion_limit": 40
        }
        all_payloads: list[ChatMessagePayload] = []
        try:
            async for event in compiled_graph.astream(
                {"messages": input_messages},
                config=config,
                stream_mode="updates"
            ):
                # LangGraph returns events like {'end': {'messages': [...]}} or {'next': {...}}
                key = next(iter(event))
                message_block = event[key].get("messages", [])
                for message in message_block:
                    enriched = ChatMessagePayload(
                        id=assistant_id or str(uuid4()),
                        type=message.type,
                        sender="assistant" if isinstance(message, AIMessage) else "system",
                        content=message.content,
                        timestamp=datetime.now().isoformat(),
                        session_id=session_id,
                        metadata=clean_agent_metadata(getattr(message, "response_metadata", {}) or {})
                    )

                    all_payloads.append(enriched)  # ✅ collect all messages
                    """ enriched_dict = {
                        "id": assistant_id or str(uuid4()),
                        "type": message.type,
                        "sender": "assistant" if isinstance(message, AIMessage) else "system",
                        "content": message.content,
                        "timestamp": datetime.now().isoformat(),
                        "session_id": session_id,
                        "metadata": clean_agent_metadata(getattr(message, "response_metadata", {}) or {})
                    } """
                    logger.info(
                        "[STREAMED] %s\n         type=%s | thought=%s | fred.task=%s",
                        enriched.id,
                        enriched.type,
                        enriched.metadata.get("thought"),
                        enriched.metadata.get("fred", {}).get("task") if isinstance(enriched.metadata.get("fred"), dict) else None
                    )

                    result = callback(enriched.model_dump())
                    if asyncio.iscoroutine(result):
                        await result

        except Exception as e:
            logger.exception(f"Error streaming agent response: {e}")
            raise e

        return all_payloads

    def _get_agent_contexts(self, agent_name: str) -> List[Dict[str, Any]]:
        """
        Gets contexts for an agent using the existing context service.
        
        Args:
            agent_name: Name of the agent for which to retrieve contexts
            
        Returns:
            List of context dictionaries
        """
        # Check if the context is already in cache
        if agent_name in self.context_cache:
            logger.debug(f"Using cached contexts for agent '{agent_name}'")
            return self.context_cache[agent_name]
            
        try:
            # Retrieve contexts from the service
            contexts = self.context_service.get_context(agent_name)
            logger.info(f"Retrieved {len(contexts)} contexts for agent '{agent_name}'")
            
            # Cache it
            self.context_cache[agent_name] = contexts
            return contexts
                
        except Exception as e:
            logger.error(f"Error retrieving contexts for agent '{agent_name}': {e}")
            return []

    def refresh_context_for_agent(self, agent_name: str) -> bool:
        """
        Refreshes an agent's context by removing it from the cache.
        
        Args:
            agent_name: Name of the agent whose context to refresh
            
        Returns:
            True if the context was refreshed, False otherwise
        """
        if agent_name in self.context_cache:
            del self.context_cache[agent_name]
            logger.info(f"Context refreshed for agent '{agent_name}'")
            return True
        return False
    

    def get_session_temp_folder(self, session_id: str) -> Path:
        base_temp_dir = Path(tempfile.gettempdir()) / "chatbot_uploads"
        session_folder = base_temp_dir / session_id
        session_folder.mkdir(parents=True, exist_ok=True)
        return session_folder

    async def upload_file(self, user_id: str, session_id: str, agent_name: str, file: UploadFile) -> dict:
        """
        Handle file upload from a user to be attached to a chatbot session.

        Args:
            user_id (str): ID of the user.
            session_id (str): ID of the session.
            agent_name (str): Name of the agent.
            file (UploadFile): The uploaded file.

        Returns:
            dict: Response info with file path.
        """
        try:
            # Create session-specific temp directory
            session_folder = self.get_session_temp_folder(session_id)
            file_path = session_folder / file.filename

            # Write file content
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)

            if str(file_path) not in self.temp_files[session_id]:
                self.temp_files[session_id].append(str(file_path))
                self.attachement_processing.process_attachment(file_path)
            logger.info(f"[📁 Upload] File '{file.filename}' saved to {file_path} for session '{session_id}'")
            return {
                "filename": file.filename,
                "saved_path": str(file_path),
                "message": "File uploaded successfully"
            }

        except Exception as e:
            logger.exception(e)
            raise RuntimeError("Failed to store uploaded file.")
