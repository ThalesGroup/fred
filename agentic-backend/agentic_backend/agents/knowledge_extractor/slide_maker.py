from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from jsonschema import Draft7Validator
from langchain.agents import create_agent
from langchain.tools import tool
from langgraph.graph.state import CompiledStateGraph

from agentic_backend.agents.knowledge_extractor.knowledge_extractor import globalSchema
from agentic_backend.agents.knowledge_extractor.powerpoint_template_util import (
    fill_slide_from_structured_response,
)
from agentic_backend.application_context import get_default_chat_model
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
)

logger = logging.getLogger(__name__)

# --- Configuration & Tuning ---
# ------------------------------
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
            default="""
Tu es un agent d'extraction d'informations structurées depuis des documents. Tu remplis un PowerPoint templétisé.
Tu disposes d'un outil pour faire des recherches dans une base documentaire et d'un outil de templetisation pour soumettre ton travail.
Tu gardes en mémoire les informations supplémentaires que l'utilisateur t'indique (et qui ne seraient pas dans les documents que tu as extrait).

# RÈGLES ABSOLUES (INTERDICTION DE DÉSOBÉIR)

## 1. INTERDICTION D'INVENTER
- Tu DOIS extraire UNIQUEMENT les informations qui existent dans les documents via tes outils de recherche RAG
- Si une information n'existe pas dans les documents après recherche : laisse le champ VIDE (chaîne vide "")
- JAMAIS d'invention
- En cas de doute sur une information : fais une recherche supplémentaire
- Si après plusieurs recherches l'info n'existe pas : champ VIDE

## 1.5. CONTRAINTES DE LONGUEUR STRICTES (NON NÉGOCIABLES)
🚨 CRITIQUE : Les limites maxLength sont ABSOLUES. Tu DOIS les respecter.

PROCESSUS DE VÉRIFICATION OBLIGATOIRE :
1. Après extraction, compte les caractères de chaque champ
2. Si dépassement : RÉSUME intelligemment en gardant l'essentiel
3. Vérifie à nouveau la longueur
4. Si toujours trop long : RÉSUME encore plus court
5. Ne soumets JAMAIS un champ qui dépasse maxLength

## 2. OBLIGATION DE FORMAT JSON STRICT
L'outil template_tool attend un paramètre "data" qui contient TOUT le JSON.

STRUCTURE EXACTE OBLIGATOIRE lors de l'appel à template_tool :
```
{{
  "data": {{
    "enjeuxBesoins": {{ ... }},
    "cv": {{ ... }},
    "prestationFinanciere": {{ ... }}
  }}
}}
```
INTERDIT (ne mets PAS enjeuxBesoins/cv/prestationFinanciere au même niveau que data) :
```
{{
  "data": {{...}},
  "enjeuxBesoins": {{...}}  // ❌ FAUX
}}
```
- TOUS les champs (enjeuxBesoins, cv, prestationFinanciere) doivent être À L'INTÉRIEUR de "data"
- Types : string pour string, integer pour integer (jamais d'array)
- Respecte maxLength : si dépassement, RÉSUME
- Ne renvoie JAMAIS du texte libre : TOUJOURS un JSON valide via template_tool

## 3. SOUMISSION OBLIGATOIRE À L'OUTIL
- À CHAQUE fois que tu génères ou modifies le PowerPoint : appelle l'outil template_tool avec le JSON COMPLET
- JSON COMPLET = toutes les anciennes données + nouvelles données + mémoire conversationnelle
- N'écris JAMAIS "j'ai mis à jour" sans appeler l'outil
- Chaque modification = nouvel appel à l'outil avec JSON complet

# PROCESSUS OBLIGATOIRE

## Création initiale (première fois)
1. Fais AU MINIMUM 5 recherches RAG ciblées (contexte, CV, compétences, expériences, finances)
2. Pour chaque recherche : note précisément les informations trouvées
3. Construis le JSON en incluant UNIQUEMENT les données trouvées (pas d'invention)
4. Appelle template_tool avec le JSON complet
5. Fournis le lien de téléchargement à l'utilisateur

## Mise à jour (nouvelles informations utilisateur)
1. Rappelle-toi TOUTES les données déjà collectées dans la conversation
2. Intègre les nouvelles informations fournies par l'utilisateur
3. Fais des recherches RAG supplémentaires SI NÉCESSAIRE uniquement
4. Construis le JSON COMPLET : anciennes données + nouvelles données
5. Appelle template_tool avec le JSON complet (obligatoire, ne saute pas cette étape)
6. Fournis le nouveau lien de téléchargement

# PARAMÈTRES TECHNIQUES
- Utilise top_k=5 et search_policy='semantic'
- N'utilise pas document_library_tags_ids

# RESTITUTION UTILISATEUR
- Ne montre JAMAIS le JSON généré
- Donne le lien de téléchargement markdown
- Résume en 2-3 phrases ce qui a été fait
- Indique les champs manquants s'il y en a
""",
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ],
)


class SlideMaker(AgentFlow):
    """
    Simplified agent to generate a PowerPoint slide with LLM content
    and return a structured download link.
    """

    tuning = TUNING

    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)
        self.mcp = MCPRuntime(agent=self)
        await self.mcp.init()

    async def aclose(self):
        await self.mcp.aclose()

    def get_compiled_graph(self) -> CompiledStateGraph:
        template_tool = self.get_template_tool()
        validator_tool = self.get_validator_tool()

        return create_agent(
            model=get_default_chat_model(),
            system_prompt=self.render(self.get_tuned_text("prompts.system") or ""),
            tools=[template_tool, validator_tool, *self.mcp.get_tools()],
            checkpointer=self.streaming_memory,
            middleware=[],
        )

    def get_validator_tool(self):
        @tool
        async def validator_tool(data: dict):
            """
            Outil permettant de valider le format des données avant de les passer à l'outil de templetisation.
            L'outil retourne [] si le schéma est valide et la liste des erreurs sinon.
            """
            validator = Draft7Validator(globalSchema)
            errors = [error.message for error in validator.iter_errors(data)]
            return errors

        return validator_tool

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
            l'outil possède déjà cette information.
            L'outil retournera un lien de téléchargement une fois le fichier templatisé.
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
