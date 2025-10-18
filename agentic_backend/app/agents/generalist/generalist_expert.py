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

from fred_core import get_model
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
)

from app.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from app.core.agents.simple_agent_flow import SimpleAgentFlow
from app.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

TUNING = AgentTuning(
    # ... (TUNING definition remains the same)
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description=(
                "Sets Georges’ base persona and boundaries. "
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
        self.model = get_model(self.agent_settings.model)
        logger.info(f"Georges initialized with model: {self.agent_settings.model}")

    async def arun(self, messages: Sequence[AnyMessage]) -> AIMessage:
        """
        The core single-step execution for a SimpleAgentFlow.
        Takes the current message history and returns the response message.
        """
        logger.debug(f"Georges.arun START. Input message count: {len(messages)}")
        logger.debug(f"Georges.arun Input messages: {messages}")

        # 1) Get the tuned system prompt
        tpl = self.get_tuned_text("prompts.system") or ""

        # 2) Render tokens (like {agent_name}, {user_name}, etc.)
        sys = self.render(tpl)
        logger.debug(f"Georges: Rendered final system prompt (len={len(sys)}).")
        logger.debug(f"Georges: System prompt: {sys[:100]}...")

        # 3) Prepend the system prompt to the messages
        llm_messages = self.with_system(sys, messages)
        logger.debug(
            f"Georges: Messages after adding system prompt. Count: {len(llm_messages)}"
        )

        # 4) Optionally add the chat context text (if available)
        llm_messages = self.with_chat_context_text(llm_messages)
        logger.debug(
            f"Georges: Messages after adding context text. Final count: {len(llm_messages)}"
        )
        logger.debug(
            f"Georges: Final messages sent to LLM: {[type(m).__name__ for m in llm_messages]}"
        )

        # 5) Invoke the model
        logger.info(
            f"Georges: Invoking model {self.agent_settings.model} asynchronously..."
        )
        try:
            response = await self.model.ainvoke(llm_messages)
            logger.info("Georges: LLM call successful (await complete).")
        except Exception as e:
            logger.error(
                f"Georges: LLM invocation failed with exception: {e}", exc_info=True
            )
            # Raise or return a clear error message if LLM fails
            raise

        return self.ensure_aimessage(response)
