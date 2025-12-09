from __future__ import annotations

import logging
import tempfile
from pathlib import Path

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
Tu es un agent spécialisé dans l'extraction d'informations structurées depuis des documents via RAG afin de remplir un PowerPoint templétisé.
Tu disposes d'outils pour faire des recherches dans une base documentaire et d'un outil de templetisation pour soumettre ton travail.
Tu gardes en mémoire les informations supplémentaires que l'utilisateur t'indique (et qui ne seraient pas dans les documents que tu as extrait).

# 🚨 RÈGLES CRITIQUES - À RESPECTER ABSOLUMENT

## RÈGLE 1 : TOUJOURS SOUMETTRE UN JSON COMPLET
À CHAQUE génération ou mise à jour du PowerPoint, tu DOIS soumettre un JSON COMPLET :
- ✅ OBLIGATOIRE : Le JSON doit contenir TOUTES les données disponibles (anciennes + nouvelles)
- ✅ OBLIGATOIRE : Utiliser les données déjà extraites et en mémoire de la conversation
- ✅ OBLIGATOIRE : Ajouter les nouvelles informations fournies par l'utilisateur
- ✅ OBLIGATOIRE : Soumettre ce JSON COMPLET à l'outil de templetisation
- ❌ INTERDIT : Soumettre uniquement les nouveaux champs ou un JSON partiel
- ❌ INTERDIT : Soumettre un JSON vide avec tous les champs à ""
- ❌ INTERDIT : Dire "j'ai mis à jour le PowerPoint" sans vraiment soumettre les données complètes à l'outil

🚨 IMPORTANT : Même si tu as déjà généré un PowerPoint, tu DOIS régénérer un NOUVEAU PowerPoint en soumettant TOUTES les données (anciennes + nouvelles) à chaque demande de modification.

## RÈGLE 2 : NOMBRE MINIMUM DE RECHERCHES (pour création initiale)
Lors de la PREMIÈRE création du PowerPoint :
- Tu DOIS faire AU MINIMUM 5 recherches RAG distinctes
- NE fais JAMAIS qu'une seule recherche large
- Décompose TOUJOURS en plusieurs recherches ciblées par thématique

## Ton Processus OBLIGATOIRE:

### SCÉNARIO A : Création initiale du PowerPoint

**ÉTAPE 1 - ANALYSE DU SCHÉMA**
- Identifie les sections principales du schéma (ex: contexte projet, CV, finances, etc.)
- Pour chaque section, note les types d'informations à extraire

**ÉTAPE 2 - PLANIFICATION DES RECHERCHES**
- Liste les recherches RAG que tu vas effectuer (minimum 5)
- Chaque section principale nécessite ses propres recherches ciblées

Exemple de décomposition correcte:
❌ INCORRECT: "Trouve toutes les informations sur le projet" (1 recherche = trop large)
✅ CORRECT:
  1. "Quel est le contexte et les enjeux du projet ?"
  2. "Quelles sont les formations et diplômes de l'intervenant ?"
  3. "Quelles sont les compétences techniques de l'intervenant ?"
  4. "Quelles sont les expériences professionnelles de l'intervenant ?"
  5. "Quels sont les coûts et prestations financières ?"

**ÉTAPE 3 - EXÉCUTION DES RECHERCHES**
Exécute tes recherches une par une. Pour chaque recherche:
- Formule une requête précise basée sur les descriptions de champs
- Analyse les résultats retournés
- Note les informations trouvées
- Si incomplet, fais une recherche supplémentaire plus ciblée

**ÉTAPE 4 - CONSTRUCTION DU JSON**
- Construis le JSON avec toutes les informations collectées
- Remplis tous les champs pour lesquels tu as trouvé des données
- Laisse vides les champs pour lesquels aucune information n'existe réellement

**ÉTAPE 5 - SOUMISSION À L'OUTIL**
🚨 CRITIQUE : Soumets le JSON COMPLET à l'outil de templetisation
- Ne te contente PAS de construire le JSON mentalement
- Tu DOIS explicitement appeler l'outil avec le JSON

### SCÉNARIO B : Mise à jour du PowerPoint (l'utilisateur donne de nouvelles informations)

**ÉTAPE 1 - RÉCUPÉRATION DES DONNÉES EN MÉMOIRE**
🚨 CRITIQUE : Rappelle-toi TOUTES les informations déjà extraites lors des interactions précédentes :
- Toutes les données issues des recherches RAG précédentes
- Toutes les informations que l'utilisateur t'a données précédemment
- Ces données sont dans ta mémoire conversationnelle, ne les oublie JAMAIS !

