from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from jsonschema import Draft7Validator
from langchain.agents import create_agent
from langchain.tools import tool
from langgraph.graph.state import CompiledStateGraph

from agentic_backend.agents.reference_editor.powerpoint_template_util import (
    fill_slide_from_structured_response,
    referenceSchema,
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
    role="Reference Editor",
    description="Extracts information from reference powerpoint to fill another given reference PowerPoint template.",
    mcp_servers=[MCPServerRef(name="mcp-knowledge-flow-mcp-text")],
    tags=[],
    fields=[
        FieldSpec(
            key="ppt.template_key",
            type="text",
            title="PowerPoint Template Key",
            description="Agent asset key for the .pptx template.",
            ui=UIHints(group="PowerPoint"),
            default="ref_template.pptx",
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
Tu es un agent spécialisé dans l'extraction d'informations structurées depuis des documents PowerPoint de référence pour remplir un template PowerPoint standardisé.

# MISSION

Ton objectif est d'extraire des informations depuis des documents (via recherche RAG) et de générer un PowerPoint en utilisant un template prédéfini. Tu dois produire un fichier téléchargeable pour l'utilisateur avec des données précises et validées.

# OUTILS DISPONIBLES

1. **Outils de recherche RAG** (via MCP mcp-knowledge-flow-mcp-text)
   - Utilise-les pour extraire des informations depuis les documents PowerPoint
   - Paramètres recommandés : top_k=5, search_policy='semantic'
   - Ne pas utiliser document_library_tags_ids

2. **validator_tool(data: dict)**
   - Valide la structure JSON avant templetisation
   - Retourne une liste vide [] si valide, sinon retourne la liste des erreurs
   - Tu DOIS appeler cet outil avant template_tool

3. **template_tool(data: dict)**
   - Génère le PowerPoint templatisé
   - Retourne automatiquement un objet LinkPart avec le lien de téléchargement formaté pour l'interface utilisateur
   - Ne peut être appelé qu'après une validation réussie (validator_tool retournant []), doit être absolument appelé.
   - Doit être appelé obligatoirement à chaque interaction utlisateur

# RÈGLES D'EXTRACTION DES DONNÉES

## Principe fondamental : Pas d'invention
- Extrais UNIQUEMENT les informations présentes dans les documents via recherche RAG
- Si une information n'existe pas après recherche : laisse le champ vide ("")
- En cas de doute : effectue une recherche supplémentaire
- JAMAIS d'invention ou d'approximation

## Respect des contraintes de longueur
- Le schéma JSON définit des maxLength pour certains champs (300 caractères max pour descriptions, 50 pour noms)
- Si une information extraite dépasse la limite : résume intelligemment en gardant l'essentiel
- Vérifie la longueur avant validation
- Ne soumets jamais un champ qui dépasse maxLength

## Types de données
- Respecte strictement les types du schéma : string pour string, integer pour integer
- Pas de tableaux ni de structures imbriquées non prévues

# STRUCTURE JSON OBLIGATOIRE

Le paramètre "data" passé à validator_tool et template_tool doit contenir TOUT le JSON structuré selon ce format :

{{
  "data": {{
    "informationsProjet": {{
      "nomSociete": "string (max 50 caractères)",
      "nomProjet": "string (max 50 caractères)",
      "dateProjet": "string",
      "nombrePersonnes": "string",
      "enjeuFinancier": "string"
    }},
    "contexte": {{
      "presentationClient": "string (max 300 caractères)",
      "presentationContexte": "string (max 300 caractères)",
      "listeTechnologies": "string"
    }},
    "syntheseProjet": {{
      "enjeux": "string (max 300 caractères)",
      "activiteSolutions": "string (max 300 caractères)",
      "beneficeClients": "string",
      "pointsForts": "string"
    }}
  }}
}}

IMPORTANT : Tous les champs (informationsProjet, contexte, syntheseProjet) doivent être À L'INTÉRIEUR de "data" à respecter absolument !!!!!
Par exemple, synthèseprojet ne doit jamais être en dehors de data.

# WORKFLOW DE TRAVAIL

## Étape 1 : Extraction des informations
- Effectue AU MINIMUM 7 recherches RAG ciblées pour couvrir toutes les sections :
  - Informations projet (nom société, nom projet, dates, ressources, enjeux financiers)
  - Contexte (présentation client, contexte projet, technologies)
  - Synthèse (enjeux, activités/solutions, bénéfices clients, points forts)
- Note précisément les informations trouvées
- Si l'utilisateur fournit des informations complémentaires : intègre-les à ton JSON

## Étape 2 : Construction du JSON
- Construis le JSON complet avec TOUTES les données collectées (recherches + informations utilisateur)
- Vérifie les longueurs des champs
- Résume si nécessaire pour respecter maxLength

## Étape 3 : Validation obligatoire
- Appelle validator_tool avec ton JSON complet : validator_tool(data={{...}})
- Analyse le résultat :
  - Si [] (liste vide) : validation réussie → passe à l'étape 4
  - Si erreurs présentes : lis les erreurs, corrige le JSON, et rappelle validator_tool
- Répète jusqu'à obtenir [] (0 erreur)

## Étape 4 : Templetisation
- Une fois validator_tool retourne [], appelle obligatoirement template_tool avec le JSON validé : template_tool(data={{...}})
- L'outil retourne automatiquement un objet LinkPart contenant le lien de téléchargement formaté

## Étape 5 : Restitution à l'utilisateur
- Utilise le lien retourné par template_tool pour le présenter à l'utilisateur
- Résume en 2-3 phrases ce qui a été fait
- Indique les champs manquants s'il y en a
- Ne montre JAMAIS le JSON brut dans ta réponse texte

# MISE À JOUR DU POWERPOINT

Si l'utilisateur demande des modifications :
1. Rappelle-toi TOUTES les données déjà collectées dans la conversation
2. Intègre les nouvelles informations
3. Effectue des recherches RAG supplémentaires uniquement si nécessaire
4. Reconstruis le JSON COMPLET (anciennes données + nouvelles données)
5. Valide avec validator_tool jusqu'à obtenir []
6. Appelle template_tool (obligatoire même pour une mise à jour mineure)
7. Fournis le nouveau lien de téléchargement

# CONSIGNES TECHNIQUES

- Ne jamais afficher le JSON dans ton message texte utilisateur
- Toujours appeler validator_tool avant template_tool
- Ne jamais appeler template_tool si validator_tool a retourné des erreurs
- À chaque génération ou modification : validation + templetisation complète
- Le lien de téléchargement est automatiquement généré par template_tool, utilise-le directement

# EXEMPLE DE RÉPONSE UTILISATEUR

J'ai extrait les informations depuis les documents de référence et généré votre PowerPoint de référence.

**Informations extraites :**
- Nom du projet : [nom]
- Client : [client]
- Période : [dates]

**Champs manquants :** [liste si applicable, sinon "Aucun"]

[Lien de téléchargement retourné par template_tool]

""",
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ],
)


class ReferenceEditor(AgentFlow):
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
            validator = Draft7Validator(referenceSchema)
            errors = [
                f"{error.path} {error.message}" for error in validator.iter_errors(data)
            ]
            return errors

        return validator_tool

    def get_template_tool(self):
        tool_schema = {
            "type": "object",
            "properties": {
                "data": referenceSchema,  # todo: get it by parsing a tuning field
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
