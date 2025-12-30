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
# -----------------------------------------------------------------------------
# ContentSave — An agent that generates content and saves it to user assets,
# then returns a download link to the user.
# This example demonstrates how to upload generated files and provide secure access.
# -----------------------------------------------------------------------------

from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO
from typing import List, TypedDict

from langchain_core.messages import AIMessage, AnyMessage
from langgraph.graph import END, START, StateGraph

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

# --- Defaults ---
DEFAULT_CONTENT_PROMPT = "Generate a sample report in plain text format."
DEFAULT_FILENAME = "generated_content.txt"
DEFAULT_ASSET_KEY = "generated_content"


# 1. Declare the Agent's state structure
class ContentSaveState(TypedDict):
    """The state tracking conversation messages."""

    messages: List[AnyMessage]
    _generated_content: str  # Internal field to hold generated content
    question: str


# 2. Declare tunables
TUNING = AgentTuning(
    role="content_save",
    description="An agent that generates content, saves it to user assets, and provides a download link.",
    tags=["academy"],
    fields=[
        FieldSpec(
            key="content.prompt",
            type="text",
            title="Content Generation Prompt",
            description="The prompt for the LLM to generate content.",
            default=DEFAULT_CONTENT_PROMPT,
            ui=UIHints(group="Content Generation"),
        ),
        FieldSpec(
            key="content.filename",
            type="text",
            title="Output Filename",
            description="The filename for the saved asset (e.g., 'report.txt').",
            default=DEFAULT_FILENAME,
            ui=UIHints(group="Content Generation"),
        ),
        FieldSpec(
            key="content.asset_key",
            type="text",
            title="Asset Key",
            description="The logical key to store the asset (e.g., 'my_report'). Defaults to filename without extension.",
            default=DEFAULT_ASSET_KEY,
            ui=UIHints(group="Content Generation"),
        ),
    ],
)


@expose_runtime_source("agent.ContentSave")
class ContentSave(AgentFlow):
    tuning = TUNING
    _graph: StateGraph | None = None

    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)
        self.model = get_default_chat_model()
        self._graph = self._build_graph()
        logger.info(
            "ContentSaveAgent initialized with content generation and asset upload."
        )

    def _build_graph(self) -> StateGraph:
        """The agent's state machine: START -> generate_node -> upload_node -> END."""
        g = StateGraph(ContentSaveState)
        g.add_node("generate_node", self.generate_node)
        g.add_node("upload_node", self.upload_node)
        g.add_edge(START, "generate_node")
        g.add_edge("generate_node", "upload_node")
        g.add_edge("upload_node", END)
        return g

    async def generate_node(self, state: ContentSaveState) -> ContentSaveState:
        """
        Node 1: Generate content using the LLM based on the configured prompt.
        """
        prompt = self.get_tuned_text("content.prompt") or DEFAULT_CONTENT_PROMPT

        try:
            # Call the LLM to generate content
            response = await self.model.ainvoke([{"role": "user", "content": prompt}])
            logger.info(f"LLM response type: {type(response)}, content: {response}")

            generated_content = self._get_text_content(response)
            logger.info(
                f"Extracted content: '{generated_content}' (length: {len(generated_content)})"
            )

            # Store the generated content in the state
            state["_generated_content"] = generated_content
            logger.info(
                f"Content generated successfully. Length: {len(generated_content)}"
            )
        except Exception as e:
            logger.error(f"Failed to generate content: {e}", exc_info=True)
            error_msg = f"[Content Generation Error: {e}]"
            state["_generated_content"] = error_msg

        state["question"] = prompt

        return state

    async def upload_node(self, state: ContentSaveState) -> ContentSaveState:
        """
        Node 2: Upload the generated content to user assets and return a download link.
        """
        generated_content = state.get("_generated_content", "")
        question = "Question : " + state.get("question", "") + "\n\n"
        filename = self.get_tuned_text("content.filename") or DEFAULT_FILENAME
        asset_key = self.get_tuned_text("content.asset_key") or DEFAULT_ASSET_KEY

        logger.info(f"Upload node received content length: {len(generated_content)}")

        # Check for generation errors
        if generated_content.startswith("[Content Generation Error:"):
            response_msg = f"Failed to generate content: {generated_content}"
            ai_response = AIMessage(content=response_msg)
            return self.delta(ai_response)

        # Validate we have content
        if not generated_content or len(generated_content.strip()) == 0:
            error_msg = "❌ **Error:** No content was generated."
            ai_response = AIMessage(content=error_msg)
            return self.delta(ai_response)

        try:
            # Convert content to bytes
            file_content = question.encode("utf-8") + generated_content.encode("utf-8")
            logger.info(f"File content size: {len(file_content)} bytes")

            # Add timestamp to make asset key and filename unique
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_asset_key = f"{asset_key}_{timestamp}"
            name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
            unique_filename = (
                f"{name}_{timestamp}.{ext}" if ext else f"{filename}_{timestamp}"
            )

            logger.info(
                f"Using unique asset key: {unique_asset_key}, "
                f"filename: {unique_filename}"
            )

            # Upload the asset to user storage
            upload_result = await self.upload_user_asset(
                key=unique_asset_key,
                file_content=file_content,
                filename=unique_filename,
                content_type="text/plain",
            )

            logger.info(
                f"Content uploaded successfully. Key: {upload_result.key}, "
                f"Size: {upload_result.size}"
            )

            # Construct the download URL
            download_url = self.get_asset_download_url(
                asset_key=upload_result.key, scope="user"
            )

            # Format the response with the download link
            response_content = (
                f"✅ **Success:** Content generated and saved to your assets.\n\n"
                f"**File:** `{upload_result.file_name}`\n"
                f"**Size:** {upload_result.size} bytes\n"
                f"**Key:** `{upload_result.key}`\n\n"
                f"[📥 Download File]({download_url})"
            )

            ai_response = AIMessage(content=response_content)
            return self.delta(ai_response)

        except Exception as e:
            logger.error(f"Failed to upload content: {e}", exc_info=True)
            error_msg = f"❌ **Error:** Failed to upload content to assets: {str(e)}"
            ai_response = AIMessage(content=error_msg)
            return self.delta(ai_response)
