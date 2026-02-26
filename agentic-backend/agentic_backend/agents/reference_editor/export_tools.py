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

"""Export tools for Reference Editor agent - template filling and file upload."""

import logging
import tempfile
from datetime import datetime
from pathlib import Path

from langchain.tools import tool
from pydantic import ValidationError

from agentic_backend.agents.reference_editor.powerpoint_template_util import (
    fill_slide_from_structured_response_async,
    fill_word_from_structured_response_async,
)
from agentic_backend.agents.reference_editor.pydantic_models import (
    Contexte,
    InformationsProjet,
    SyntheseProjet,
)
from agentic_backend.common.kf_base_client import KfBaseClient
from agentic_backend.common.kf_vectorsearch_client import VectorSearchClient
from agentic_backend.core.chatbot.chat_schema import LinkKind, LinkPart

logger = logging.getLogger(__name__)


def _validate_sections(data: dict) -> list[str]:
    """Validate each section with its Pydantic model. Returns a list of errors (empty if valid)."""
    actual_data = data.get("data", data)
    errors = []
    for section_name, model_cls in [
        ("informationsProjet", InformationsProjet),
        ("contexte", Contexte),
        ("syntheseProjet", SyntheseProjet),
    ]:
        try:
            model_cls.model_validate(actual_data.get(section_name, {}))
        except ValidationError as e:
            for err in e.errors():
                field = ".".join(str(loc) for loc in err["loc"])
                errors.append(f"{section_name}.{field}: {err['msg']}")
    return errors


class ExportTools:
    """Helper class to organize reference editor export tools."""

    def __init__(self, agent):
        self.agent = agent

    def _build_tool_schema(self):
        """Build the tool schema from Pydantic models, following ppt_filler pattern."""
        return {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "properties": {
                        "informationsProjet": {"$ref": "#/$defs/InformationsProjet"},
                        "contexte": {"$ref": "#/$defs/Contexte"},
                        "syntheseProjet": {"$ref": "#/$defs/SyntheseProjet"},
                    },
                    "required": ["informationsProjet", "contexte", "syntheseProjet"],
                },
            },
            "required": ["data"],
            "$defs": {
                "InformationsProjet": InformationsProjet.model_json_schema(),
                "Contexte": Contexte.model_json_schema(),
                "SyntheseProjet": SyntheseProjet.model_json_schema(),
            },
        }

    def get_ppt_template_tool(self):
        """Create the PowerPoint template tool."""
        tool_schema = self._build_tool_schema()

        @tool(args_schema=tool_schema)
        async def ppt_template_tool(data: dict):
            """
            Outil permettant de templétiser le fichier envoyé par l'utilisateur.
            La nature du fichier importe peu tant que le format des données est respecté. Tu n'as pas besoin de préciser quel fichier,
            l'outil possède déjà cette information.
            L'outil retourne un LinkPart pour l'interface. Ne jamais réécrire ce lien en texte/Markdown.
            """
            # 0. Validate data before proceeding
            validation_errors = _validate_sections(data)
            if validation_errors:
                error_list = "\n".join(f"- {e}" for e in validation_errors)
                return f"❌ Validation échouée. Corrige les champs puis réessaie:\n{error_list}"

            output_path = None
            try:
                # 1. Fetch template from secure asset storage
                template_key = (
                    self.agent.get_tuned_text("ppt.template_key")
                    or "simple_template.pptx"
                )
                template_path = await self.agent.fetch_config_blob_to_tempfile(
                    template_key, suffix=".pptx"
                )

                # 2. Fill the template into a temp file
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".pptx", prefix="result_"
                ) as out:
                    output_path = Path(out.name)

                actual_data = data.get("data", data)
                vector_search_client = VectorSearchClient(agent=self.agent)
                search_options = self.agent.build_vector_search_scope_options()
                kf_base_client = KfBaseClient(
                    allowed_methods=frozenset({"GET", "POST"}), agent=self.agent
                )
                await fill_slide_from_structured_response_async(
                    template_path,
                    actual_data,
                    output_path,
                    vector_search_client,
                    kf_base_client,
                    search_options=search_options,
                )

                # 3. Upload the generated file to user storage
                timestamp = datetime.now().strftime("%m%d%H%M")
                final_key = f"Reference_{timestamp}.pptx"

                with open(output_path, "rb") as f_out:
                    upload_result = await self.agent.upload_user_blob(
                        key=final_key,
                        file_content=f_out,
                        filename=final_key,
                        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    )

                # 4. Return structured download link for the UI
                return LinkPart(
                    href=upload_result.download_url,
                    title=f"Download {upload_result.file_name}",
                    kind=LinkKind.download,
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                ).model_dump(mode="json")
            except Exception as e:
                error_msg = f"❌ Erreur lors de la génération du PowerPoint: {e}"
                logger.error(f"[ppt_template_tool] {error_msg}", exc_info=True)
                return error_msg
            finally:
                if output_path:
                    output_path.unlink(missing_ok=True)

        return ppt_template_tool

    def get_word_template_tool(self):
        """Create the Word template tool."""
        tool_schema = self._build_tool_schema()

        @tool(args_schema=tool_schema)
        async def word_template_tool(data: dict):
            """
            Outil permettant de templétiser un fichier Word envoyé par l'utilisateur.
            La nature du fichier importe peu tant que le format des données est respecté. Tu n'as pas besoin de préciser quel fichier,
            l'outil possède déjà cette information.
            L'outil retourne un LinkPart pour l'interface. Ne jamais réécrire ce lien en texte/Markdown.
            """
            # 0. Validate data before proceeding
            validation_errors = _validate_sections(data)
            if validation_errors:
                error_list = "\n".join(f"- {e}" for e in validation_errors)
                return f"❌ Validation échouée. Corrige les champs puis réessaie:\n{error_list}"

            output_path = None
            try:
                # 1. Fetch template from secure asset storage
                template_key = (
                    self.agent.get_tuned_text("word.template_key")
                    or "simple_template.docx"
                )
                template_path = await self.agent.fetch_config_blob_to_tempfile(
                    template_key, suffix=".docx"
                )

                # 2. Fill the template into a temp file
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".docx", prefix="result_"
                ) as out:
                    output_path = Path(out.name)

                actual_data = data.get("data", data)
                vector_search_client = VectorSearchClient(agent=self.agent)
                search_options = self.agent.build_vector_search_scope_options()
                kf_base_client = KfBaseClient(
                    allowed_methods=frozenset({"GET", "POST"}), agent=self.agent
                )
                await fill_word_from_structured_response_async(
                    template_path,
                    actual_data,
                    output_path,
                    vector_search_client,
                    kf_base_client,
                    search_options=search_options,
                )

                # 3. Upload the generated file to user storage
                timestamp = datetime.now().strftime("%m%d%H%M")
                final_key = f"Reference_{timestamp}.docx"

                with open(output_path, "rb") as f_out:
                    upload_result = await self.agent.upload_user_blob(
                        key=final_key,
                        file_content=f_out,
                        filename=final_key,
                        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )

                # 4. Return structured download link for the UI
                return LinkPart(
                    href=upload_result.download_url,
                    title=f"Download {upload_result.file_name}",
                    kind=LinkKind.download,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ).model_dump(mode="json")
            except Exception as e:
                error_msg = f"❌ Erreur lors de la génération du document Word: {e}"
                logger.error(f"[word_template_tool] {error_msg}", exc_info=True)
                return error_msg
            finally:
                if output_path:
                    output_path.unlink(missing_ok=True)

        return word_template_tool
