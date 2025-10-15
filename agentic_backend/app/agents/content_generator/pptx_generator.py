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
import os
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional

from fred_core import VectorSearchHit, get_model
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from app.common.rags_utils import (
    attach_sources_to_llm_response,
    ensure_ranks,
    format_sources_for_prompt,
    sort_hits,
)
from app.core.runtime_source import expose_runtime_source

from app.common.structures import AgentChatOptions
from app.common.vector_search_client import VectorSearchClient
from app.core.agents.agent_flow import AgentFlow
from app.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from app.core.agents.runtime_context import (
    get_document_library_tags_ids,
    get_search_policy,
)

# LangChain structured parsing
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import StructuredOutputParser, ResponseSchema

# PowerPoint generation
from pptx import Presentation
from pptx.util import Pt

# Asset / UI parts
from app.core.chatbot.chat_schema import LinkKind, LinkPart, MessagePart, TextPart
from app.common.kf_agent_asset_client import AssetRetrievalError

logger = logging.getLogger(__name__)

# -----------------------------
# Tuning (UI schema)
# -----------------------------
RAG_TUNING = AgentTuning(
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="RAG System Prompt",
            description="Defines assistant behavior and citation style.",
            required=True,
            default=(
                "You answer strictly based on the retrieved document chunks.\n"
                "Extract the project reference information"
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="rag.top_k",
            type="integer",
            title="Top-K Documents",
            description="Number of chunks to retrieve per question.",
            required=False,
            default=6,
            ui=UIHints(group="Retrieval"),
        ),
        FieldSpec(
            key="prompts.include_chat_context",
            type="boolean",
            title="Append Chat Context to System Prompt",
            description="If true, append the runtime chat context text after the system prompt.",
            required=False,
            default=False,
            ui=UIHints(group="Prompts"),
        ),
        FieldSpec(
            key="ppt.template_path",
            type="text",
            title="PowerPoint Template Path",
            description="Filesystem path to the .pptx template used to generate the reference sheet.",
            required=False,
            default="/home/simon/Documents/github_repos/ThalesGroup/fred/agentic_backend/app/agents/content_generator/templates/pptx/template_fiche_ref_projet.pptx",
            ui=UIHints(group="PowerPoint"),
        ),
    ]
)

