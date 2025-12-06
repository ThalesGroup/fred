from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

from jsonschema import Draft7Validator
from langchain.agents import AgentState, create_agent
from langchain.agents.structured_output import ProviderStrategy
from langchain.tools import tool
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agentic_backend.agents.knowledge_extractor.knowledge_extractor import globalSchema
from agentic_backend.agents.knowledge_extractor.powerpoint_template_util import (
    fill_slide_from_structured_response,
)
from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.kf_agent_asset_client import AssetRetrievalError
from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import (
    AgentTuning,
    FieldSpec,
    MCPServerRef,
    UIHints,
)
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.chatbot.chat_schema import (
    LinkKind,
    LinkPart,
    MessagePart,
    TextPart,
)
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)
TUNING = AgentTuning(
    role="Powerpoint Maker",
    description="Extracts information from project documents to fill a given PowerPoint template.",
    mcp_servers=[MCPServerRef(name="mcp-knowledge-flow-mcp-text")],
    tags=[],
    fields=[
        FieldSpec(
            key="ppt.template_key",
            type="text",
            title="PowerPoint Template Key",
            description="Agent asset key for the .pptx template.",
            ui=UIHints(group="PowerPoint"),
            default="ppt_template.pptx",
        ),
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description=(
                "High-level instructions for the agent. "
                "State the mission, how to use the available tools, and constraints."
            ),
            required=True,
            default=(
                "Tu es un agent spécialisé dans l'extraction d'informations structurées depuis des documents via RAG afin de templétiser des documents (powerpoint, word...).\n"
                "Tu dispose d'outil pour faire des recherches dans une base documentaire et d'un outils de templetisation pour soumettre ton travail.Respecte le format attendu d'entrée de l'outils (un JSON Schema où chaque champ contient une `description` précisant l'information attendue).\n"
                "## Ton Processus:\n"
                "- Analyse du schéma : Lis attentivement la `description` de chaque champ ET sa contrainte `maxLength` pour comprendre exactement"
                "ce qui est attendu\n"
                "- Requêtes RAG ciblées : Formule une requête précise basée sur les descriptions des champs à chaque fois que c'est nécessaire\n"
                "- Extraction fidèle : Récupère les informations depuis les documents retournés\n"
                "- Validation des contraintes : Vérifie et ajuste les longueurs/valeurs selon le schéma\n"
                "- Remplissage du JSON : Peuple chaque champ avec les données extraites\n"
                "## Règles d'Extraction:\n"
                "Chaque champ a une `description` qui définit exactement ce qu'il faut extraire\n"
                "Base tes requêtes RAG sur ces descriptions\n"
                "Exemple de schéma:\n"
                "{{\n"
                '  "client_name": {{\n'
                '    "type": "string",\n'
                '    "description": "Nom complet du client tel que mentionné dans le contrat",\n'
                '    "maxLength": 100\n'
                "  }}\n"
                "}}\n"
                '→ Requête RAG :"Quel est le nom complet du client dans le contrat ?"\n'
                "### Fidélité Absolue\n"
                "- ✅ Extrais UNIQUEMENT depuis les documents RAG\n"
                "- ❌ N'invente JAMAIS de données\n"
                "- ❌ N'utilise pas ta connaissance générale\n"
                "### 🚨 RESPECT STRICT DES LONGUEURS - CRITIQUE\n"
                "**SI `maxLength` est renseigné** et que le texte extrait dépasse `maxLength` : **RESUME INTELLIGEMMENT**\n"
                "### Optimisation des requêtes RAG\n"
                "- Multiplie les recherches si nécessaire\n"
                "- Regroupe les champs similaires si pertinent\n"
                '- Évite les requêtes trop larges ("tout sur le document")\n'
                "- Privilégie la précision sur l'exhaustivité\n"
                "## Ton Attitude\n"
                "- Méthodique : traite chaque champ systématiquement. Si tu ne trouve pas une information fais une recherche spécialisée\n"
                "- Précis : base-toi sur les descriptions fournies\n"
                "- Rigoureux : les contraintes de longueur sont NON NÉGOCIABLES\n"
                "- Honnête : si l'information n'existe pas, ne mets rien\n"
                "- Efficace : formule de **MULTIPLES** requêtes RAG ciblées et pertinentes\n"
                "# IMPORTANT: Utilises un 'top_k' de 5 et une 'search_policy' de 'semantic'. N'utilise pas 'document_library_tags_ids'.\n"
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ],
)


class TemplateExpert(AgentFlow):
    tuning = TUNING

    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context=runtime_context)

        # Initialize MCP runtime
        self.mcp = MCPRuntime(
            agent=self,
        )
        await self.mcp.init()

    async def aclose(self):
        await self.mcp.aclose()

    def get_compiled_graph(self) -> CompiledStateGraph:
        template_tool = self.get_template_tool()

        return create_agent(
            model=get_default_chat_model(),
            system_prompt=self.render(self.get_tuned_text("prompts.system") or ""),
            tools=[template_tool, *self.mcp.get_tools()],
            checkpointer=self.streaming_memory,
        )

    def get_template_tool(self):
        tool_schema = {
            "type": "object",
            "properties": {
                "data": globalSchema,  # todo: get it by parsing a tuning field
            },
            "required": ["data"],
        }

        @tool(args_schema=tool_schema)
        async def template_tool(data: dict):
            """
            Outil permettant de templétiser le fichier envoyé par l'utilisateur.
            La nature du fichier importe peu tant que le format des données est respecté. Tu n'as pas besoin de préciser quel fichier,
            l'outil possede déjà cette information.
            """
            # 1. Fetch template from secure asset storage
            template_key = (
                self.get_tuned_text("ppt.template_key") or "simple_template.pptx"
            )
            template_path = await self.fetch_asset_blob_to_tempfile(
                template_key, suffix=".pptx"
            )

            # 2. Save the modified presentation to a temp file
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".pptx", prefix="result_"
            ) as out:
                output_path = Path(out.name)
                fill_slide_from_structured_response(template_path, data, output_path)

            # 3. Upload the generated asset to user storage
            user_id_to_store_asset = self.get_end_user_id()
            final_key = f"{user_id_to_store_asset}_{output_path.name}"

            with open(output_path, "rb") as f_out:
                upload_result = await self.upload_user_asset(
                    key=final_key,
                    file_content=f_out,
                    filename=f"Generated_Slide_{self.get_name()}.pptx",
                    content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    user_id_override=user_id_to_store_asset,
                )

            # 4. Construct the structured message for the UI
            final_download_url = self.get_asset_download_url(
                asset_key=upload_result.key, scope="user"
            )

            return LinkPart(
                href=final_download_url,
                title=f"Download {upload_result.file_name}",
                kind=LinkKind.download,
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )

        return template_tool
