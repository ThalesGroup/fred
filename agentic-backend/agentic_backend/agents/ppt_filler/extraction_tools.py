"""Schema-driven extraction tools for PPT Filler agent."""

import json
import logging
from typing import Type

import httpx
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import BaseModel

from agentic_backend.agents.ppt_filler.pydantic_models import (
    CV,
    EnjeuxBesoins,
    PrestationFinanciere,
    SearchQueries,
    schema_without_max_length,
)
from agentic_backend.agents.ppt_filler.skill_mastery import (
    extract_mastery_from_image,
    inject_mastery_alt_text,
    is_raster_image,
    parse_image_refs,
)
from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.kf_markdown_media_client import KfMarkdownMediaClient

logger = logging.getLogger(__name__)

SEARCH_TOOL_NAME = "search_documents_using_vectorization"
TOP_K_DEFAULT = 8
MAX_UNIQUE_CHUNKS = 40

# Hardcoded queries per extraction type: (query, top_k) pairs.
# Use a higher top_k for broad queries that may span many document sections.
ENJEUX_BESOINS_QUERIES: list[tuple[str, int]] = [
    ("Quels sont les objectifs et les missions principales du projet ?", TOP_K_DEFAULT),
    ("Quel est le contexte du projet ?", TOP_K_DEFAULT),
]
CV_QUERIES: list[tuple[str, int]] = [
    ("Intitulé du poste", 5),
    ("Trigramme de l'intervenant", 5),
    ("Formations avec dates et établissements", TOP_K_DEFAULT),
    ("Langues parlées et niveau de maîtrise", TOP_K_DEFAULT),
    ("Compétences en management et niveau de maîtrise", TOP_K_DEFAULT),
    ("Compétences en informatique et niveau de maîtrise", 20),
    ("Compétences en gestion de projet et niveau de maîtrise", TOP_K_DEFAULT),
    (
        "Expériences professionnelles avec entreprises, postes, durées et réalisations",
        15,
    ),
]
PRESTATION_FINANCIERE_QUERIES: list[tuple[str, int]] = [
    ("Nom et coût unitaire des prestations", TOP_K_DEFAULT),
    ("Charge estimée en unités d'œuvre pour chaque prestation", TOP_K_DEFAULT),
    ("Coût total de chaque prestation et coût total global", TOP_K_DEFAULT),
]


