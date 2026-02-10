from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from jsonschema import Draft7Validator
from langchain.agents import create_agent
from langchain.tools import tool
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer

from agentic_backend.agents.reference_editor.powerpoint_template_util import (
    fill_slide_from_structured_response,
    fill_word_from_structured_response,
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
    mcp_servers=[MCPServerRef(id="mcp-knowledge-flow-mcp-text")],
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
            key="word.template_key",
            type="text",
            title="Word Template Key",
            description="Agent asset key for the .docx template.",
            ui=UIHints(group="Word"),
            default="ref_template.docx",
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
   - Retourne un message de succès si valide, sinon retourne la liste des erreurs
   - Tu DOIS appeler cet outil avant template_tool

3. **template_tool(data: dict)**
   - Génère le PowerPoint templatisé
   - Retourne automatiquement un objet LinkPart avec le lien de téléchargement formaté pour l'interface utilisateur
   - IMPÉRATIF : Dès que validator_tool retourne un message de succès, tu DOIS IMMÉDIATEMENT appeler template_tool(data={{...}}) avec exactement les mêmes données
   - Ne JAMAIS afficher le JSON à l'utilisateur, appelle directement template_tool

4. **word_template_tool(data: dict)**
   - Génère un document Word templatisé (au lieu d'un PowerPoint)
   - Fonctionne exactement comme template_tool mais produit un fichier .docx
   - N'utilise cet outil QUE si l'utilisateur demande EXPLICITEMENT un document Word
   - Par défaut, utilise toujours template_tool (PowerPoint) sauf demande contraire de l'utilisateur

# RÈGLES D'EXTRACTION DES DONNÉES

## Principe fondamental : Pas d'invention
- Extrais UNIQUEMENT les informations présentes dans les documents via recherche RAG
- Si une information n'existe pas après recherche : laisse le champ vide ("")
- En cas de doute : effectue une recherche supplémentaire
- JAMAIS d'invention ou d'approximation

## Gestion des images de technologies
- Pour le champ "listeTechnologies", le système peut automatiquement remplacer les noms de technologies par leurs logos/images
- Si l'utilisateur a uploadé des images de logos (par exemple "Apple.png", "Nvidia.jpg"), ces images seront automatiquement insérées dans le document
- Tu dois simplement lister les noms des technologies séparés par des virgules (exemple: "Nvidia, Apple, AWS")
- Le système cherchera automatiquement les images correspondantes et les placera dans le template

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
  - Si message de succès : validation réussie → APPELLE IMMÉDIATEMENT template_tool à l'étape 4 (NE PAS S'ARRÊTER)
  - Si liste d'erreurs : lis les erreurs, corrige le JSON, et rappelle validator_tool
- Répète jusqu'à obtenir un message de succès

## Étape 4 : Templetisation (OBLIGATOIRE, NE PAS SAUTER)
- CRITIQUE : Dès que validator_tool retourne un message de succès, tu DOIS appeler l'outil de templetisation approprié dans le MÊME tour de conversation
- Choix de l'outil :
  - Si l'utilisateur a demandé EXPLICITEMENT un document Word : appelle word_template_tool(data={{...}})
  - Sinon (par défaut) : appelle template_tool(data={{...}}) pour générer un PowerPoint
- Appelle l'outil avec exactement les mêmes données validées
- NE JAMAIS afficher le JSON brut à l'utilisateur
- NE JAMAIS t'arrêter après validation sans appeler l'outil de templetisation
- L'outil retourne automatiquement un objet LinkPart contenant le lien de téléchargement formaté

## Étape 5 : Restitution à l'utilisateur
- Utilise le lien retourné par l'outil de templetisation pour le présenter à l'utilisateur
- Résume en 2-3 phrases ce qui a été fait
- Indique les champs manquants s'il y en a
- Ne montre JAMAIS le JSON brut dans ta réponse texte

# MISE À JOUR DU DOCUMENT

Si l'utilisateur demande des modifications :
1. Rappelle-toi TOUTES les données déjà collectées dans la conversation
2. Intègre les nouvelles informations
3. Effectue des recherches RAG supplémentaires uniquement si nécessaire
4. Reconstruis le JSON COMPLET (anciennes données + nouvelles données)
5. Valide avec validator_tool jusqu'à obtenir un message de succès
6. Appelle IMMÉDIATEMENT l'outil de templetisation approprié (template_tool ou word_template_tool selon le format demandé initialement)
7. Fournis le nouveau lien de téléchargement

# CONSIGNES TECHNIQUES

⚠️ RÈGLE ABSOLUE : VALIDATION → TEMPLETISATION (SÉQUENCE OBLIGATOIRE)
1. Appelle validator_tool(data={{...}})
2. Si retour = message de succès → Appelle IMMÉDIATEMENT l'outil de templetisation approprié (data={{...}}) dans la MÊME réponse
   - word_template_tool si l'utilisateur a demandé explicitement un document Word
   - template_tool (PowerPoint) par défaut
3. Ne JAMAIS afficher le JSON à l'utilisateur
4. Ne JAMAIS t'arrêter entre validation et templetisation

Autres règles :
- Ne jamais appeler les outils de templetisation si validator_tool a retourné des erreurs
- À chaque génération ou modification : validation + templetisation complète (les deux dans le même tour)
- Le lien de téléchargement est automatiquement généré par l'outil de templetisation, utilise-le directement

# EXEMPLE DE RÉPONSE UTILISATEUR

J'ai extrait les informations depuis les documents de référence et généré votre document de référence.

**Informations extraites :**
- Nom du projet : [nom]
- Client : [client]
- Période : [dates]

**Champs manquants :** [liste si applicable, sinon "Aucun"]

[Lien de téléchargement retourné par l'outil de templetisation]

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

    def get_compiled_graph(
        self, checkpointer: Checkpointer | None = None
    ) -> CompiledStateGraph:
        template_tool = self.get_template_tool()
        word_template_tool = self.get_word_template_tool()
        validator_tool = self.get_validator_tool()

        return create_agent(
            model=get_default_chat_model(),
            system_prompt=self.render(self.get_tuned_text("prompts.system") or ""),
            tools=[
                template_tool,
                word_template_tool,
                validator_tool,
                *self.mcp.get_tools(),
            ],
            checkpointer=checkpointer,
        )

    def get_validator_tool(self):
        @tool
        async def validator_tool(data: dict):
            """
            Outil permettant de valider le format des données avant de les passer à l'outil de templetisation.
            L'outil retourne [] si le schéma est valide et la liste des erreurs sinon.

            IMPORTANT : Si cet outil retourne [] (liste vide), tu DOIS IMMÉDIATEMENT appeler template_tool(data={{...}})
            avec exactement les mêmes données dans le MÊME tour de conversation. Ne t'arrête pas ici.
            """
            if len(data.keys()) != 3:
                return (
                    "Bad root key format. The JSON should have the following format:\n"
                    "{{\n"
                    '    "enjeuxBesoins": {{...}},\n'
                    '    "cv": {{...}},\n'
                    '    "prestationFinanciere": {{...}}\n'
                    "}}"
                )

            def shorten_error_message(error):
                """Convert verbose validation errors to concise messages"""
                field_path = ".".join(str(p) for p in error.path) or "root"
                if error.validator == "type":
                    return f"{field_path} type invalid. Expected {error.schema.get('type')}."
                return f"{field_path} invalid. Reason: {error.validator}."

            validator = Draft7Validator(referenceSchema)

            errors = [shorten_error_message(e) for e in validator.iter_errors(data)]
            if not errors:
                return "✓ Validation réussie ! Appelle maintenant template_tool(data={{...}}) avec ces mêmes données."
            return errors

        return validator_tool

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
            template_path = await self.fetch_config_blob_to_tempfile(
                template_key, suffix=".pptx"
            )

            # 2. Save the modified presentation to a temp file
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".pptx", prefix="result_"
            ) as out:
                output_path = Path(out.name)
                # Extract the actual data from the wrapper
                actual_data = data.get("data", data)
                # Create clients for image search
                from agentic_backend.common.kf_base_client import KfBaseClient
                from agentic_backend.common.vector_search_client import (
                    VectorSearchClient,
                )

                vector_search_client = VectorSearchClient()
                kf_base_client = KfBaseClient(
                    allowed_methods=frozenset({"GET", "POST"}), agent=self
                )
                fill_slide_from_structured_response(
                    template_path,
                    actual_data,
                    output_path,
                    vector_search_client,
                    kf_base_client,
                )

            # 3. Upload the generated asset to user storage
            import asyncio
            import uuid

            # user_id_to_store_asset = self.get_end_user_id()
            # Use UUID to generate a unique filename that won't trigger versioning conflicts
            unique_id = str(uuid.uuid4())
            final_key = f"Generated_Slide_{unique_id}.pptx"

            # Try upload with retry logic in case of temporary backend issues
            max_retries = 2
            upload_succeeded = False
            last_error = None

            for attempt in range(max_retries):
                try:
                    with open(output_path, "rb") as f_out:
                        upload_result = await self.upload_user_blob(
                            key=final_key,
                            file_content=f_out,
                            filename=final_key,  # Use the same unique filename to avoid versioning conflicts
                            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        )
                    upload_succeeded = True
                    break  # Success, exit retry loop
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        # Wait a bit before retrying
                        await asyncio.sleep(1)
                        continue

            if upload_succeeded:
                # 4. Construct the structured message for the UI
                final_download_url = upload_result.download_url

                return LinkPart(
                    href=final_download_url,
                    title=f"Download {upload_result.file_name}",
                    kind=LinkKind.download,
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )
            else:
                return last_error

        return template_tool

    def get_word_template_tool(self):
        tool_schema = {
            "type": "object",
            "properties": {
                "data": referenceSchema,  # todo: get it by parsing a tuning field
            },
            "required": ["data"],
        }

        @tool(args_schema=tool_schema)
        async def word_template_tool(data: dict):
            """
            Outil permettant de templétiser un fichier Word envoyé par l'utilisateur.
            La nature du fichier importe peu tant que le format des données est respecté. Tu n'as pas besoin de préciser quel fichier,
            l'outil possède déjà cette information.
            L'outil retournera un lien de téléchargement une fois le fichier templatisé.
            """
            # 1. Fetch template from secure asset storage
            template_key = (
                self.get_tuned_text("word.template_key") or "simple_template.docx"
            )
            template_path = await self.fetch_config_blob_to_tempfile(
                template_key, suffix=".docx"
            )

            # 2. Save the modified document to a temp file
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".docx", prefix="result_"
            ) as out:
                output_path = Path(out.name)
                # Extract the actual data from the wrapper
                actual_data = data.get("data", data)
                # Create clients for image search
                from agentic_backend.common.kf_base_client import KfBaseClient
                from agentic_backend.common.vector_search_client import (
                    VectorSearchClient,
                )

                vector_search_client = VectorSearchClient()
                kf_base_client = KfBaseClient(
                    allowed_methods=frozenset({"GET", "POST"}), agent=self
                )
                fill_word_from_structured_response(
                    template_path,
                    actual_data,
                    output_path,
                    vector_search_client,
                    kf_base_client,
                )

            # 3. Upload the generated asset to user storage
            import asyncio
            import uuid

            # user_id_to_store_asset = self.get_end_user_id()
            # Use UUID to generate a unique filename that won't trigger versioning conflicts
            unique_id = str(uuid.uuid4())
            final_key = f"Generated_Document_{unique_id}.docx"

            # Try upload with retry logic in case of temporary backend issues
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    with open(output_path, "rb") as f_out:
                        upload_result = await self.upload_user_blob(
                            key=final_key,
                            file_content=f_out,
                            filename=final_key,  # Use the same unique filename to avoid versioning conflicts
                            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                    break  # Success, exit retry loop
                except Exception:
                    if attempt < max_retries - 1:
                        # Wait a bit before retrying
                        await asyncio.sleep(1)
                        continue
                    else:
                        # Final attempt failed, re-raise
                        raise

            # 4. Construct the structured message for the UI
            final_download_url = upload_result.download_url

            return LinkPart(
                href=final_download_url,
                title=f"Download {upload_result.file_name}",
                kind=LinkKind.download,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        return word_template_tool