@expose_runtime_source("agent.SlidShady")
class SlidShady(AgentFlow):
    """
    RAG agent for project reference extraction:
    - Retrieves context chunks via VectorSearchClient
    - Uses StructuredOutputParser for structured fields
    - Generates a PowerPoint reference sheet and provides a download link (LinkPart)
    """

    tuning = RAG_TUNING
    default_chat_options = AgentChatOptions(
        search_policy_selection=True,
        libraries_selection=True,
    )

    async def async_init(self):
        """Initialize model, search client, parser, and prompt."""
        self.model = get_model(self.agent_settings.model)
        self.search_client = VectorSearchClient()
        self._graph = self._build_graph()

        # Structured output schema
        self.response_schemas = [
            ResponseSchema(name="client_presentation_and_context", description="Client presentation and context"),
            ResponseSchema(name="stakes", description="Project stakes"),
            ResponseSchema(name="activities_and_solutions", description="Activities and solutions"),
            ResponseSchema(name="client_benefits", description="Client benefits"),
            ResponseSchema(name="strengths", description="Strengths"),
            ResponseSchema(name="tech_list", description="List of technologies used"),
        ]
        self.parser = StructuredOutputParser.from_response_schemas(self.response_schemas)
        self.format_instructions = self.parser.get_format_instructions()

        # Prompt template (langchain)
        self.prompt_template = ChatPromptTemplate.from_template("""
            You are an assistant that reads project documents.
            Extract the following information:
            1. Client presentation and context
            2. Project stakes
            3. Activities and solutions
            4. Benefits for the client
            5. Project strengths
            6. List of technologies used

            No field should remain empty unless the information is completely missing.
            The content of each field should be concise (3 to 5 points maximum).

            Return only in the following format:
            {format_instructions}

            Context:
            {context}
            """)

        logger.info("SlidesExpert initialized with structured output parsing enabled.")

    # -----------------------------
    # Graph definition
    # -----------------------------
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", self._run_reasoning_step)
        builder.add_edge(START, "reasoner")
        builder.add_edge("reasoner", END)
        return builder

    # -----------------------------
    # Internal helpers
    # -----------------------------
    def _system_prompt(self) -> str:
        """Retrieve tuned system prompt."""
        sys_tpl = self.get_tuned_text("prompts.system")
        if not sys_tpl:
            logger.warning("SlidesExpert: no tuned system prompt found.")
            raise RuntimeError("Missing system prompt.")
        return self.render(sys_tpl)

    def _fill_ppt_template(self, output_data: Dict[str, str], project_name: str) -> Path:
        """
        Fill a PowerPoint template with extracted fields and write to a temporary file.
        Returns the Path to the generated pptx file (caller must clean it up).
        """
        # Prefer configured template path, fallback to bundled path if not present
        template_path = self.get_tuned_text("ppt.template_path") or ""
        if not template_path or not os.path.exists(template_path):
            logger.warning("Configured template not found at '%s'. Trying default path.", template_path)
            template_path = "/home/simon/Documents/github_repos/ThalesGroup/fred/agentic_backend/app/agents/content_generator/templates/pptx/template_fiche_ref_projet.pptx"

        if not os.path.exists(template_path):
            raise FileNotFoundError(f"PowerPoint template not found: {template_path}")

        # Create a temp output file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pptx", prefix=f"fiche_{project_name}_") as out:
            output_path = Path(out.name)

        prs = Presentation(template_path)

        # We assume the first slide contains placeholders with fixed indexes.
        # If the template differs, placeholder indexes must be adjusted via tuning.
        slide = prs.slides[0]

        mapping = {
            "client_presentation_and_context": 10,
            "stakes": 11,
            "activities_and_solutions": 12,
            "client_benefits": 13,
            "strengths": 14,
            "tech_list": 15,
        }

        for key, ph_idx in mapping.items():
            try:
                placeholder = slide.placeholders[ph_idx]
                if not getattr(placeholder, "has_text_frame", False):
                    continue
                textbox = placeholder.text_frame  # type: ignore[attr-defined]
                textbox.clear()
                p = textbox.add_paragraph()
                p.text = output_data.get(key, "")
                p.font.size = Pt(10)
            except IndexError:
                logger.warning("Placeholder index %s not found on slide for key %s", ph_idx, key)
            except Exception as e:
                logger.warning("Error filling placeholder %s for key %s: %s", ph_idx, key, e)

        prs.save(str(output_path))
        logger.info("PowerPoint generated: %s", output_path)
        return output_path

    # -----------------------------
    # Node: reasoner
    # -----------------------------
    async def _run_reasoning_step(self, state: MessagesState):
        if self.model is None:
            raise RuntimeError("Model not initialized. Call async_init().")

        last = state["messages"][-1]
        if not isinstance(last.content, str):
            raise TypeError("Expected string content for the last message.")
        question = last.content

        try:
            # 1) Retrieval context
            doc_tag_ids = get_document_library_tags_ids(self.get_runtime_context())
            search_policy = get_search_policy(self.get_runtime_context())
            top_k = self.get_tuned_int("rag.top_k", default=6)

            # 2) Retrieve via vector search
            hits: List[VectorSearchHit] = self.search_client.search(
                question=question,
                top_k=top_k,
                document_library_tags_ids=doc_tag_ids,
                search_policy=search_policy,
            )

            if not hits:
                warn = "I did not find any relevant documents. Try rephrasing your question."
                messages = self.with_chat_context_text([HumanMessage(content=warn)])
                return {"messages": [await self.model.ainvoke(messages)]}

            # 3) Normalize hits
            hits = sort_hits(hits)
            ensure_ranks(hits)

            # 4) Build prompt for structured extraction
            sys_msg = SystemMessage(content=self._system_prompt())
            context_text = format_sources_for_prompt(hits, snippet_chars=1200)
            human_msg = HumanMessage(
                content=self.prompt_template.format_messages(
                    format_instructions=self.format_instructions,
                    context=context_text,
                )[0].content
            )

            messages = [sys_msg, human_msg]
            messages = self.with_chat_context_text(messages)

            # 5) Ask the model for structured output
            answer_msg = await self.model.ainvoke(messages)
            answer_text = getattr(answer_msg, "content", "")
            logger.debug("Raw model answer: %s", answer_text)

            # 6) Parse structured data
            try:
                structured_data = self.parser.parse(answer_text)
            except Exception as e:
                logger.warning("Failed to parse structured output: %s", e)
                structured_data = {"raw_text": answer_text}

            # 7) Attach metadata for UI
            attach_sources_to_llm_response(answer_msg, hits)

            # 8) Generate PPTX file from extracted structured data
            project_name = "project_auto"
            ppt_path: Optional[Path] = None
            try:
                ppt_path = self._fill_ppt_template(structured_data, project_name)
            except Exception as e:
                logger.exception("Failed to generate PPTX: %s", e)
                error_msg = AIMessage(content=f"❌ Error generating PowerPoint: {e}")
                return {"messages": [answer_msg, error_msg], "structured_data": structured_data}

            # 9) Upload generated PPT to user asset storage and prepare structured LinkPart
            try:
                user_id = self.get_end_user_id()
                final_key = f"{user_id}_{ppt_path.name}"
                logger.info(f"override user_id: {user_id}")
                with open(ppt_path, "rb") as f:
                    upload_result = await self.upload_user_asset(
                        key=final_key,
                        file_content=f,
                        filename=f"fiche_ref_{project_name}.pptx",
                        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        user_id_override=user_id,
                    )

                download_url = self.get_asset_download_url(asset_key=upload_result.key, scope="user")

                parts: List[MessagePart] = [
                    TextPart(text="✅ Slides generated successfully."),
                    LinkPart(
                        href=download_url,
                        title=f"Download {upload_result.file_name}",
                        kind=LinkKind.download,
                        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    ),
                ]

                ai_msg = AIMessage(content="", parts=parts)

                return {"messages": [ai_msg], "structured_data": structured_data}

            except AssetRetrievalError as e:
                logger.exception("Asset retrieval/upload error: %s", e)
                return {"messages": [AIMessage(content=f"❌ Upload error: {e}")], "structured_data": structured_data}
            except Exception as e:
                logger.exception("Unexpected error during upload: %s", e)
                return {"messages": [AIMessage(content=f"❌ Unexpected error during upload: {e}")], "structured_data": structured_data}
            finally:
                if ppt_path and ppt_path.exists():
                    try:
                        ppt_path.unlink(missing_ok=True)
                    except Exception:
                        logger.debug("Could not delete temporary ppt at %s", ppt_path)

        except Exception:
            logger.exception("SlidesExpert: error in reasoning step.")
            fallback = await self.model.ainvoke(
                [HumanMessage(content="An error occurred while extracting the information.")]
            )
            return {"messages": [fallback]}