class ExtractionTools:
    """Schema-driven search and extraction tools for PPT data."""

    def __init__(self, agent):
        """Initialize extraction tools with reference to parent agent."""
        self.agent = agent

    def _get_langfuse_handler(self):
        """Get Langfuse handler from parent agent."""
        return self.agent._get_langfuse_handler()

    def _build_llm_config(self) -> RunnableConfig:
        """Build a RunnableConfig with Langfuse callback if enabled."""
        handler = self._get_langfuse_handler()
        return {"callbacks": [handler]} if handler else {}

    async def _enrich_with_skill_mastery(self, chunks_text: str) -> str:
        """Fetch skill-bar images referenced in chunks and inject mastery alt text.

        Parses <img> tags from the markdown, fetches each raster image from
        knowledge-flow, checks if it's a 214x33 skill bar, counts blue dots,
        and replaces the alt text inline.
        """
        image_refs = parse_image_refs(chunks_text)
        if not image_refs:
            return chunks_text

        client = KfMarkdownMediaClient(agent=self.agent)

        mastery_map: dict[str, int] = {}
        for doc_uid, filename in image_refs:
            if not is_raster_image(filename) or filename in mastery_map:
                continue
            try:
                image_bytes = await client.fetch_media(doc_uid, filename)
                level = extract_mastery_from_image(image_bytes)
                if level is not None:
                    mastery_map[filename] = level
            except httpx.HTTPStatusError:
                continue
            except Exception:
                logger.warning(
                    "[skill_mastery] Failed to fetch %s/%s",
                    doc_uid,
                    filename,
                    exc_info=True,
                )

        if mastery_map:
            logger.info("[skill_mastery] Detected: %s", mastery_map)
            chunks_text = inject_mastery_alt_text(chunks_text, mastery_map)

        return chunks_text

    def _find_search_tool(self):
        """Find the MCP vector search tool by name."""
        tools = self.agent.mcp.get_tools()
        for t in tools:
            if t.name == SEARCH_TOOL_NAME:
                return t
        return None

    async def _generate_queries(
        self, model_class: Type[BaseModel], context_hint: str = ""
    ) -> list[str]:
        """
        Phase 1: LLM generates search queries from schema fields.

        Args:
            model_class: The Pydantic model class to generate queries for
            context_hint: Optional context hint to guide search (e.g., candidate name)

        Returns:
            List of search query strings
        """
        # Human readable names and descriptions for fields
        lines = []
        for name, info in model_class.model_fields.items():
            lines.append(f"- {name}: {info.description or ''}")
        schema_desc = "\n".join(lines)

        prompt = f"""Voici les champs à extraire depuis des documents projet et un CV:

{schema_desc}

Génère un ensemble minimal de requêtes de recherche (en français) pour trouver
toutes les informations nécessaires. Regroupe les champs liés dans une même requête.
{f"Contexte: {context_hint}" if context_hint else ""}

Règles:
- Génère entre 2 et 6 requêtes au total
- Chaque requête doit être courte et ciblée
- Regroupe les champs similaires ensemble
- Utilise le vocabulaire métier approprié"""

        model = get_default_chat_model().with_structured_output(
            SearchQueries, method="json_schema"
        )
        result = await model.ainvoke(
            [SystemMessage(content=prompt)], config=self._build_llm_config()
        )
        if not isinstance(result, SearchQueries):
            result = SearchQueries.model_validate(result)

        logger.info(f"Generated {len(result.queries)} search queries: {result.queries}")
        return result.queries

    async def _search_and_collect(
        self, queries: list[tuple[str, int]]
    ) -> tuple[str, list[str]]:
        """
        Phase 2: Execute queries via MCP, deduplicate, rank, return formatted text.

        Args:
            queries: List of (query, top_k) pairs. top_k controls how many chunks
                are retrieved per query; use higher values for broad queries.

        Returns:
            Tuple of (formatted_text, ranked_titles) where ranked_titles lists
            unique document titles sorted by cumulative relevance score.
        """
        search_tool = self._find_search_tool()
        if not search_tool:
            logger.error("Search tool not found")
            return "❌ Outil de recherche documentaire introuvable.", []

        # Run all queries and collect results
        all_chunks: list[dict] = []
        seen = set()

        for query, top_k in queries:
            try:
                result = await search_tool.ainvoke({"question": query, "top_k": top_k})
                if not result:
                    continue

                for hit in json.loads(result):
                    # Deduplicate by (uid, content prefix)
                    key = (hit.get("uid", ""), hit.get("content", "")[:100])
                    if key not in seen:
                        seen.add(key)
                        all_chunks.append(hit)
            except Exception:
                logger.warning(
                    f"[ExtractionTools] Search failed for query: {query}", exc_info=True
                )

        if not all_chunks:
            return "❌ Aucun document trouvé.", []

        # Sort by score (descending) and keep top chunks
        all_chunks.sort(key=lambda c: c.get("score", 0), reverse=True)
        top_chunks = all_chunks[:MAX_UNIQUE_CHUNKS]

        # Rank document filenames by cumulative score
        filename_scores: dict[str, float] = {}
        for chunk in top_chunks:
            fname = chunk.get("file_name", "")
            if fname:
                filename_scores[fname] = filename_scores.get(fname, 0) + chunk.get(
                    "score", 0
                )
        ranked_filenames = sorted(
            filename_scores, key=lambda f: filename_scores[f], reverse=True
        )

        # Format chunks for the LLM
        formatted_chunks = []
        for i, chunk in enumerate(top_chunks, 1):
            title = chunk.get("title", "Sans titre")
            content = chunk.get("content", "")
            formatted_chunks.append(f"### Extrait {i} (source: {title})\n{content}")

        logger.info(f"Collected {len(top_chunks)} unique chunks from search")
        return "\n\n".join(formatted_chunks), ranked_filenames

    def get_extract_enjeux_besoins_tool(self):
        """Tool to extract project context and missions."""

        @tool
        async def extract_enjeux_besoins(runtime: ToolRuntime, context_hint: str = ""):
            """
            Extrait le contexte et les missions du projet depuis les documents.

            Args:
                context_hint: Indication optionnelle (nom du projet) pour cibler la recherche.

            Returns:
                JSON contenant les enjeux et besoins du projet.
            """
            # Phase 1: Search and collect
            chunks_text, ranked_filenames = await self._search_and_collect(
                ENJEUX_BESOINS_QUERIES
            )
            if chunks_text.startswith("❌"):
                return Command(
                    update={
                        "messages": [
                            ToolMessage(chunks_text, tool_call_id=runtime.tool_call_id)
                        ]
                    }
                )

            # Phase 3: Extract with structured output (no maxLength constraints)
            model = get_default_chat_model().with_structured_output(
                schema_without_max_length(EnjeuxBesoins), method="json_schema"
            )
            extraction_prompt = """Extrais le contexte et les missions du projet depuis les extraits suivants.

RÈGLES IMPORTANTES:
- N'invente RIEN - utilise uniquement les informations présentes dans les extraits
- Si une information n'est pas trouvée, utilise une chaîne vide
- Le contexte doit décrire le projet de manière détaillée (2-3 phrases)
- Les missions doivent résumer les objectifs clés (2-3 phrases)
- Laisse refCahierCharges vide, il sera rempli automatiquement"""

            result = await model.ainvoke(
                [
                    SystemMessage(content=extraction_prompt),
                    HumanMessage(content=chunks_text),
                ],
                config=self._build_llm_config(),
            )
            if not isinstance(result, EnjeuxBesoins):
                result = EnjeuxBesoins.model_construct(**dict(result))

            # Set refCahierCharges from the most relevant document title
            if ranked_filenames:
                result.refCahierCharges = ranked_filenames[0]

            # Return formatted JSON
            json_output = json.dumps(result.model_dump(), ensure_ascii=False, indent=2)
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            f"✅ Enjeux et besoins extraits:\n```json\n{json_output}\n```",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ]
                }
            )

        return extract_enjeux_besoins

    def get_extract_cv_tool(self):
        """Tool to extract CV information."""

        @tool
        async def extract_cv(
            runtime: ToolRuntime, project_context: str = "", context_hint: str = ""
        ):
            """
            Extrait les informations du CV de l'intervenant.

            Args:
                project_context: Contexte projet (issu de extract_enjeux_besoins) pour aligner
                    les compétences et expériences avec le projet.
                context_hint: Indication optionnelle (nom du candidat) pour cibler la recherche.

            Returns:
                JSON contenant les informations du CV.
            """
            # Phase 1: Search and collect
            chunks_text, _ = await self._search_and_collect(CV_QUERIES)
            if chunks_text.startswith("❌"):
                return Command(
                    update={
                        "messages": [
                            ToolMessage(chunks_text, tool_call_id=runtime.tool_call_id)
                        ]
                    }
                )

            # Phase 2: Enrich with skill mastery from blue-dot images
            chunks_text = await self._enrich_with_skill_mastery(chunks_text)

            # Phase 3: Extract with structured output (no maxLength constraints)
            model = get_default_chat_model().with_structured_output(
                schema_without_max_length(CV), method="json_schema"
            )
            extraction_prompt = """Extrais les informations du CV de l'intervenant depuis les extraits suivants.

CONTEXTE PROJET (pour aligner les compétences et expériences):
{project_context}

RÈGLES IMPORTANTES:
- N'invente RIEN - utilise uniquement les informations présentes dans les extraits
- Les compétences et expériences doivent être pertinentes par rapport au contexte projet
- Sélectionne les compétences les plus pertinentes par rapport au projet (max 3 par catégorie)
- COMPÉTENCES INFORMATIQUES: trie par pertinence projet mais ne laisse pas de slots vides inutilement
- Pour les expériences, garde les plus récentes et pertinentes (max 3)
- Pour la maitrise (langues et compétences), utilise une échelle de 1 à 5 (en tant que string):
  "1" = Débutant, "2" = Intermédiaire, "3" = Bon, "4" = Très bon, "5" = Expert
- Si un emplacement de compétence n'est pas rempli (ex: competenceManagement3 est vide),
  la maîtrise associée (maitriseManagement3) DOIT être une chaîne vide "", pas "0"
- LANGUES: NE PAS inclure la langue maternelle du candidat (typiquement le français).
  Inclure uniquement les langues étrangères (Anglais, Espagnol, Allemand, etc.).
- Si une information n'est pas trouvée, utilise une chaîne vide
- STYLE: Rédige TOUJOURS à la troisième personne (pas de "je", "j'ai", "mon").
  Exemple: "A géré une équipe de 5 personnes" et non "J'ai géré une équipe de 5 personnes"."""

            result = await model.ainvoke(
                [
                    SystemMessage(
                        content=extraction_prompt.format(
                            project_context=project_context or "Non fourni"
                        )
                    ),
                    HumanMessage(content=chunks_text),
                ],
                config=self._build_llm_config(),
            )
            if not isinstance(result, CV):
                result = CV.model_construct(**dict(result))

            logger.info(f"Extracted CV: poste={result.poste}")

            # Return formatted JSON
            json_output = json.dumps(result.model_dump(), ensure_ascii=False, indent=2)
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            f"✅ CV extrait:\n```json\n{json_output}\n```",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ]
                }
            )

        return extract_cv

    def get_extract_prestation_financiere_tool(self):
        """Tool to extract financial prestations."""

        @tool
        async def extract_prestation_financiere(
            runtime: ToolRuntime, context_hint: str = ""
        ):
            """
            Extrait les informations de prestation financière depuis les documents.

            Args:
                context_hint: Indication optionnelle pour cibler la recherche.

            Returns:
                JSON contenant les prestations financières.
            """
            # Phase 1: Search and collect
            chunks_text, _ = await self._search_and_collect(
                PRESTATION_FINANCIERE_QUERIES
            )
            if chunks_text.startswith("❌"):
                return Command(
                    update={
                        "messages": [
                            ToolMessage(chunks_text, tool_call_id=runtime.tool_call_id)
                        ]
                    }
                )

            # Phase 3: Extract with structured output (no maxLength constraints)
            model = get_default_chat_model().with_structured_output(
                schema_without_max_length(PrestationFinanciere), method="json_schema"
            )
            extraction_prompt = """Extrais les prestations financières depuis les extraits suivants.

RÈGLES IMPORTANTES:
- N'invente RIEN - utilise uniquement les informations présentes dans les extraits
- Les prix doivent être en euros (nombres entiers)
- La charge est exprimée en unités d'œuvre (jours/homme typiquement)
- Le prixTotal d'une prestation = prix × charge
- Le prixTotal global = somme de tous les prixTotal des prestations
- NE PAS inventer de catégories de prestations. Si aucune information financière
  n'est trouvée dans les extraits, laisse TOUS les champs vides (chaînes vides pour
  les noms, 0 pour les montants). Ne crée pas de titres de catégories avec un coût de 0.
- Remplis uniquement les prestations pour lesquelles tu as des données concrètes
  (nom ET prix/charge). Un nom sans données financières n'est pas une prestation valide."""

            result = await model.ainvoke(
                [
                    SystemMessage(content=extraction_prompt),
                    HumanMessage(content=chunks_text),
                ],
                config=self._build_llm_config(),
            )
            if not isinstance(result, PrestationFinanciere):
                result = PrestationFinanciere.model_construct(**dict(result))

            logger.info(f"Extracted PrestationFinanciere: total={result.prixTotal}€")

            # Return formatted JSON
            json_output = json.dumps(result.model_dump(), ensure_ascii=False, indent=2)
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            f"✅ Prestations financières extraites:\n```json\n{json_output}\n```",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ]
                }
            )

        return extract_prestation_financiere
