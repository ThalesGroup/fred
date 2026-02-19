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
from typing import Sequence

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
)

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from agentic_backend.core.agents.runtime_context import get_language
from agentic_backend.core.agents.simple_agent_flow import SimpleAgentFlow
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

TUNING = AgentTuning(
    role="Broad and general knowledge assistant",
    description="Fallback generalist expert used to handle broad queries when no specialist applies.",
    tags=["fallback"],
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description=(
                "Sets Georges' base persona and boundaries. "
                "Adjust to shift tone/voice or emphasize constraints."
            ),
            required=True,
            default=(
                "You are a friendly generalist expert, skilled at providing guidance on a wide range "
                "of topics without deep specialization.\n"
                "Your role is to respond with clarity, providing accurate and reliable information.\n"
                "When appropriate, highlight elements that could be particularly relevant.\n"
                "In case of graphical representation, render mermaid diagrams code."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ],
)


@expose_runtime_source("agent.Georges")
class Georges(SimpleAgentFlow):
    """
    The Generalist/Fallback Expert. Simplified to a single-step LLM call
    without a LangGraph wrapper.
    """

    tuning = TUNING

    def __init__(self, *args, **kwargs):
        # The SimpleAgentFlow base class would handle setting self.agent_settings
        super().__init__(*args, **kwargs)
        # Bind the model directly in __init__ if it's not resource-heavy,
        # or rely on SimpleAgentFlow's initialization
        self.model = get_default_chat_model()

    async def arun(self, messages: Sequence[AnyMessage]) -> AIMessage:
        """
        The core single-step execution for a SimpleAgentFlow.
        Takes the current message history and returns the response message.
        """
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Georges.arun START. Input message count: %s", len(messages))
            logger.debug("Georges.arun Input messages: %s", messages)

        # 1) Get the tuned system prompt
        tpl = self.get_tuned_text("prompts.system") or ""

        # 2) Render tokens (like {user_name}, etc.)
        sys = self.render(tpl)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Georges: Rendered final system prompt (len=%s).", len(sys))
            logger.debug("Georges: System prompt: %s", sys[:100] + "...")

        # 3) Prepend the system prompt to the messages
        llm_messages = self.with_system(sys, messages)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Georges: Messages after adding system prompt. Count: %s",
                len(llm_messages),
            )

        # 4) Optionally add the chat context text (if available)
        chat_context = await self.chat_context_text()
        include_chat_context = self.get_field_spec(
            "prompts.include_chat_context"
        ) is None or bool(self.get_tuned_any("prompts.include_chat_context"))
        response_language = get_language(self.get_runtime_context()) or "English"
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "[AGENT] Georges prompt check: response_language=%s include_chat_context=%s system_prompt=%r chat_context=%r",
                response_language,
                include_chat_context,
                sys,
                chat_context,
            )
        llm_messages = await self.with_chat_context_text(llm_messages)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Georges: Messages after adding context text. Final count: %s",
                len(llm_messages),
            )
            logger.debug(
                "Georges: Final messages sent to LLM: %s",
                [type(m).__name__ for m in llm_messages],
            )

        # 5) Invoke the model
        async with self.phase("llm_invoke"):
            response = await self.model.ainvoke(llm_messages)
        logger.debug("[AGENTS] Georges: LLM call successful (await complete).")
        return self.ensure_aimessage(response)
