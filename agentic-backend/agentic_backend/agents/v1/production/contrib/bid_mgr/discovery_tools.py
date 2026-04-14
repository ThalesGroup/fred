"""Discovery tools for Bid Manager agent — 4 independent tender analysis tools."""

import json
import logging

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import SystemMessage
from pydantic import BaseModel

from agentic_backend.agents.v1.production.contrib.bid_mgr.pydantic_models import (
    AttentesResult,
    RiskAnalysisResult,
    SyntheseResult,
)
from agentic_backend.application_context import get_default_chat_model

logger = logging.getLogger(__name__)

SEARCH_TOOL_NAME = "search_documents_using_vectorization"
TOP_K_PER_QUERY = 10
MAX_UNIQUE_CHUNKS = 30

# ---------------------------------------------------------------------------
# RAG queries per tool
# ---------------------------------------------------------------------------

SYNTHESE_QUERIES = [
    "type de consultation procédure appel d'offres RFI RFP RFQ MAPA accord-cadre",
    "objet du marché périmètre missions prestations attendues",
    "date limite soumission remise offre délai calendrier",
    "durée du marché reconduction période",
    "pouvoir adjudicateur acheteur entité contractante",
    "présentation client organisation secteur activités missions contexte institutionnel",
    "contexte projet situation actuelle système information existant transformation migration besoins enjeux",
    "modèle économique forfait régie BPU prix unitaires accord-cadre conditions financières",
]

ATTENTES_QUERIES = [
    "exigences techniques spécifications fonctionnelles performances architecture",
    "sécurité cybersécurité intégration hébergement souveraineté données",
    "exigences organisationnelles gouvernance équipe maintenance support formation",
    "propriété intellectuelle droits cession sous-traitance réversibilité portabilité",
    "critères évaluation pondération notation barème grille jugement offres",
    "SLA SLO niveaux de service disponibilité pénalités contractuelles obligation résultat",
]

RISK_ANALYSIS_QUERIES = [
    "clauses pénalités résiliation conditions inhabituelles sensibles",
    "obligations résultat livrables contractuels exigences bloquantes",
    "risques juridiques sous-traitance responsabilité assurances",
    "contraintes délais jalons planning budget conditions paiement",
    "habilitations sécurité contraintes réglementaires RGPD conformité",
    "livrables attendus mémoire technique formulaires attestations réponse",
]

# ---------------------------------------------------------------------------
# LLM prompts per tool
# ---------------------------------------------------------------------------

SYNTHESE_PROMPT = """Tu es un analyste expert en marchés publics.
À partir des extraits documentaires ci-dessous, extrais les métadonnées clés et rédige une section narrative.

## Extraits documentaires

{chunks}

## Consignes

**executive_summary** (champs structurés) :
- tender_title : titre exact de l'AO
- client : entité acheteuse / pouvoir adjudicateur
- tender_type : type de consultation (RFP, RFI, RFQ, Appel d'offres ouvert, Appel d'offres restreint, MAPA, Accord-cadre...)
- economic_model : modèle économique du contrat (FFP/forfait, T&M/régie, BPU/DQE, Cost+, Accord-cadre, hybride) — null si non précisé
- scope : périmètre et objet du marché (2-3 phrases)
- submission_deadline : date limite de remise des offres — null si non mentionnée
- contract_duration : durée du marché (y compris reconductions) — null si non mentionnée
- procedure_type : type de procédure formelle si précisé, sinon null
- allotissement : description des lots si le marché est alloti, sinon null
- key_structuring_elements : points structurants du cahier des charges (contraintes majeures, exigences clés, conditions particulières) — max 8

**executive_overview** : synthèse narrative de 8 à 10 lignes couvrant l'objet, le périmètre, les conditions clés et les enjeux principaux du marché.

**client_presentation** : secteur d'activité du client, principales missions/activités, contexte organisationnel.

**project_context** : situation actuelle (SI existant, contexte opérationnel), problèmes et enjeux à résoudre, type de solutions attendues.

⚠️ N'invente RIEN. Si une information n'est pas dans les extraits, omets-la."""

