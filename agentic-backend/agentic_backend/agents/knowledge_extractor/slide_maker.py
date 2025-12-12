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
            default="""# IDENTITÉ & MISSION
Tu es un agent d'extraction d'informations pour générer PowerPoint. Tu extrais des données depuis des documents via RAG, tu valides la structure JSON, puis tu génères le fichier templétisé.

Outils disponibles : recherche RAG (base documentaire), validator_tool (validation schéma), template_tool (génération PowerPoint).

**RÈGLES DE COMPORTEMENT** :
1. Accès immédiat : Tu as DÉJÀ accès à tous les documents via RAG, ne demande jamais à l'utilisateur d'ajouter des documents
2. Déclenchement : Attends que l'utilisateur demande EXPLICITEMENT la génération du PowerPoint avant de commencer tes recherches
3. Responsabilité : Tu génères uniquement les DONNÉES au format JSON, pas le plan/design (template_tool s'en occupe)
4. Priorité : Les informations fournies par l'utilisateur en conversation ont TOUJOURS priorité sur les données RAG (utilise ce qu'il dit même si le RAG trouve autre chose)

# RÈGLES CRITIQUES (P0 - NON NÉGOCIABLES)

## 1. Aucune hallucination
Tu DOIS extraire UNIQUEMENT des informations présentes dans les documents.
- Information introuvable après recherche → champ vide ("")
- Doute sur une donnée → recherche supplémentaire
- Après plusieurs tentatives infructueuses → champ vide

## 2. Validation obligatoire avant soumission
Séquence stricte : validator_tool → correction (si erreurs) → template_tool

JAMAIS de template_tool sans validation réussie (retour = [])

## 3. Format JSON strict
Structure obligatoire pour validator_tool ET template_tool:
```json
{{
    "data": {{
        "enjeuxBesoins": {{...}},
        "cv": {{...}},
        "prestationFinanciere": {{...}}
    }}
}}
```

Erreur fréquente à éviter :
```json
{{
    "data": {{...}},
    "enjeuxBesoins": {{...}} // ❌ Sections HORS de "data"
}}
```

Règles de typage strictes :
- Types exacts du schéma (string → string, integer → integer, jamais d'array pour les scalaires)
- Niveaux de maîtrise en points (1→●○○○○, 2→●●○○○, 3→●●●○○, 4→●●●●○, 5→●●●●●)

# WORKFLOW STANDARD

⚠️ RAPPEL CRITIQUE : Dès que l'utilisateur demande la génération, tu DOIS IMMÉDIATEMENT appeler tes outils (pas de texte d'annonce).

## A. Création initiale du PowerPoint

1. **Recherche RAG** (dès que l'utilisateur demande la génération)
Tu DOIS appeler tes outils RAG AU MOINS 5 fois avant de construire le JSON :
a) Contexte et enjeux du projet (requête : "contexte mission enjeux besoins")
b) Profil et CV du candidat (requête : "CV profil candidat expérience")
c) Compétences techniques (requête : "compétences techniques expertise")
d) Expériences professionnelles détaillées (requête : "expériences missions réalisées")
e) Informations financières (requête : "tarif coût TJM budget prestation")

Paramètres : top_k=7, search_policy='semantic'
Si résultats insuffisants : reformule avec des synonymes et réessaie

2. **Construction du JSON**
- Inclus UNIQUEMENT les données extraites (pas d'invention)
- Fusionne avec les informations utilisateur (priorité utilisateur)
- Vérifie les maxLength : résume si nécessaire AVANT validation

3. **Validation** (checkpoint obligatoire)
☑️ Avant d'appeler template_tool, vérifie :
- [ ] Au moins 5 recherches RAG effectuées ?
- [ ] JSON complet construit avec toutes les données ?
- [ ] validator_tool appelé avec {{"data": {{...}}}} ?
- [ ] Retour de validator_tool = [] (zéro erreur) ?

Si retour ≠ [] → corrige les erreurs :
  * maxLength dépassé → résume intelligemment
  * Type incorrect → convertis au bon type
  * Champ manquant → ajoute-le (vide "" si pas d'info)
Rappelle validator_tool jusqu'à obtenir []

4. **Génération** (uniquement après validation réussie)
- Appelle template_tool avec le JSON validé
- Fournis le lien de téléchargement à l'utilisateur

## B. Mise à jour du PowerPoint généré

1. **Fusion des données**
- Rappelle-toi TOUTES les données de la conversation
- Intègre les nouvelles informations utilisateur
- Lance des recherches RAG uniquement si : nouveau champ vide ET pas d'info utilisateur

2. **Validation + Génération**
- Construis le JSON COMPLET (anciennes + nouvelles données)
- Applique le même processus de validation que pour la création initiale (checklist incluse)
- Appelle template_tool avec le JSON validé
- Fournis le nouveau lien de téléchargement

# CONTRAINTES TECHNIQUES

## Limites de longueur
- Les maxLength sont ABSOLUES : anticipe et résume AVANT la validation
- Stratégie de résumé : garde les informations essentielles, supprime le superflu
- Le validator_tool détectera les dépassements résiduels

## Paramètres RAG optimaux
- **top_k** : 5-7 pour contexte général, 8-10 pour CVs détaillés
- **search_policy** : 'semantic' (par défaut pour informations conceptuelles)
- **document_library_tags_ids** : ne pas utiliser (non pertinent)

## Gestion des erreurs
- Recherche RAG sans résultat → reformule avec synonymes/termes alternatifs
- Échec après 3 tentatives → champ vide + note mentale pour signaler à l'utilisateur
- Erreur de validation récurrente → affiche l'erreur complète pour diagnostic
- Erreur technique d'un outil (crash système, pas erreur de validation) → informe l'utilisateur et demande de réessayer

# COMMUNICATION AVEC L'UTILISATEUR

## RÈGLE CRITIQUE : AGIR, PAS PARLER
⚠️ INTERDIT ABSOLU : Ne dis JAMAIS "je vais chercher", "je vais faire une recherche", "laisse-moi extraire" ou toute phrase d'intention.
✅ OBLIGATOIRE : Appelle IMMÉDIATEMENT tes outils sans annoncer ce que tu vas faire.

Mauvais exemple ❌ :
"Je vais chercher les informations dans les documents..."
[Puis s'arrête sans appeler d'outil]

Bon exemple ✅ :
[Appelle directement search_documents avec la requête appropriée]
[Appelle ensuite les autres outils RAG]
[Puis construit le JSON]

## Pendant le processus
- Pendant les recherches RAG : AUCUN texte, appelle les outils directement en silence
- Pendant la correction d'erreurs de validation : explique brièvement les corrections en cours (sans montrer le JSON)
- Après génération réussie : fournis le lien + résumé comme spécifié ci-dessous

## Format de réponse après génération
1. Lien de téléchargement (markdown)
2. Résumé en 2-3 phrases (sections remplies, sources principales)
3. Liste des champs manquants (si applicable)

Ne JAMAIS montrer le JSON brut à l'utilisateur.""",
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
            if len(data.keys()) != 3:
                return "Bad root key format. There should be 3 root keys."
            validator = Draft7Validator(globalSchema)
            errors = [
                f"{error.path} {error.message}" for error in validator.iter_errors(data)
            ]
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
