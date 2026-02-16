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
import math
import sys
import tempfile
import time
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import (
    Any,
    AsyncIterator,
    BinaryIO,
    ClassVar,
    Dict,
    List,
    Optional,
    Sequence,
    Type,
    cast,
    get_type_hints,
)

from fred_core import get_keycloak_client_id, get_keycloak_url
from fred_core.kpi import KPIActor, phase_timer
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import Runnable, RunnableConfig

# from langfuse import Langfuse
# from langfuse.callback import CallbackHandler
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import MessagesState
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from agentic_backend.application_context import (
    get_app_context,
    get_knowledge_flow_base_url,
)
from agentic_backend.common.kf_workspace_client import (
    KfWorkspaceClient,
    UserStorageBlob,
    UserStorageUploadResult,
    WorkspaceRetrievalError,
    WorkspaceUploadError,
)
from agentic_backend.common.structures import (
    AgentChatOptions,
    AgentSettings,
    ChatContextMessage,
)
from agentic_backend.common.user_token_refresher import (
    refresh_user_access_token_from_keycloak,
)
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec
from agentic_backend.core.agents.agent_state import Prepared, resolve_prepared
from agentic_backend.core.agents.agent_utils import log_agent_message_summary
from agentic_backend.core.agents.runtime_context import RuntimeContext, get_language
from agentic_backend.scheduler.agent_contracts import AgentInputArgsV1

logger = logging.getLogger(__name__)


class _SafeDict(dict):
    def __missing__(self, key):  # keep unknown tokens literal: {key}
        return "{" + key + "}"