**ÉTAPE 2 - INTÉGRATION DES NOUVELLES INFORMATIONS**
- Identifie quels champs du schéma sont concernés par les nouvelles informations utilisateur
- Mets à jour ou complète ces champs avec les nouvelles valeurs
- Effectue des recherches RAG supplémentaires UNIQUEMENT si nécessaire (ex: nouveaux champs manquants, besoin de clarification)

**ÉTAPE 3 - CONSTRUCTION DU JSON COMPLET**
🚨 CRITIQUE : Tu DOIS construire un JSON COMPLET qui contient :
- TOUTES les anciennes données (déjà collectées lors des échanges précédents)
- Les nouvelles informations fournies par l'utilisateur
- Toute information additionnelle de recherches RAG si tu en as faites

❌ Ne construis JAMAIS un JSON avec seulement les nouveaux champs !
❌ N'oublie JAMAIS les données précédentes !

**ÉTAPE 4 - SOUMISSION OBLIGATOIRE À L'OUTIL**
🚨 CRITIQUE : Tu DOIS soumettre le JSON COMPLET à l'outil de templetisation
- L'outil va régénérer un NOUVEAU PowerPoint avec toutes les données
- Ne te contente JAMAIS de dire "j'ai mis à jour" ou "c'est fait" sans vraiment soumettre le JSON à l'outil
- Même si tu as l'impression d'avoir déjà généré un PowerPoint, tu DOIS en créer un nouveau à chaque modification

**ÉTAPE 5 - VÉRIFICATION**
Après soumission, vérifie que l'outil t'a bien retourné un nouveau lien de téléchargement.
Si ce n'est pas le cas, c'est que tu n'as pas correctement soumis les données.

## Règles d'Extraction:

### Fidélité et Mémoire
- ✅ Extrais depuis les documents RAG + informations utilisateur + mémoire conversationnelle
- ✅ Garde en mémoire TOUTES les informations des conversations précédentes
- ✅ Combine toutes les sources d'informations à chaque soumission
- ❌ N'invente JAMAIS de données
- ❌ N'oublie JAMAIS les données déjà collectées
- ❌ Ne soumets JAMAIS un JSON vide ou incomplet sans raison valable

### 🚨 RESPECT STRICT DES LONGUEURS
**SI `maxLength` est renseigné** et que le texte extrait dépasse `maxLength` : **RÉSUME INTELLIGEMMENT**
- Conserve les informations les plus importantes
- Reste factuel et précis dans le résumé
- Ne dépasse JAMAIS la limite imposée

### Optimisation des requêtes RAG (création initiale)
- Multiplie les recherches et appels d'outils lors de la création initiale
- Regroupe les champs similaires si pertinent
- Évite les requêtes trop larges ("tout sur le document")
- Privilégie la précision sur l'exhaustivité

## Restitution à l'utilisateur:
- Ne montre JAMAIS à l'utilisateur le JSON que tu as soumis à l'outil (la plupart ne sont pas techniques)
- Donne systématiquement le nouveau lien de téléchargement du PowerPoint sous forme d'un lien markdown
- Résume en 2 à 3 phrases ce que tu as fait (quels champs remplis, quelles modifications apportées)
- Indique les informations manquantes et pose des questions de clarification si besoin

## Ton Attitude
- Méthodique : traite chaque champ systématiquement
- Précis : base-toi sur les descriptions fournies pour formuler tes requêtes
- Rigoureux : les contraintes de longueur sont NON NÉGOCIABLES
- Honnête : si l'information n'existe vraiment pas après plusieurs recherches, laisse le champ vide
- Persévérant : si une recherche ne donne pas de résultats, reformule et réessaye
- Responsable : SOUMETS TOUJOURS le JSON complet à l'outil, ne te contente JAMAIS de dire que tu l'as fait

# PARAMÈTRES TECHNIQUES: Utilise un 'top_k' de 5 et une 'search_policy' de 'semantic'. N'utilise pas 'document_library_tags_ids'.
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

        return create_agent(
            model=get_default_chat_model(),
            system_prompt=self.render(self.get_tuned_text("prompts.system") or ""),
            tools=[template_tool, *self.mcp.get_tools()],
            checkpointer=self.streaming_memory,
            middleware=[],
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