ATTENTES_PROMPT = """Tu es un analyste expert en marchés publics.
À partir des extraits documentaires ci-dessous, extrais toutes les exigences et critères d'évaluation.

## Extraits documentaires

{chunks}

## Consignes

**technical_requirements** : exigences techniques (fonctionnalités, performances, SLA, sécurité, architecture, intégration)
**organizational_requirements** : exigences organisationnelles (gouvernance, méthodologie, comitologie, formation, maintenance, support)
**administrative_requirements** : exigences administratives/contractuelles (pénalités, garanties, PI, sous-traitance, facturation)

Pour chaque exigence : title (titre court) + description (détaillée).

**evaluation_criteria** : critères d'évaluation avec name, weight (ex: "60%" ou null), description.

**key_contractual_clauses** : clauses contractuelles à fort impact (uniquement celles présentes dans les extraits). Pour chaque clause :
- category : exactement l'une de ces valeurs : 'Pénalités', 'SLA/SLO', 'Propriété intellectuelle / Souveraineté', 'Réversibilité', 'Obligation (moyens/résultat)'
- title : intitulé court
- description : contenu et impact contractuel
- criticality : 'Élevée', 'Moyenne', 'Faible', ou null

⚠️ N'invente RIEN. Base-toi UNIQUEMENT sur les extraits fournis."""

RISK_ANALYSIS_PROMPT = """Tu es un expert juridique et contractuel en marchés publics.
À partir des extraits documentaires ci-dessous, réalise une analyse de risques exhaustive du CCTP et des documents contractuels.

## Extraits documentaires

{chunks}

## Consignes

**risks** : Identifie environ 20 risques, classés par priorité :
- P0 = Risque bloquant / rédhibitoire (remet en cause la candidature)
- P1 = Risque élevé (impact fort sur marge, planning ou engagement)
- P2 = Risque moyen (à surveiller, mitigation possible)
- P3 = Point de vigilance / risque faible

Pour chaque risque : title (court), priority (P0/P1/P2/P3), description (détaillée), mitigation (piste si pertinente, sinon null).
Couvre les domaines : clauses contractuelles, délais, budget, obligations de résultat, sécurité/habilitations, propriété intellectuelle, sous-traitance, réversibilité, SLA/pénalités.

**constraints** : Contraintes majeures (délais, budget, localisation, sécurité, réglementaire). Title + description.

**deliverables** : Tous les livrables attendus dans la réponse (mémoire technique, offre financière, attestations, formulaires, planning...). Title + description.

⚠️ N'invente RIEN. Base-toi UNIQUEMENT sur les extraits fournis."""

GO_NO_GO_PROMPT = """Tu es un analyste senior en marchés publics avec une expertise dans les secteurs Défense et Secteur Public.

## Contexte Thales

Tu analyses cet appel d'offres du point de vue de **Thales Services Numériques**, business unit **Défense et Secteur Public**, business line **Systèmes d'Information de Sécurité Critiques** (SISC).
Thales est un acteur de référence dans les systèmes d'information critiques, la cybersécurité, l'intégration de systèmes complexes et les solutions de commandement pour la Défense et la Sécurité.

## Consignes

Rédige en markdown les sections suivantes :

## Analyse SWOT

Du point de vue de Thales — listes à puces pour chaque quadrant :

**Forces** : atouts de Thales pour ce marché (compétences, références, positionnement, relation client)
**Faiblesses** : risques internes (écarts exigences, ressources, sous-traitance nécessaire)
**Opportunités** : intérêts stratégiques (nouveau client, marché récurrent, synergies portefeuille)
**Menaces** : risques externes (concurrence, clauses contractuelles risquées, délais, instabilité budgétaire)

## Recommandation Go / No-Go

- **Recommandation** : GO, NO-GO ou GO CONDITIONNEL
- **Niveau de confiance** : Haute, Moyenne ou Faible
- **Arguments pour** : max 5 points concrets
- **Arguments contre** : max 5 points concrets
- **Conditions** : uniquement si GO CONDITIONNEL
- **Justification** : 3-4 phrases motivant la recommandation

## Thèmes Gagnants (Win Themes)

Identifie 3 à 5 Win Themes — messages différenciants structurant la proposition :
- Titre percutant (8 mots max) + 1-2 phrases ancrant l'avantage dans un besoin client explicite ou un critère d'évaluation
- Évite les formules génériques (« expertise reconnue », « approche agile »)

## Stratégie de Réponse

- **PTW (Price to Win)** : positionnement tarifaire recommandé au regard du modèle économique identifié et des risques financiers
- **USP / CVP** : 2-3 propositions de valeur différenciantes Thales pour ce marché

Base ta recommandation sur l'analyse du dossier produite par les outils précédents (synthese, attentes_et_reponses, analyse_risques_cctp) : alignement avec l'expertise Thales, risques identifiés (dont clauses contractuelles clés), contraintes, et attractivité stratégique du marché."""