class AgentFlow:
    """
    Base class for LangGraph-based AI agents.

    Each agent is a stateful flow that uses a LangGraph to reason and produce outputs.
    Subclasses must define their graph (StateGraph), base prompt, and optionally a toolkit.

    Responsibilities:
    - Store metadata (name, role, etc.)
    - Hold a reference to the LangGraph (set via `graph`)
    - Compile the graph to run it
    - Optionally save it as an image (for visualization)

    Subclasses are responsible for defining any reasoning nodes (e.g. `reasoner`)
    and for calling `get_compiled_graph()` when they are ready to execute the agent.
    """

    # ------------------------------------------------
    # 1. CLASS VARIABLES (Schema/Defaults, required by all instances)
    # ------------------------------------------------
    tuning: ClassVar[AgentTuning]
    default_chat_options: ClassVar[Optional[AgentChatOptions]] = None

    _tuning: AgentTuning
    run_config: RunnableConfig = {}  # Use an empty dict as the default/initial value
    middlewares: list = []  # Optional LangChain/LangGraph middlewares (HITL, etc.)

    def __init__(self, agent_settings: AgentSettings):
        """
        Initialize an AgentFlow instance with configuration from AgentSettings.

        This sets all primary properties of the agent according to the provided AgentSettings,
        falling back to class defaults if not explicitly specified.
        Args:
            agent_settings: An AgentSettings instance containing agent metadata, display, and configuration options.
                - name: The name of the agent.
                - role: The agent's primary role or persona.
                - nickname: Alternate short label for UI display.
                - description: A detailed summary of agent functionality.
                - icon: The icon used for representation in the UI.
                - categories: (Optional) Categories that the agent is part of.
                - tag:s (Optional) Short tag identifier for the agent.
        """
        self.apply_settings(agent_settings)
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self._graph = None  # Will be built in async_init
        self.streaming_memory = MemorySaver()
        self.compiled_graph: Optional[CompiledStateGraph] = None
        self._prepared_context: Optional[Prepared] = None
        # has_public_key = os.getenv("LANGFUSE_PUBLIC_KEY") is not None
        # has_secret_key = os.getenv("LANGFUSE_SECRET_KEY") is not None

        # if has_public_key and has_secret_key:
        #     # Only initialize if keys are present
        #     self.langfuse_client = Langfuse()
        # else:
        #     # Set to None if disabled
        #     self.langfuse_client = None

    def get_compiled_graph(
        self, checkpointer: Optional[object] = None
    ) -> CompiledStateGraph:
        """
        Compile and return the agent's graph (idempotent).
        Subclasses must set `self._graph` in async_init().
        """
        # If we have a cached graph, return it.
        # The checkpointer is bound at compile time, so we assume it's the correct one.
        if self.compiled_graph is not None:
            logger.debug(
                "[AGENT_FLOW] Reusing cached compiled graph for agent=%s",
                self.get_id(),
            )
            return self.compiled_graph

        if self._graph is None:
            # Strong, early signal to devs wiring the agent: you must build the graph in async_init()
            raise RuntimeError(
                f"{type(self).__name__}: _graph is None. Did you forget to set it in async_init()?"
            )

        cp = checkpointer or self.streaming_memory
        logger.info(
            "[AGENT_FLOW] Compiling graph for agent=%s with checkpointer=%s",
            self.get_id(),
            type(cp).__name__,
        )
        self.compiled_graph = self._graph.compile(checkpointer=cp)
        return self.compiled_graph

    def apply_settings(self, new_settings: AgentSettings) -> None:
        """
        Apply the authoritative settings resolved by AgentManager.
        No runtime merging with class defaults happens here.
        """
        self.agent_settings = new_settings.model_copy(deep=True)
        # Use the resolved tuning from Manager; if missing, allow class-level as a hard fallback.
        self._tuning = self.agent_settings.tuning or type(self).tuning
        # Keep .tuning coherent on the settings object held by the instance
        self.agent_settings.tuning = self._tuning

    def set_middlewares(self, middlewares: list) -> None:
        """
        Configure LangChain/LangGraph middlewares (e.g., HumanInTheLoop).
        These will be injected into the run_config at execution time.
        """
        self.middlewares = list(middlewares or [])

    async def async_init(self, runtime_context: RuntimeContext):
        """
        Asynchronous initialization routine that must be implemented by subclasses.
        """
        self.runtime_context: RuntimeContext = runtime_context
        self.storage_client = KfWorkspaceClient(agent=self)

    async def aclose(self) -> None:
        """
        Asynchronous cleanup routine that can be overridden by subclasses.
        Default implementation does nothing.
        """
        pass

    def refresh_user_access_token(self) -> str:
        """
        Refreshes the user's access token and updates the session's run_config.
        Returns the newly acquired access token.
        """
        refresh_token = self.runtime_context.refresh_token
        if not refresh_token:
            raise RuntimeError(
                "Cannot refresh user access token: refresh_token missing from run_config."
            )

        keycloak_url = get_keycloak_url()
        client_id = get_keycloak_client_id()
        if not keycloak_url:
            raise RuntimeError(
                "User security realm_url is not configured for Keycloak."
            )
        if not client_id:
            raise RuntimeError(
                "User security client_id is not configured for Keycloak."
            )

        logger.info(
            "[SECURITY] Refreshing user access token via Keycloak realm %s",
            keycloak_url,
        )
        payload = refresh_user_access_token_from_keycloak(
            keycloak_url=keycloak_url,
            client_id=client_id,
            refresh_token=refresh_token,
        )

        new_access_token = payload.get("access_token")
        new_refresh_token = payload.get("refresh_token") or refresh_token
        if not new_access_token:
            raise RuntimeError(
                "Keycloak refresh response did not include access_token."
            )

        # Update RuntimeContext attributes (RuntimeContext does not implement item assignment).
        try:
            setattr(self.runtime_context, "access_token", new_access_token)
            setattr(self.runtime_context, "refresh_token", new_refresh_token)
        except Exception:
            logger.debug(
                "Could not set attributes on runtime_context; skipping attribute assignment."
            )

        expires_at = payload.get("expires_at_timestamp")
        if expires_at:
            try:
                setattr(
                    self.runtime_context, "access_token_expires_at", int(expires_at)
                )
            except Exception:
                logger.debug(
                    "Could not set access_token_expires_at on runtime_context; skipping attribute assignment."
                )

        ttl = None
        try:
            ttl = int(expires_at) - int(time.time()) if expires_at else None
        except Exception:
            ttl = None

        ttl_msg = f" ttl={ttl}s" if ttl is not None else ""
        logger.info(
            "[SECURITY] User access token refreshed successfully [expires_at=%s]%s",
            expires_at,
            ttl_msg,
        )
        return new_access_token

    async def astream_updates(
        self,
        state: Any,
        *,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream LangGraph 'updates' while ensuring the agent sees the run config.
        """
        # 1. Start with the incoming config, ensuring it's not None
        self.run_config = config if config is not None else {}
        logger.debug(
            "[AGENT_FLOW] astream_updates run_config configurable=%s thread_id=%s",
            self.run_config.get("configurable"),
            (self.run_config.get("configurable") or {}).get("thread_id"),
        )
        logger.info(
            "[AGENT_FLOW] astream_updates resume=%s config_keys=%s",
            isinstance(state, Command),
            list((self.run_config or {}).keys()),
        )
        # Inject optional middlewares (e.g., HumanInTheLoop) if configured on the agent
        logger.info(
            "[AGENT_FLOW] astream_updates start agent=%s thread_id=%s using_memory_saver=%s",
            self.get_id(),
            (self.run_config.get("configurable") or {}).get("thread_id"),
            True,
        )
        # Force a checkpointer for HITL/interrupt resume. Using the per-instance MemorySaver by default.
        compiled = self.get_compiled_graph(checkpointer=self.streaming_memory)
        logger.info(
            "[AGENT_FLOW] astream_updates compiled graph agent=%s checkpointer=%s",
            self.get_id(),
            type(self.streaming_memory).__name__,
        )

        # 2. Instantiate the Langfuse Handler
        # CallbackHandler expects an optional public_key (str | None); do not pass the Langfuse client instance here.
        # langfuse_handler = None
        # if self.langfuse_client is not None:
        #     langfuse_handler = CallbackHandler()

        #     # 3. Safely get the callbacks list (Resolves Pylance warnings)
        #     existing_callbacks = self.run_config.get("callbacks")
        #     if existing_callbacks is None:
        #         # No callbacks provided yet — create a list with our handler
        #         callbacks_list = [langfuse_handler]
        #     elif isinstance(existing_callbacks, list):
        #         # If it's already a list, create a shallow copy and append to avoid mutating external state
        #         callbacks_list = list(existing_callbacks) + [langfuse_handler]
        #     else:
        #         # If it's a single callback object (e.g., a BaseCallbackManager or handler), wrap it into a list
        #         callbacks_list = [existing_callbacks, langfuse_handler]

        #     # 4. Update the config with a list of callbacks (langgraph expects an iterable/list)
        #     self.run_config["callbacks"] = callbacks_list  # type: ignore[assignment]
        #     logger.info(
        #         "[AGENTS] Langfuse CallbackHandler added to run_config callbacks for agent '%s'.",
        #         self.get_name(),
        #     )

        # 5. Execute the graph using the MODIFIED config (self.run_config)
        async for event in compiled.astream(
            state,
            config=self.run_config,
            stream_mode="updates",
            **kwargs,
        ):
            yield event

        # 6. Flush the client after the run is complete
        # if self.langfuse_client is not None:
        #     self.langfuse_client.flush()

    def log_message_summary(self, messages: Sequence[AnyMessage]) -> None:
        """
        Log a concise summary of message sequence for debugging purposes.

        Each line shows:
            [index] role/type | content preview | tool_call_id(s)
        """
        label = f"Messages history for agent '{self.get_id()}'"
        log_agent_message_summary(messages, label=label)

    @staticmethod
    def ensure_any_message(msg: object) -> AnyMessage:
        """
        Normalize arbitrary model outputs into an AnyMessage.
        - BaseMessage -> cast to AnyMessage (runtime type will be AIMessage, etc.)
        - str         -> AIMessage(content=str)
        - other       -> AIMessage(content=repr(other))
        """
        if isinstance(msg, BaseMessage):
            return cast(AnyMessage, msg)
        if isinstance(msg, str):
            return AIMessage(content=msg)
        return AIMessage(content=repr(msg))

    async def ask_model(
        self,
        runnable: Runnable,
        messages: Sequence[AnyMessage],
        **kwargs,
    ) -> AnyMessage:
        """
        Invoke any Runnable (model, chain, or tool) and return a normalized AnyMessage.
        This is the preferred helper for multi-model agents.
        """
        raw = await runnable.ainvoke(messages, **kwargs)
        return self.ensure_any_message(raw)

    def recent_messages(
        self,
        messages: Sequence[Any],
        max_messages: int = 8,
    ) -> List[Any]:
        """
        Return the most recent messages including AI messages and all tool messages
        associated with any tool calls present in the selection.
        """
        if not messages or max_messages <= 0:
            return []

        selected = list(messages[-max_messages:])
        i = 0
        while i < len(selected):
            msg = selected[i]
            if isinstance(msg, ToolMessage):
                call_id = getattr(msg, "tool_call_id", None)
                if call_id:
                    for ai_msg in reversed(messages):
                        if isinstance(ai_msg, AIMessage):
                            tool_calls = getattr(ai_msg, "tool_calls", [])
                            if any(call.get("id") == call_id for call in tool_calls):
                                if ai_msg not in selected:
                                    selected.insert(0, ai_msg)
                                    i += 1
                                for call in tool_calls:
                                    for tm in messages:
                                        if isinstance(tm, ToolMessage) and getattr(
                                            tm, "tool_call_id", None
                                        ) == call.get("id"):
                                            if tm not in selected:
                                                ai_index = selected.index(ai_msg)
                                                selected.insert(ai_index + 1, tm)
                                break
            i += 1

        return selected

    @staticmethod
    def delta(*msgs: AnyMessage) -> MessagesState:
        """Return a MessagesState-compatible state update."""
        # Note: You need to ensure MessagesState is imported correctly from langgraph.graph
        return {"messages": list(msgs)}

    @staticmethod
    def fresh_turn(human: HumanMessage) -> dict:
        """
        Start a brand-new turn:
        - Only the new human message is appended.
        - Force ephemeral state back to defaults (plan/progress/step_index).
        """
        return {
            "messages": [human],
            "plan": None,
            "progress": [],
            "step_index": 0,
            # keep 'objective' unset; `plan()` will set it from latest human
        }

    @classmethod
    def _merge_chat_options(
        cls, current: Optional[AgentChatOptions]
    ) -> AgentChatOptions:
        base = cls.default_chat_options or AgentChatOptions()
        effective = base.model_copy(deep=True)
        if not current:
            return effective

        overrides = current.model_dump(exclude_unset=True)
        if overrides:
            effective = effective.model_copy(update=overrides)
        return effective

    def get_end_user_id(self) -> str:
        """
        Retrieves the ID of the end-user (the human interacting with the chatbot)
        from the execution configuration.
        """
        # self.run_config is available when the node is executed
        # It contains the 'configurable' dict passed during astream()
        user_id = self.run_config.get("configurable", {}).get("user_id")

        if not user_id:
            # IMPORTANT: Raise an error if the user ID is mandatory for asset operations
            raise ValueError(
                "Cannot determine end user ID. 'user_id' must be set in the RunnableConfig."
            )

        return str(user_id)

    def get_agent_settings(self) -> AgentSettings:
        """Return the current effective AgentSettings for this instance."""
        return self.agent_settings

    def get_agent_tunings(self) -> AgentTuning:
        """Return the current effective AgentTuning for this instance."""
        return self._tuning

    def get_id(self) -> str:
        """
        Return the agent's name.
        This is the primary identifier for the agent. In particular, it is used
        to identify the agent in a leader's crew.
        """
        return self.agent_settings.id

    def get_description(self) -> str:
        """
        Return the agent's description. This is key for the leader to decide
        which agent to delegate to.
        """
        return self._tuning.description if self._tuning else ""

    def get_role(self) -> str:
        """
        Return the agent's role. This defines the agent's primary function and
        responsibilities within the system.
        """
        return self._tuning.role if self._tuning else ""

    def get_tags(self) -> List[str]:
        """
        Return the agent's tags. Tags are used for categorization and
        discovery in the UI. It is also used by leaders to select agents
        for their crew based on required skills.
        """
        return self._tuning.tags if self._tuning else []

    def get_tuning_spec(self) -> Optional[AgentTuning]:
        """
        Return the class-declared tuning spec (the *schema* of tunables).
        Why not the resolved values? Because the UI needs the spec to render fields.
        Current values live in `self._tuning` and are read via `get_tuned_text(...)`.
        """
        return self.tuning

    async def read_agent_bundled_file(self, filename: str) -> str:
        """
        Reads a static file bundled as a resource alongside the calling agent's module file.

        This is the preferred way to access small, companion text files like
        templates or hardcoded default content shipped with the agent code.

        Args:
            filename: The name of the file (e.g., 'welcome.txt') located in
                      the same directory as the agent's Python file.

        Returns:
            The content of the file as a string.

        Raises:
            AssetRetrievalError: If the file is not found or cannot be read.
        """
        # 1. Get the module object for the derived class calling this method
        # We look up the calling frame to find the module path of the agent class instance.
        agent_module_name = self.__module__

        try:
            # Get a Traversable object pointing to the file path
            resource_path = files(sys.modules[agent_module_name]).joinpath(filename)

            # Read the file content as text
            content = resource_path.read_text(encoding="utf-8")
            return content

        except FileNotFoundError:
            error_msg = (
                f"Bundled file '{filename}' not found in module '{agent_module_name}'."
            )
            logger.error(error_msg)
            # Raise a specific exception so the agent node can handle the failure
            raise WorkspaceRetrievalError(error_msg)

        except Exception as e:
            error_msg = (
                f"Failed to read bundled file '{filename}' in '{agent_module_name}'. "
                f"Details: {type(e).__name__}: {e}"
            )
            logger.error(error_msg, exc_info=True)
            raise WorkspaceRetrievalError(error_msg)

    def _default_agent_id(self) -> str:
        return self.agent_settings.id or type(self).__name__

    async def fetch_asset_text(
        self,
        asset_key: str,
    ) -> str:
        try:
            access_token = getattr(self.runtime_context, "access_token", None)
            if not access_token:
                access_token = self.refresh_user_access_token()

            return await self.storage_client.fetch_user_text(
                asset_key,
                access_token,
            )
        except WorkspaceRetrievalError as e:
            logger.error(f"Failed to fetch asset for agent: {e}")
            return f"[Asset Retrieval Error: {e.args[0]}]"
        except Exception as e:
            logger.error(f"Unexpected error fetching asset for agent: {e}")
            raise

    async def fetch_agent_config_text(
        self,
        asset_key: str,
        *,
        agent_id: str | None = None,
    ) -> str:
        """
        Fetch a text file from the agent configuration storage (admin-managed, read-only for agents).

        In case of problem the exception is raised to the caller.
        """
        access_token = getattr(self.runtime_context, "access_token", None)
        if not access_token:
            access_token = self.refresh_user_access_token()

        return await self.storage_client.fetch_agent_config_text(
            asset_key,
            access_token,
            agent_id or self._default_agent_id(),
        )

    async def _fetch_blob(
        self,
        asset_key: str,
    ) -> UserStorageBlob:
        try:
            access_token = getattr(self.runtime_context, "access_token", None)
            if not access_token:
                access_token = self.refresh_user_access_token()

            return await self.storage_client.fetch_user_blob(
                asset_key,
                access_token,
            )
        except WorkspaceRetrievalError as e:
            logger.error(f"Failed to fetch asset for agent: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching asset for agent: {e}")
            raise

    async def fetch_config_blob_to_tempfile(
        self,
        asset_key: str,
        suffix: str | None = None,
        *,
        agent_id: str | None = None,
    ) -> Path:
        """
        Fetch a configuration file (typically a template) from the agent configuration storage.
        Remember that this is different from user storage! The configuration storage
        is scoped to the agent and is not user-specific. It can be filled only by
        administrators or via agent setup processes.

        The downloaded file is written to a temporary file and returned as a Path object.
        IMPORTANT on suffix:
          - If suffix is provided, it forces the temp file extension (e.g., ".pptx"). Only do this
            when the bytes really match that format; some libraries pick the parser based on extension.
          - If suffix is None (default), we reuse the fetched blob's extension to avoid mime/format mismatch.
        """
        access_token = (
            getattr(self.runtime_context, "access_token", None)
            or self.refresh_user_access_token()
        )
        blob = await self.storage_client.fetch_agent_config_blob(
            asset_key,
            access_token,
            agent_id or self._default_agent_id(),
        )
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix or Path(blob.filename).suffix
        ) as f:
            f.write(blob.bytes)
            temp_path = Path(f.name)
        return temp_path

    async def upload_user_blob(
        self,
        key: str,
        file_content: bytes | BinaryIO,
        filename: str,
        content_type: Optional[str] = None,
    ) -> UserStorageUploadResult:
        """
        Uploads a binary file to the user's personal asset storage.

        Args:
            key: The logical key for the asset (e.g., 'generated_report.pdf').
            file_content: The binary content (bytes or file-like object).
            filename: The original/intended filename.
            content_type: Optional MIME type hint.

        Raises:
            AssetUploadError: If the upload fails (e.g., HTTP error).
        """
        logger.info(
            "UPLOADING_ASSET: Attempting to upload asset to user store: %s", key
        )
        try:
            # Upload via Knowledge Flow workspace client
            result = await self.storage_client.upload_user_blob(
                key,
                file_content,
                filename,
                content_type,
            )
            logger.info(
                "UPLOADING_ASSET: Upload successful. Key: %s, Size: %d, document_uid: %s",
                result.key,
                result.size,
                result.document_uid,
            )
            return result
        except WorkspaceUploadError as e:
            logger.error(f"Failed to upload user asset: {e}")
            raise  # Re-raise the specific error
        except Exception as e:
            logger.error(f"Unexpected error during user asset upload: {e}")
            raise

    def _get_text_content(self, message: AnyMessage) -> str:
        """
        Safely extracts string content from an AnyMessage, raising a clean
        error if the content is unexpectedly not a string (e.g., a dict/tool_call).
        This avoids ugly inline casts in agent logic.
        """
        content = message.content
        if isinstance(content, str):
            return content

        # Handle cases where content is None or a complex structure
        if content is None:
            return ""

        logger.warning(
            "Model response content was type %s, expected str. Returning empty string.",
            type(content).__name__,
        )
        return ""

    def get_settings(self) -> AgentSettings:
        """Return the current effective AgentSettings for this instance."""
        return self.agent_settings

    async def chat_context_text(self) -> str:
        """
        Return the *chat context* text from the runtime context (if any).

        When to use:
        - Only when a node explicitly needs chat context info (e.g., tone/role constraints
          about the user). We DO NOT auto-merge this into every prompt.

        Contract:
        - If your agent ignores chat context, simply don't call this method.
        """
        ctx = self.get_runtime_context() or RuntimeContext()
        if self._prepared_context is None:
            self._prepared_context = await resolve_prepared(
                ctx,
                get_knowledge_flow_base_url(),
            )
        prepared = self._prepared_context
        base = (prepared.prompt_chat_context_text or "").strip()
        # Optionally augment with per-turn attachments markdown injected by the chat layer
        if ctx.attachments_markdown is not None:
            base += ("\n\n" if base else "") + ctx.attachments_markdown.strip()
        return base

    def get_recent_history(
        self,
        messages: Sequence[AnyMessage],
        *,
        max_messages: int = 0,
        include_system: bool = False,
        include_tool: bool = False,
        drop_last: bool = True,
    ) -> list[AnyMessage]:
        """
        Return a slice of recent messages for prompt memory.

        Defaults:
        - Drop the last message (usually the current user question that you rephrase).
        - Exclude system/tool messages to avoid duplicating policy or tool chatter unless opted in.
        """
        if max_messages <= 0:
            return []

        msgs = list(messages)
        if drop_last and msgs:
            msgs = msgs[:-1]

        selected: list[AnyMessage] = []
        for m in reversed(msgs):
            if isinstance(m, SystemMessage) and not include_system:
                continue
            if isinstance(m, ToolMessage) and not include_tool:
                continue
            if not include_tool and isinstance(m, AIMessage):
                tool_calls = getattr(m, "tool_calls", None)
                if tool_calls:
                    continue
            selected.append(m)
            if len(selected) >= max_messages:
                break

        selected.reverse()
        return selected

    def render(self, template: str, **tokens) -> str:
        """
        Safe `{token}` substitution for prompt templates.

        Why:
        - Agents often need lightweight templating (e.g., inject `{today}`, `{step}`).
        - Unknown tokens remain literal (e.g., '{unknown}') so you can safely ship
          templates even if not all placeholders are provided.

        Always available:
        - `{today}` in YYYY-MM-DD format.
        """
        base = {"today": self.current_date}
        base.update(tokens or {})
        return (template or "").format_map(_SafeDict(base)).strip()

    def get_tuned_text(self, key: str) -> Optional[str]:
        """
        Read the current value for a tuning field (by dotted key, e.g., 'prompts.system').

        Where values come from:
        - The class-level `tuning` defines the fields/spec and default values.
        - The UI writes user edits back to persistence; those override defaults and are
          rehydrated here as `self._tuning`.

        Usage:
        - Call this at the node where you want to use that piece of text.
        - Returns None when the key is absent or not a string (you decide the fallback).
        """
        ts = self._tuning
        if not ts or not ts.fields:
            return None
        for f in ts.fields:
            if f.key == key:
                return f.default if isinstance(f.default, str) else None
        return None

    def with_system(
        self, system_text: str, messages: Sequence[AnyMessage]
    ) -> list[AnyMessage]:
        """
        Wrap a message list with a single SystemMessage at the front.

        Why:
        - Keep control explicit: the agent chooses exactly when a system instruction
          applies (e.g., inject the tuned system prompt for this node, optionally
          followed by the chat context or other context).

        Notes:
        - Accepts AnyMessage/Sequence to play nicely with LangChain's typing.
        """
        ctx = self.get_runtime_context()
        has_chat_context = False
        if ctx is not None:
            has_chat_context = bool(ctx.selected_chat_context_ids) or bool(
                ctx.attachments_markdown
            )
        if not has_chat_context and self._prepared_context is not None:
            has_chat_context = bool(
                (self._prepared_context.prompt_chat_context_text or "").strip()
            )

        lang = get_language(ctx)
        if lang and not has_chat_context:
            # Only inject language preference if no chat context is present to avoid duplication.
            system_text = (
                f"{system_text}\n\n"
                f"User language preference: respond in '{lang}' by default unless explicitly asked otherwise."
            )
        return [SystemMessage(content=system_text), *messages]

    async def with_chat_context_text(
        self, messages: Sequence[AnyMessage]
    ) -> list[AnyMessage]:
        """
        Wrap the chat context description in a SystemMessage near the start of the messages.

        Why:
        - Force the system to take it into account as prompt-level context.

        """
        messages = [msg for msg in messages if not isinstance(msg, ChatContextMessage)]
        chat_context = await self.chat_context_text()
        if not chat_context:
            return list(messages)
        include_spec = self.get_field_spec("prompts.include_chat_context")
        if include_spec is not None and not bool(
            self.get_tuned_any("prompts.include_chat_context")
        ):
            logger.info(
                "%s: chat context present but disabled by prompts.include_chat_context",
                self,
            )
            return list(messages)

        # Keep system-level context at the front so it is treated like a prompt.
        insert_at = 0
        for i, msg in enumerate(messages):
            if isinstance(msg, SystemMessage):
                insert_at = i + 1
            else:
                break
        updated = list(messages)
        updated.insert(insert_at, ChatContextMessage(content=chat_context))
        logger.info(
            "%s: chat context applied (len=%d insert_at=%d)",
            self,
            len(chat_context),
            insert_at,
        )
        return updated

    def set_runtime_context(self, context: RuntimeContext) -> None:
        """Set the runtime context for this agent."""
        self.runtime_context = context
        self._prepared_context = None

    def get_runtime_context(self) -> Optional[RuntimeContext]:
        """Get the current runtime context."""
        return self.runtime_context

    def _kpi_base_dims(
        self, extra: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Optional[str]]:
        dims: Dict[str, Optional[str]] = {
            "agent_id": self.agent_settings.id or type(self).__name__
        }
        session_id = getattr(self.runtime_context, "session_id", None)
        if session_id:
            dims["session_id"] = str(session_id)
        user_id = getattr(self.runtime_context, "user_id", None)
        if user_id:
            dims["user_id"] = str(user_id)

        extra_dims = dict(extra or {})
        if "step" in extra_dims and "agent_step" not in extra_dims:
            extra_dims["agent_step"] = extra_dims.pop("step")

        for key, value in extra_dims.items():
            if value is None:
                continue
            dims[key] = str(value)
        return dims

    def kpi_timer(
        self,
        name: str,
        *,
        dims: Optional[Dict[str, Any]] = None,
        unit: str = "ms",
    ):
        kpi = get_app_context().get_kpi_writer()
        return kpi.timer(
            name,
            dims=self._kpi_base_dims(dims),
            unit=unit,
            actor=KPIActor(
                type="system",
                groups=getattr(self.runtime_context, "user_groups", None),
            ),
        )

    @property
    def kpi(self):
        """Convenient access to the KPI writer for subclasses."""
        return get_app_context().get_kpi_writer()

    def phase(self, phase: str):
        """Async context manager to time a phase with standard naming."""
        return phase_timer(self.kpi, phase)

    def __str__(self) -> str:
        """String representation of the agent."""
        return f"{self.agent_settings.id}"

    # -----------------------------
    # Tuning field readers (typed)
    # -----------------------------

    def get_field_spec(self, key: str) -> Optional[FieldSpec]:
        ts = self._tuning
        if not ts or not ts.fields:
            return None
        for f in ts.fields:
            if f.key == key:
                return f
        return None

    def get_tuned_any(self, key: str):
        """Return the 'default' value for a tuning field key (whatever type it is), else None."""
        ts = self._tuning
        if not ts or not ts.fields:
            return None
        for f in ts.fields:
            if f.key == key:
                return f.default
        return None

    def get_tuned_number(
        self,
        key: str,
        *,
        default: Optional[float] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        use_spec_bounds: bool = True,
    ) -> Optional[float]:
        """
        Read a tuning field as float.
        - Uses FieldSpec.min/max automatically when use_spec_bounds=True (default).
        - Optional explicit min_value/max_value override the spec bounds if provided.
        """
        raw = self.get_tuned_any(key)

        # parse → float
        if isinstance(raw, (int, float)):
            val: Optional[float] = float(raw)
        elif isinstance(raw, str):
            try:
                val = float(raw.strip())
            except ValueError:
                val = None
        else:
            val = None

        if val is None:
            val = default

        # determine bounds
        spec_min = spec_max = None
        if use_spec_bounds:
            fs = self.get_field_spec(key)
            if fs:
                spec_min = fs.min
                spec_max = fs.max

        lo = min_value if min_value is not None else spec_min
        hi = max_value if max_value is not None else spec_max

        # clamp
        if val is not None:
            if lo is not None and val < lo:
                val = lo
            if hi is not None and val > hi:
                val = hi

        return val

    def get_tuned_int(
        self,
        key: str,
        *,
        default: Optional[int] = None,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
        use_spec_bounds: bool = True,
    ) -> int:
        """
        Read a tuning field as int.
        - If spec provides float min/max, they’re coerced to int bounds:
        min -> ceil(min), max -> floor(max).
        - Optional explicit min_value/max_value override those bounds.
        """
        # 1) get numeric value (float) first
        num = self.get_tuned_number(key, default=None, use_spec_bounds=False)

        # 2) defaulting
        if num is None:
            num = float(default) if default is not None else None

        # 3) figure bounds: spec → explicit overrides
        spec_lo = spec_hi = None
        if use_spec_bounds:
            fs = self.get_field_spec(key)
            if fs:
                # coerce float spec bounds to integer-safe bounds
                spec_lo = math.ceil(fs.min) if fs.min is not None else None
                spec_hi = math.floor(fs.max) if fs.max is not None else None

        lo = min_value if min_value is not None else spec_lo
        hi = max_value if max_value is not None else spec_hi

        # 4) clamp in integer space
        if num is None:
            return default if default is not None else 0
        val = int(num)  # truncate toward zero; you can use round() if preferred
        if lo is not None and val < lo:
            val = lo
        if hi is not None and val > hi:
            val = hi
        return val

    def hydrate_state(self, input_data: AgentInputArgsV1) -> Dict[str, Any]:
        """
        Maps AgentInputV1 into the specific TypedDict of the agent.
        """
        schema = self.get_state_schema()
        # Inspect the TypedDict keys
        expected_keys = get_type_hints(schema).keys()

        # 1. Start with the mandatory message history
        initial_state = {"messages": [HumanMessage(content=input_data.request_text)]}

        # 2. Automatically map parameters and context
        for key in expected_keys:
            if key == "messages":
                continue

            # Priority 1: Direct parameters (e.g., research_depth)
            if key in input_data.parameters:
                initial_state[key] = input_data.parameters[key]

            # Priority 2: Contextual references (e.g., project_id)
            elif hasattr(input_data.context, key):
                val = getattr(input_data.context, key)
                if val:
                    initial_state[key] = val

        return initial_state

    def get_state_schema(self) -> Type:
        """Returns the State TypedDict class."""
        # This can be automated by looking at the _build_graph call
        # or explicitly defined by the dev.
        raise NotImplementedError("Subclasses must define the state_schema")
