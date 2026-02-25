"""PPT Filler Agent for extracting data from documents and filling PowerPoint templates."""

import logging
import os

from langchain.agents import create_agent
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer

from agentic_backend.agents.ppt_filler.export_tools import ExportTools
from agentic_backend.agents.ppt_filler.extraction_tools import ExtractionTools
from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.common.structures import AgentChatOptions
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import (
    AgentTuning,
    FieldSpec,
    MCPServerRef,
    UIHints,
)
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)


@expose_runtime_source("agent.PptFiller")
class PptFillerAgent(AgentFlow):
    """Agent that extracts data from documents to fill PowerPoint templates."""

    tuning = AgentTuning(
        role="PowerPoint Template Filler",
        description="Extracts data from resumes and project documents to fill PowerPoint templates with structured information.",
        mcp_servers=[MCPServerRef(id="mcp-knowledge-flow-mcp-text")],
        tags=["document", "powerpoint", "extraction"],
        fields=[
            FieldSpec(
                key="ppt.template_key",
                type="text",
                title="PowerPoint Template Key",
                description="Agent asset key for the .pptx template file.",
                ui=UIHints(group="PowerPoint"),
                default="ppt_template.pptx",
            ),
            FieldSpec(
                key="prompts.system",
                type="prompt",
                title="System Prompt",
                description="Instructions for the agent on how to extract and fill data",
                required=True,
                default="""Tu es un expert en extraction de données professionnelles depuis des documents pour remplir des templates PowerPoint.

## WORKFLOW

Suis ces 4 étapes dans l'ordre. Ne passe jamais à l'étape suivante sans avoir terminé la précédente.

**Étape 1 — Extraction des enjeux et besoins (OBLIGATOIRE EN PREMIER)**
Appelle `extract_enjeux_besoins(context_hint=<nom du projet si connu>)`.
Le contexte extrait sera réutilisé à l'étape 2 pour aligner le CV.

**Étape 2 — Extraction du CV**
Appelle `extract_cv(project_context=<contexte extrait étape 1>, context_hint=<nom du candidat si connu>)`.
Le `project_context` permet de filtrer les compétences et expériences selon leur pertinence au projet.

**Étape 3 — Extraction des prestations financières**
Appelle `extract_prestation_financiere(context_hint=<indication si connue>)`.

**Étape 4 — Génération du PowerPoint**
Appelle `fill_template` avec les trois JSON extraits comme arguments séparés:
```
fill_template(enjeuxBesoins=<JSON étape 1>, cv=<JSON étape 2>, prestationFinanciere=<JSON étape 3>)
```

## RÈGLES

- Les outils d'extraction utilisent UNIQUEMENT les informations présentes dans les documents. Ne JAMAIS inventer ou déduire des informations.
- Les outils retournent des JSON à structure plate avec champs numérotés (formation1, formation2, etc.). Ces JSON sont prêts à être passés tels quels à `fill_template`.
- Ne jamais appeler `fill_template` sans avoir les trois JSON.
- Les niveaux de maîtrise (langues, compétences) sont sur une échelle de 1 à 5: 1=Débutant, 2=Intermédiaire, 3=Bon, 4=Très bon, 5=Expert.

## COMMUNICATION

- Sois concis entre les appels d'outils. Ne décris pas ce que tu vas faire avant chaque appel.
- Ne montre pas les JSON bruts à l'utilisateur.
- Si fill_template retourne un LinkPart, ne le réécris JAMAIS en texte ou en Markdown. N'affiche jamais d'URL brute ni de lien `[Download ...]`. Ne mentionne pas le bouton de téléchargement. Résume simplement ce qui a été extrait et les champs manquants.""",
                ui=UIHints(group="Prompts", multiline=True, markdown=True),
            ),
            FieldSpec(
                key="chat_options.attach_files",
                type="boolean",
                title="Allow file attachments",
                description="Show file upload/attachment controls for this agent.",
                required=False,
                default=True,
                ui=UIHints(group="Chat options"),
            ),
            FieldSpec(
                key="chat_options.libraries_selection",
                type="boolean",
                title="Document libraries picker",
                description="Let users select document libraries/knowledge sources for this agent.",
                required=False,
                default=True,
                ui=UIHints(group="Chat options"),
            ),
        ],
    )

    default_chat_options = AgentChatOptions(
        attach_files=True,
        libraries_selection=True,
        search_rag_scoping=False,
        search_policy_selection=False,
        deep_search_delegate=False,
    )

    async def async_init(self, runtime_context: RuntimeContext):
        """Initialize agent and tool helpers."""
        await super().async_init(runtime_context=runtime_context)
        self.mcp = MCPRuntime(agent=self)
        await self.mcp.init()

        # Initialize tool helpers
        self.extraction_tools = ExtractionTools(self)
        self.export_tools = ExportTools(self)

        # Check if Langfuse is configured
        self.langfuse_enabled = bool(
            os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
        )
        if self.langfuse_enabled:
            logger.info("[PptFillerAgent] Langfuse tracing enabled")

    def _get_langfuse_handler(self) -> LangfuseCallbackHandler | None:
        """Create a Langfuse callback handler for tracing LLM calls."""
        if not self.langfuse_enabled:
            return None
        return LangfuseCallbackHandler()

    async def aclose(self):
        """Clean up resources."""
        await self.mcp.aclose()

    def get_compiled_graph(
        self, checkpointer: Checkpointer | None = None
    ) -> CompiledStateGraph:
        """Create the agent graph with all tools."""
        return create_agent(
            model=get_default_chat_model(),
            system_prompt=self.render(self.get_tuned_text("prompts.system") or ""),
            tools=[
                # Extraction tools
                self.extraction_tools.get_extract_enjeux_besoins_tool(),
                self.extraction_tools.get_extract_cv_tool(),
                self.extraction_tools.get_extract_prestation_financiere_tool(),
                # Export tool
                self.export_tools.get_fill_template_tool(),
                # MCP tools for additional document search if needed
                *self.mcp.get_tools(),
            ],
            checkpointer=checkpointer,
        )
