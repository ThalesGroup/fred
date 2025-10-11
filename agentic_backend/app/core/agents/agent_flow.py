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
from datetime import datetime
from importlib.resources import files
from typing import ClassVar, List, Optional, Sequence, cast

from langchain_core.messages import AIMessage, AnyMessage, BaseMessage, SystemMessage
from langchain_core.runnables import Runnable
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import MessagesState
from langgraph.graph.state import CompiledStateGraph

from app.application_context import (
    get_app_context,
    get_knowledge_flow_base_url,
)
from app.common.kf_agent_asset_client import AssetRetrievalError, KfAgentAssetClient
from app.common.structures import (
    AgentChatOptions,
    AgentSettings,
    ChatContextMessage,
)
from app.core.agents.agent_spec import AgentTuning, FieldSpec
from app.core.agents.agent_state import Prepared, resolve_prepared
from app.core.agents.runtime_context import RuntimeContext

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

    # Subclasses MUST override this with a concrete AgentTuning
    tuning: ClassVar[Optional[AgentTuning]] = None
    default_chat_options: ClassVar[Optional[AgentChatOptions]] = None

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
        self.runtime_context: Optional[RuntimeContext] = None
        self.asset_client = KfAgentAssetClient()

    async def async_init(self):
        """
        Asynchronous initialization routine that must be implemented by subclasses.
        """
        pass

    def apply_settings(self, new_settings: AgentSettings) -> None:
        """
        Live update (hot-swap) the effective configuration of this instance.

        Why:
        - The user may edit tuning fields from the UI; the controller persists and
          calls this so the running instance reflects the latest values.

        Behavior:
        - Replace in-memory `AgentSettings`.
        - Re-resolve `_tuning`: use `new_settings.tuning` when available, otherwise fall
          back to the class-level `tuning` defaults.
        - Note: this does not recompile the graph or rebuild models; call your own
          re-init logic if tuneables require it.
        """
        merged_settings = type(self).merge_settings_with_class_defaults(new_settings)
        self.agent_settings = merged_settings
        self._tuning = merged_settings.tuning
        self.agent_settings.tuning = self._tuning

    @staticmethod
    def _ensure_any_message(msg: object) -> AnyMessage:
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
        return self._ensure_any_message(raw)

    @staticmethod
    def delta(*msgs: AnyMessage) -> MessagesState:
        """Return a MessagesState-compatible state update."""
        # Note: You need to ensure MessagesState is imported correctly from langgraph.graph
        return {"messages": list(msgs)}

    @classmethod
    def merge_settings_with_class_defaults(
        cls, settings: AgentSettings
    ) -> AgentSettings:
        """Return a copy of settings augmented with class-level defaults."""

        merged = settings.model_copy(deep=True)

        resolved_tuning = merged.tuning or cls.tuning
        if resolved_tuning is not None:
            merged.tuning = resolved_tuning.model_copy(deep=True)

        merged.chat_options = cls._merge_chat_options(merged.chat_options)
        return merged

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

    def get_name(self) -> str:
        """
        Return the agent's name.
        This is the primary identifier for the agent. In particular, it is used
        to identify the agent in a leader's crew.
        """
        return self.agent_settings.name

    def get_description(self) -> str:
        """
        Return the agent's description. This is key for the leader to decide
        which agent to delegate to.
        """
        return self.agent_settings.description

    def get_role(self) -> str:
        """
        Return the agent's role. This defines the agent's primary function and
        responsibilities within the system.
        """
        return self.agent_settings.role

    def get_tags(self) -> List[str]:
        """
        Return the agent's tags. Tags are used for categorization and
        discovery in the UI. It is also used by leaders to select agents
        for their crew based on required skills.
        """
        return self.agent_settings.tags or []

    def get_tuning_spec(self) -> Optional[AgentTuning]:
        """
        Return the class-declared tuning spec (the *schema* of tunables).
        Why not the resolved values? Because the UI needs the spec to render fields.
        Current values live in `self._tuning` and are read via `get_tuned_text(...)`.
        """
        return self.tuning

    async def read_bundled_file(self, filename: str) -> str:
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
            raise AssetRetrievalError(error_msg)

        except Exception as e:
            error_msg = (
                f"Failed to read bundled file '{filename}' in '{agent_module_name}'. "
                f"Details: {type(e).__name__}: {e}"
            )
            logger.error(error_msg, exc_info=True)
            raise AssetRetrievalError(error_msg)

    async def fetch_asset_content(self, asset_key: str) -> str:
        """
        Retrieves the content of a user-uploaded asset securely and cleanly.

        """
        agent_name = self.get_name()
        try:
            return await get_app_context().run_in_executor(
                self.asset_client.fetch_asset_content_text, agent_name, asset_key
            )
        except AssetRetrievalError as e:
            logger.error(f"Failed to fetch asset for agent: {e}")
            # Re-raise the error, or return a default/fail state
            return f"[Asset Retrieval Error: {e.args[0]}]"
        except Exception as e:
            logger.error(f"Unexpected error fetching asset for agent: {e}")
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

    def chat_context_text(self) -> str:
        """
        Return the *chat context* text from the runtime context (if any).

        When to use:
        - Only when a node explicitly needs chat context info (e.g., tone/role constraints
          about the user). We DO NOT auto-merge this into every prompt.

        Contract:
        - If your agent ignores chat context, simply don't call this method.
        """
        ctx = self.get_runtime_context() or RuntimeContext()
        prepared: Prepared = resolve_prepared(ctx, get_knowledge_flow_base_url())
        return (prepared.prompt_chat_context_text or "").strip()

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
        return [SystemMessage(content=system_text), *messages]

    def with_chat_context_text(
        self, messages: Sequence[AnyMessage]
    ) -> list[AnyMessage]:
        """
        Wrap the chat context description in a SystemMessage at the end of the messages.

        Why:
        - Force the system to take it into account.

        """
        messages = [msg for msg in messages if not isinstance(msg, ChatContextMessage)]
        chat_context = self.chat_context_text()
        if not chat_context:
            return list(messages)
        messages.append(ChatContextMessage(content=chat_context))
        return messages

    def get_compiled_graph(self) -> CompiledStateGraph:
        """
        Compile and return the agent's graph (idempotent).
        Subclasses must set `self._graph` in async_init().
        """
        if self.compiled_graph is not None:
            return self.compiled_graph
        if self._graph is None:
            # Strong, early signal to devs wiring the agent: you must build the graph in async_init()
            raise RuntimeError(
                f"{type(self).__name__}: _graph is None. Did you forget to set it in async_init()?"
            )
        self.compiled_graph = self._graph.compile(checkpointer=self.streaming_memory)
        return self.compiled_graph

    def set_runtime_context(self, context: RuntimeContext) -> None:
        """Set the runtime context for this agent."""
        self.runtime_context = context

    def get_runtime_context(self) -> Optional[RuntimeContext]:
        """Get the current runtime context."""
        return self.runtime_context

    def __str__(self) -> str:
        """String representation of the agent."""
        return f"{self.agent_settings.name}"

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
