# agentic_backend/core/agents/slide_maker.py
# -----------------------------------------------------------------------------
# 💡 ACADEMY AGENT: SLIDE MAKER 💡
# This agent demonstrates two key patterns for asset generation:
# 1. Using the LLM to generate content (Node: plan_node).
# 2. Rendering that content into a binary file (.pptx) and uploading it to secure storage (Node: render_node).
# 3. Returning a **structured message** (LinkPart) for client-side download rendering.
# -----------------------------------------------------------------------------

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

from jsonschema import Draft7Validator
from langchain.agents import AgentState, create_agent
from langchain.agents.structured_output import ProviderStrategy
from langchain_core.messages import AIMessage
from langfuse.langchain import CallbackHandler
from langgraph.graph import END, START, StateGraph

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
Tu es un agent spécialisé dans l'extraction d'informations structurées depuis des documents via RAG.
Tu utilises le response_format avec un JSON Schema où chaque champ contient une `description` précisant l'information attendue.

# 🚨 RÈGLE CRITIQUE - NOMBRE MINIMUM DE RECHERCHES
Tu DOIS faire AU MINIMUM 5 recherches RAG distinctes avant de remplir le schéma.
NE fais JAMAIS qu'une seule recherche large. Décompose TOUJOURS en plusieurs recherches ciblées.

## Ton Processus OBLIGATOIRE:
**ÉTAPE 1 - ANALYSE DU SCHÉMA**
Identifie les sections principales du schéma (ex: contexte projet, CV, finances, etc.)
Pour chaque section, note les types d'informations à extraire

**ÉTAPE 2 - PLANIFICATION DES RECHERCHES**
Liste mentalement les recherches RAG que tu vas effectuer (minimum 5).
Chaque section principale nécessite ses propres recherches ciblées.

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

**ÉTAPE 4 - EXTRACTION ET VALIDATION**
- Extrais les informations depuis les résultats RAG obtenus
- Vérifie les contraintes `maxLength` et résume si nécessaire
- Remplis le JSON avec les données validées

## Règles d'Extraction:

### Fidélité Absolue
- ✅ Extrais UNIQUEMENT depuis les documents RAG
- ❌ N'invente JAMAIS de données
- ❌ N'utilise pas ta connaissance générale
- ❌ Ne te contente JAMAIS d'une seule recherche globale

### 🚨 RESPECT STRICT DES LONGUEURS - CRITIQUE
**SI `maxLength` est renseigné** et que le texte extrait dépasse `maxLength` : **RESUME INTELLIGEMMENT**

### Optimisation des requêtes RAG
- Multiplie les recherches et appels d'outil
- Regroupe les champs similaires si pertinent
- Évite les requêtes trop larges ("tout sur le document")
- Privilégie la précision sur l'exhaustivité

## Ton Attitude
- Méthodique : traite chaque champ systématiquement. Si tu ne trouve pas une information fais une recherche spécialisée
- Précis : base-toi sur les descriptions fournies pour formuler tes requêtes
- Rigoureux : les contraintes de longueur sont NON NÉGOCIABLES
- Honnête : si l'information n'existe pas, ne mets rien
- Persévérant : si une recherche ne donne pas de résultats, reformule et réessaye

