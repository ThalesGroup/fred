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
import requests

from app.chatbot.agent_manager import AgentManager
from app.flow import AgentFlow
from app.services.chatbot_session.attachement_processing import AttachementProcessing
from app.services.chatbot_session.structure.chat_schema import ChatMessagePayload, ChatTokenUsage, SessionSchema, SessionWithFiles, clean_agent_metadata, clean_token_usage
from app.services.chatbot_session.abstract_session_backend import AbstractSessionStorage
from langchain_core.messages import (BaseMessage, HumanMessage, AIMessage, SystemMessage)

from langgraph.graph.state import CompiledStateGraph
from app.application_context import get_app_context, get_configuration, get_default_model

from app.monitoring.logging_context import set_logging_context

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
        self.context_cache = {}  # Cache for agent contexts
        self.temp_files: dict[str, list[str]] = defaultdict(list)
        self.attachement_processing = AttachementProcessing()

        config = get_configuration()
        self.recursion_limit = config.ai.recursion.recursion_limit
        
    def _infer_message_subtype(self, metadata: dict, message_type: str | None = None) -> Optional[str]:
        """
        Infers the semantic subtype of a message based on its metadata and optionally its message type.
        """
        finish_reason = metadata.get("finish_reason")
        if finish_reason == "stop":
            return "final"
        if finish_reason == "tool_calls":
            return "tool_result"

        # Handle system/tool messages even if finish_reason is missing
        if message_type == "tool":
            return "tool_result"

        if metadata.get("thought") is True:
            fred = metadata.get("fred", {})
            node = fred.get("node")
            if node == "plan":
                return "plan"
            if node == "execute":
                return "execution"
            return "thought"

        if metadata.get("error"):
            return "error"

        return None
    
    def get_chat_profile_data(self, chat_profile_id: str, knowledge_base_url: str = "http://localhost:8111/knowledge/v1") -> dict:
        try:
            response = requests.get(f"{knowledge_base_url}/chatProfiles/{chat_profile_id}", timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to fetch chat profile {chat_profile_id}: {e}")



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
            session = self.storage.get_session(session_id, user_id)
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
        agent_name: str,
        argument: str,
        chat_profile_id: Optional[str] = None
    ) -> Tuple[SessionSchema, List[ChatMessagePayload]]:
        logger.info(f"chat_ask_websocket called with user_id: {user_id}, session_id: {session_id}, message: {message}, agent_name: {agent_name}, chat_profile_id: {chat_profile_id}")

        session, history, agent, is_new_session = self._prepare_session_and_history(
            user_id=user_id,
            session_id=session_id,
            message=message,
            agent_name=agent_name,
            argument=argument
        )
        set_logging_context(user_id=user_id, session_id=session.id, agent_name=agent_name)
        exchange_id = str(uuid4())
        base_rank = len(history)

        injected_payload = None

        # 🔁 Inject profile context if provided
        if chat_profile_id:
            try:
                profile_data = self.get_chat_profile_data(chat_profile_id)
                title = profile_data.get("title", "")
                description = profile_data.get("description", "")
                markdown = profile_data.get("markdown", "")
                full_context = f"## {title}\n\n{description}\n\n{markdown}"

                profile_message = AIMessage(
                    content=full_context,
                    response_metadata={"injected": True, "origin": "chat_profile"}
                )
                history.insert(0, profile_message)

                injected_payload = ChatMessagePayload(
                    exchange_id=str(uuid4()),
                    type="ai",
                    sender="assistant",
                    content=full_context,
                    timestamp=datetime.now().isoformat(),
                    session_id=session.id,
                    rank=base_rank,  # injected context comes before user message
                    metadata={"injected": True, "origin": "chat_profile"},
                    subtype="injected_context"
                )

                logger.info(f"[PROFILE CONTEXT INJECTED] Profile {chat_profile_id} injected successfully.")

            except Exception as e:
                logger.error(f"Failed to inject chat profile context: {e}")

        # 🕐 Generate timestamp and extract metadata
        timestamp = datetime.now().isoformat()
        metadata = clean_agent_metadata(getattr(message, "response_metadata", getattr(message, "metadata", {})) or {})
        subtype = self._infer_message_subtype(metadata, message.type if isinstance(message, BaseMessage) else None)

        # 👤 Create the user message payload first (before any agent response)
        user_payload = ChatMessagePayload(
            exchange_id=exchange_id,
            type="human",
            sender="user",
            content=message,
            timestamp=timestamp,
            session_id=session.id,
            rank=base_rank,
            subtype=subtype
        )

        all_payloads = []
        if injected_payload:
            all_payloads.append(injected_payload)

        all_payloads.append(user_payload)

        # 🤖 Call the agent and collect the assistant responses
        try:
            agent_messages = await self._stream_agent_response(
                compiled_graph=agent.get_compiled_graph(),
                input_messages=history,
                session_id=session.id,
                callback=callback,
                exchange_id=exchange_id,
                base_rank=base_rank,
            )

            # Ensure correct ranks for assistant messages
            for i, m in enumerate(agent_messages):
                m.rank = base_rank + 1 + i

            all_payloads.extend(agent_messages)

        except Exception as e:
            logger.error(f"Error during agent execution: {e}")
            # No crash — we still return user message only

        # 💾 Save all messages in correct order
        session.updated_at = datetime.now()
        self.storage.save_session(session)
        self.storage.save_messages(session.id, all_payloads, user_id)

        return session, all_payloads


    def _prepare_session_and_history(
        self, user_id: str, 
        session_id: str | None, 
        message: str,
        agent_name: str,
        argument: str
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
            messages = self.get_session_history(session.id, user_id)

            for msg in messages:
                logger.debug(f"[RESTORED] session_id={msg.session_id} exchange_id={msg.exchange_id} rank={msg.rank} | type={msg.type} | subtype={msg.subtype} | fred.task={msg.metadata.get('fred', {}).get('task')}")
                if msg.type == "human":
                    history.append(HumanMessage(content=msg.content))
                elif msg.type == "ai":
                        history.append(AIMessage(content=msg.content, response_metadata=msg.metadata or {}))
                elif msg.type == "system":
                        history.append(SystemMessage(content=msg.content))
                    


        # Append the new question
        history.append(HumanMessage(message))

        agent = self.agent_manager.get_create_agent_instance(agent_name, session.id, argument=argument)

        return session, history, agent, is_new_session

    def delete_session(self, session_id: str, user_id: str) -> bool:
        return self.storage.delete_session(session_id, user_id)

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


    def get_session_history(self, session_id: str, user_id: str) -> List[ChatMessagePayload]:
        return self.storage.get_message_history(session_id, user_id)
    

    async def _stream_agent_response(
        self,
        compiled_graph: CompiledStateGraph,
        input_messages: List[BaseMessage],
        session_id: str,
        base_rank: int,
        callback: CallbackType,
        exchange_id: str,
        config: Dict = None,
    ) -> List[BaseMessage]:
        """
        Executes the agentic flow and streams responses via the given callback.

        Args:
            compiled_graph: A compiled LangGraph graph.
            input_messages: List of Human/AI messages.
            session_id: Current session ID (used as thread ID).
            callback: A function that takes a `dict` and handles the streamed message.
            exchange_id:  the ID of the exchange, used to identify the messages part of a single request-replies group.
            config: Optional LangGraph config dict override.
            
        Returns:
            The final AIMessage.
        """

        config = config or {
            "configurable": {"thread_id": session_id},
            "recursion_limit": self.recursion_limit
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
                for i, message in enumerate(message_block):
                    raw_metadata = getattr(message, "response_metadata", {}) or {}
                    cleaned_metadata = clean_agent_metadata(raw_metadata)
                    token_usage = getattr(message, "usage_metadata", {}) or {}
                    cleaned_metadata["token_usage"] = clean_token_usage(token_usage)
                    # If LangChain returns type='tool', force subtype to 'tool_result'
                    #subtype = self._infer_message_subtype(cleaned_metadata)
                    subtype = self._infer_message_subtype(cleaned_metadata, message.type if isinstance(message, BaseMessage) else None)
                    enriched = ChatMessagePayload(
                        exchange_id=exchange_id,
                        type=message.type,
                        sender="assistant" if isinstance(message, AIMessage) else "system",
                        content=message.content,
                        timestamp=datetime.now().isoformat(),
                        rank=base_rank + 1 + i, 
                        session_id=session_id,
                        metadata=cleaned_metadata,
                        subtype=subtype
                    )

                    all_payloads.append(enriched)  # ✅ collect all messages
                    logger.info(
                        "[STREAMED] session_id=%s exchange_id=%s type=%s | subtype=%s | fred.task=%s",
                        enriched.session_id,
                        enriched.exchange_id,
                        enriched.type,
                        enriched.subtype,
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
            logger.debug(f"Retrieved {len(contexts)} contexts for agent '{agent_name}'")
            
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
            logger.debug(f"Context refreshed for agent '{agent_name}'")
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
