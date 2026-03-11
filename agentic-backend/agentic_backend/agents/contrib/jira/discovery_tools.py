"""Project discovery tools for Jira agent."""

import asyncio
import json
import logging

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from agentic_backend.agents.jira.helpers import ensure_pydantic_model
from agentic_backend.application_context import get_default_chat_model

logger = logging.getLogger(__name__)

# Predefined queries covering all aspects of a project.
# Phrased as natural language for better semantic search performance.
DISCOVERY_QUERIES = [
    "objectif et contexte du projet",
    "fonctionnalités principales et cas d'utilisation",
    "utilisateurs, acteurs et rôles du système",
    "règles métier et processus",
    "contraintes techniques, sécurité et performance",
    "architecture, composants et interfaces externes",
]

SEARCH_TOOL_NAME = "search_documents_using_vectorization"
TOP_K_PER_QUERY = 10
MAX_UNIQUE_CHUNKS = 30


class ProjectDiscovery(BaseModel):
    """Structured summary produced by the discovery LLM call."""

    project_name: str = Field(
        description="Nom du projet tel que mentionné dans les documents"
    )
    domain: str = Field(
        description="Domaine métier du projet (ex: santé, transport, finance, défense…)"
    )
    summary: str = Field(description="Résumé du projet en 2-3 phrases")
    key_features: list[str] = Field(
        description="Principales fonctionnalités ou modules identifiés"
    )
    actors: list[str] = Field(
        description="Acteurs, utilisateurs ou personas mentionnés"
    )
    key_vocabulary: list[str] = Field(
        description="Termes métier importants trouvés dans les documents"
    )
    raw_context: str = Field(
        description="Synthèse complète et détaillée du contexte projet, à utiliser comme context_summary pour les outils de génération"
    )


DISCOVERY_PROMPT = """Tu es un analyste expert. À partir des extraits documentaires ci-dessous, produis un résumé structuré du projet.

## Extraits documentaires

{chunks}

## Consignes

1. **project_name** : le nom exact du projet tel qu'il apparaît dans les documents.
2. **domain** : le domaine métier (santé, transport, défense, finance, etc.).
3. **summary** : résumé concis du projet (2-3 phrases).
4. **key_features** : liste des fonctionnalités ou modules principaux identifiés.
5. **actors** : liste des acteurs, utilisateurs, personas ou rôles mentionnés.
6. **key_vocabulary** : termes métier spécifiques au projet (vocabulaire technique ou métier récurrent).
7. **raw_context** : synthèse COMPLÈTE et DÉTAILLÉE de tout ce que tu as appris des documents. Ce texte servira de contexte pour générer des exigences et des User Stories — il doit être riche, précis et fidèle aux documents.

⚠️ N'invente RIEN. Utilise UNIQUEMENT les informations présentes dans les extraits ci-dessus."""


class DiscoveryTools:
    """Project discovery tool that performs deterministic RAG queries."""

    def __init__(self, agent):
        self.agent = agent

    def _find_search_tool(self):
        """Find the MCP vector search tool by name."""
        tools = self.agent.mcp.get_tools()
        for t in tools:
            if t.name == SEARCH_TOOL_NAME:
                return t
        return None

    def get_discover_project_tool(self):
        @tool
        async def discover_project(runtime: ToolRuntime):
            """
            Analyse automatiquement les documents du projet via des recherches prédéfinies
            et retourne un résumé structuré : nom du projet, domaine, fonctionnalités,
            acteurs, vocabulaire métier et contexte complet.

            OBLIGATOIRE avant d'appeler generate_requirements ou generate_user_stories.
            Aucun paramètre nécessaire.
            """
            search_tool = self._find_search_tool()
            if not search_tool:
                return (
                    "❌ Outil de recherche documentaire introuvable. "
                    "Vérifiez la connexion au serveur MCP."
                )

            # Run all predefined queries in parallel and collect results
            async def _run_query(query: str) -> list[dict]:
                try:
                    result = await search_tool.ainvoke(
                        {"question": query, "top_k": TOP_K_PER_QUERY}
                    )
                    return json.loads(result) if result else []
                except Exception:
                    logger.warning(
                        "[DiscoveryTools] Search failed for query: %s",
                        query,
                        exc_info=True,
                    )
                    return []

            query_results = await asyncio.gather(
                *[_run_query(q) for q in DISCOVERY_QUERIES]
            )

            all_chunks: list[dict] = []
            seen = set()
            for hits in query_results:
                for hit in hits:
                    key = (hit.get("uid", ""), hit.get("content", "")[:100])
                    if key not in seen:
                        seen.add(key)
                        all_chunks.append(hit)

            if not all_chunks:
                return (
                    "❌ Aucun document trouvé. Vérifiez qu'une bibliothèque "
                    "documentaire contenant des documents projet est sélectionnée."
                )

            # Sort by score (descending) and keep top chunks
            all_chunks.sort(key=lambda c: c.get("score", 0), reverse=True)
            top_chunks = all_chunks[:MAX_UNIQUE_CHUNKS]

            # Format chunks for the LLM
            formatted_chunks = []
            for i, chunk in enumerate(top_chunks, 1):
                title = chunk.get("title", "Sans titre")
                content = chunk.get("content", "")
                formatted_chunks.append(f"### Extrait {i} (source: {title})\n{content}")
            chunks_text = "\n\n".join(formatted_chunks)

            # Call LLM to produce structured summary
            model = get_default_chat_model().with_structured_output(
                ProjectDiscovery, method="json_schema"
            )
            result = ensure_pydantic_model(
                await model.ainvoke(
                    [SystemMessage(content=DISCOVERY_PROMPT.format(chunks=chunks_text))]
                ),
                ProjectDiscovery,
            )

            # Format readable report
            report_lines = [
                f"# Découverte projet : {result.project_name}",
                f"**Domaine :** {result.domain}",
                f"**Résumé :** {result.summary}",
                "",
                "## Fonctionnalités identifiées",
                *[f"- {f}" for f in result.key_features],
                "",
                "## Acteurs / Personas",
                *[f"- {a}" for a in result.actors],
                "",
                "## Vocabulaire métier clé",
                *[f"- {v}" for v in result.key_vocabulary],
                "",
                "---",
                "",
                "## Contexte complet (à utiliser comme context_summary)",
                result.raw_context,
            ]
            report = "\n".join(report_lines)

            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            report,
                            tool_call_id=runtime.tool_call_id,
                        )
                    ]
                }
            )

        return discover_project