# ---------------------------------------------------------------------------
# Tools class
# ---------------------------------------------------------------------------


class DiscoveryTools:
    """Four independent tender dossier analysis tools."""

    def __init__(self, agent):
        self.agent = agent

    def _find_search_tool(self):
        """Find the MCP vector search tool by name."""
        tools = self.agent.mcp.get_tools()
        for t in tools:
            if t.name == SEARCH_TOOL_NAME:
                return t
        return None

    async def _run_rag_queries(self, search_tool, queries: list[str]) -> list[dict]:
        """Run multiple RAG queries, deduplicate and rank results."""

        all_chunks: list[dict] = []
        seen: set[tuple] = set()

        for query in queries:
            try:
                result = await search_tool.ainvoke(
                    {"question": query, "top_k": TOP_K_PER_QUERY}
                )
                if not result:
                    continue
                for hit in json.loads(result):
                    key = (hit.get("uid", ""), hit.get("content", "")[:100])
                    if key not in seen:
                        seen.add(key)
                        all_chunks.append(hit)
            except Exception:
                logger.warning(
                    "[DiscoveryTools] Search failed for query: %s",
                    query,
                    exc_info=True,
                )

        all_chunks.sort(key=lambda c: c.get("score", 0), reverse=True)
        return all_chunks[:MAX_UNIQUE_CHUNKS]

    def _format_chunks(self, chunks: list[dict]) -> str:
        """Format chunks as markdown for LLM context."""
        formatted = []
        for i, chunk in enumerate(chunks, 1):
            title = chunk.get("title", "Sans titre")
            content = chunk.get("content", "")
            formatted.append(f"### Extrait {i} (source: {title})\n{content}")
        return "\n\n".join(formatted)

    async def _extract_structured(
        self, model_class: type[BaseModel], prompt: str, chunks_text: str
    ) -> BaseModel:
        """Call LLM with structured output for a given prompt and chunks."""
        model = get_default_chat_model().with_structured_output(
            model_class, method="json_schema"
        )
        result = await model.ainvoke(
            [SystemMessage(content=prompt.format(chunks=chunks_text))],
        )
        if not isinstance(result, model_class):
            result = model_class.model_validate(result)
        return result

    def _no_docs_error(self) -> str:
        return "Aucun document trouvé. Vérifiez qu'une bibliothèque documentaire contenant le dossier d'AO est sélectionnée."

    def _no_search_tool_error(self) -> str:
        return "Outil de recherche documentaire introuvable. Vérifiez la connexion au serveur MCP."

    # -----------------------------------------------------------------------
    # Tool 1: synthese
    # -----------------------------------------------------------------------

    def get_synthese_tool(self):
        """Tool: executive summary, client presentation and project context."""

        @tool
        async def synthese(runtime: ToolRuntime):
            """
            Synthèse du dossier d'appel d'offres :
            - Type de consultation (RFI, RFP, RFQ, MAPA, Accord-cadre...)
            - Dates clés et durée du marché
            - Présentation du client / pouvoir adjudicateur
            - Contexte et enjeux du projet
            - Périmètre, modèle économique et éléments structurants

            Aucun paramètre nécessaire.
            """
            search_tool = self._find_search_tool()
            if not search_tool:
                return self._no_search_tool_error()

            chunks = await self._run_rag_queries(search_tool, SYNTHESE_QUERIES)
            if not chunks:
                return self._no_docs_error()

            chunks_text = self._format_chunks(chunks)
            p1 = await self._extract_structured(
                SyntheseResult, SYNTHESE_PROMPT, chunks_text
            )
            assert isinstance(p1, SyntheseResult)
            return p1.model_dump_json(indent=2)

        return synthese

    # -----------------------------------------------------------------------
    # Tool 2: attentes_et_reponses
    # -----------------------------------------------------------------------

    def get_attentes_reponses_tool(self):
        """Tool: requirements, evaluation criteria and key contractual clauses."""

        @tool
        async def attentes_et_reponses(runtime: ToolRuntime):
            """
            Analyse des attentes du client et des éléments de réponse :
            - Exigences techniques, organisationnelles et administratives
            - Critères d'évaluation et pondérations
            - Clauses contractuelles clés (pénalités, SLA, PI, réversibilité...)

            Aucun paramètre nécessaire.
            """
            search_tool = self._find_search_tool()
            if not search_tool:
                return self._no_search_tool_error()

            chunks = await self._run_rag_queries(search_tool, ATTENTES_QUERIES)
            if not chunks:
                return self._no_docs_error()

            chunks_text = self._format_chunks(chunks)
            p2 = await self._extract_structured(
                AttentesResult, ATTENTES_PROMPT, chunks_text
            )
            assert isinstance(p2, AttentesResult)
            return p2.model_dump_json(indent=2)

        return attentes_et_reponses

    # -----------------------------------------------------------------------
    # Tool 3: analyse_risques_cctp
    # -----------------------------------------------------------------------

    def get_analyse_risques_tool(self):
        """Tool: CCTP risk analysis with P0–P3 prioritization."""

        @tool
        async def analyse_risques_cctp(runtime: ToolRuntime):
            """
            Analyse de risques du CCTP — environ 20 risques priorisés :
            - P0 : Risque bloquant / rédhibitoire
            - P1 : Risque élevé
            - P2 : Risque moyen
            - P3 : Point de vigilance

            Inclut également les contraintes majeures et les livrables attendus dans la réponse.

            Aucun paramètre nécessaire.
            """
            search_tool = self._find_search_tool()
            if not search_tool:
                return self._no_search_tool_error()

            chunks = await self._run_rag_queries(search_tool, RISK_ANALYSIS_QUERIES)
            if not chunks:
                return self._no_docs_error()

            chunks_text = self._format_chunks(chunks)
            result = await self._extract_structured(
                RiskAnalysisResult, RISK_ANALYSIS_PROMPT, chunks_text
            )
            assert isinstance(result, RiskAnalysisResult)
            return result.model_dump_json(indent=2)

        return analyse_risques_cctp

    # -----------------------------------------------------------------------
    # Tool 4: go_no_go
    # -----------------------------------------------------------------------

    def get_go_no_go_tool(self):
        """Tool: SWOT analysis and Go/No-Go recommendation."""

        @tool
        async def go_no_go(runtime: ToolRuntime):
            """
            Proposition Go / No-Go pour l'appel d'offres, basée sur l'analyse produite
            par les outils précédents (synthese, attentes_et_reponses, analyse_risques_cctp) :
            - Analyse SWOT (Forces, Faiblesses, Opportunités, Menaces) du point de vue Thales
            - Recommandation Go / No-Go / Go Conditionnel avec justification
            - Thèmes Gagnants (Win Themes)
            - Stratégie de réponse (PTW, USP/CVP)

            Appeler de préférence après synthese(), attentes_et_reponses() et analyse_risques_cctp().
            Aucun paramètre nécessaire.
            """
            result = await get_default_chat_model().ainvoke(
                [SystemMessage(content=GO_NO_GO_PROMPT)],
            )
            return str(result.content)

        return go_no_go