# PARAMETRES TECHNIQUES: Utilises un 'top_k' de 5 et une 'search_policy' de 'semantic'. N'utilise pas 'document_library_tags_ids'.
""",
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ],
)


# --- Agent State ---
# -------------------
class SlideMakerState(AgentState):
    """Minimal state: conversation messages and LLM output content."""


# --- Core Agent ---
# ------------------
@expose_runtime_source("agent.SlideMaker")
class SlideMaker(AgentFlow):
    """
    Simplified agent to generate a PowerPoint slide with LLM content
    and return a structured download link.
    """

    tuning = TUNING
    _graph: Optional[StateGraph] = None
    # TARGET_PLACEHOLDER_INDEX = 1  # Hardcoded index for content insertion

    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)
        self.model = get_default_chat_model()
        self._graph = self._build_graph()
        self.mcp = MCPRuntime(agent=self)
        await self.mcp.init()

    async def aclose(self):
        await self.mcp.aclose()

    def _build_graph(self) -> StateGraph:
        """Sets up the two-node linear flow: plan -> render -> END."""
        g = StateGraph(SlideMakerState)
        g.add_node("plan_node", self.plan_node)
        g.add_node("render_node", self.render_node)
        g.add_edge(START, "plan_node")
        g.add_edge("plan_node", "render_node")
        g.add_edge("render_node", END)
        return g

    def _last_user_message_text(self, state: SlideMakerState) -> str:
        """Fetches the content of the most recent user message."""
        for msg in reversed(state.get("messages", [])):
            if getattr(msg, "type", "") in ("human", "user"):
                return str(getattr(msg, "content", "")).strip()
        return ""

    # --------------------------------------------------------------------------
    # Node 1: Plan Node (LLM Content Generation)
    # --------------------------------------------------------------------------

    async def plan_node(self, state: SlideMakerState) -> dict:
        """Generates a concise text block from the LLM based on the user's request."""
        user_ask = self._last_user_message_text(state)

        langfuse_handler = CallbackHandler()
        agent = create_agent(
            model=get_default_chat_model(),
            system_prompt=self.render(self.get_tuned_text("prompts.system") or ""),
            tools=[*self.mcp.get_tools()],
            checkpointer=None,  # self.streaming_memory,
            response_format=ProviderStrategy(globalSchema),  # type: ignore
        )
        resp = await agent.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": user_ask},
                ]
            },
            config={"callbacks": [langfuse_handler]},
        )
        """validator = Draft7Validator(globalSchema)
        errors = list(validator.iter_errors(resp["structured_response"]))
        validation_errors = 0
        while errors and validation_errors < 0:
            validation_errors += 1
            resp = await agent.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "Your response did not fit the json schema validation."
                                "If it is too long, summarize it."
                                f"Here is the error message: {[err.message for err in errors]}."
                            ),
                        },
                    ]
                }
            )
            validator = Draft7Validator(globalSchema)
            errors = list(validator.iter_errors(resp["structured_response"]))
        logger.info(f"{validation_errors} retries to validate the JSON schema.")"""
        return {"structured_response": resp["structured_response"]}

    # --------------------------------------------------------------------------
    # Node 2: Render Node (Asset Generation, Upload, and Structured Response)
    # --------------------------------------------------------------------------
    async def render_node(self, state: SlideMakerState) -> dict:
        """
        Fetches template, inserts LLM text, saves deck, uploads to storage,
        and returns a structured message with the download link.
        """
        template_path: Path | str = ""
        output_path: Optional[Path] = None

        def _append_error(msg_content: str) -> dict:
            logger.error("Error encountered: %s", msg_content)
            return {"messages": [AIMessage(content=msg_content)]}

        if not state.get("structured_response"):
            return _append_error("❌ Generation failed: LLM did not provide content.")

        try:
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
                fill_slide_from_structured_response(
                    template_path, state.get("structured_response"), output_path
                )

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

            final_parts: list[MessagePart] = [
                TextPart(
                    text=f"✅ **Success:** PowerPoint deck generated and securely saved to your assets.\n**Display Filename:** `{upload_result.file_name}`"
                ),
                LinkPart(
                    href=final_download_url,
                    title=f"Download {upload_result.file_name}",
                    kind=LinkKind.download,
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                ),
                TextPart(
                    text=(
                        f"\n---\n"
                        f"**💡 Academy Note (Structured Output Pattern)**\n"
                        f"The download button above is a **`LinkPart`** object (`kind='download'`).\n"
                        f"This pattern cleanly separates binary assets from text/Markdown in the UI.\n"
                        f"**Secure Header Required by UI:** `X-Asset-User-ID: {user_id_to_store_asset}`"
                    )
                ),
            ]

            # FINAL RETURN: Use structured parts in the AIMessage
            return {
                "messages": [AIMessage(content="", parts=final_parts)],
                "content_slot": state.get("content_slot", ""),
            }

        except AssetRetrievalError as e:
            return _append_error(
                f"❌ **Asset Error:** Cannot find template '{template_key}'. Check asset availability. (Details: {e})"
            )
        except Exception as e:
            # Catch all other exceptions during rendering/upload
            logger.exception("An unexpected error occurred during rendering/upload.")
            return _append_error(
                f"❌ **Processing Error:** Failed to generate/upload the slide. (Details: {e})"
            )

        finally:
            # 6. CRITICAL: Cleanup temporary files (template and output deck)
            if template_path:
                Path(template_path).unlink(missing_ok=True)
            if output_path and output_path.exists():
                output_path.unlink(missing_ok=True)
