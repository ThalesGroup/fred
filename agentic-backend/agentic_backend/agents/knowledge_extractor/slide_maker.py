from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from jsonschema import Draft7Validator
from langchain.agents import create_agent
from langchain.agents.middleware import after_model
from langchain.tools import tool
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer

from agentic_backend.agents.knowledge_extractor.jsonschema import globalSchema
from agentic_backend.agents.knowledge_extractor.powerpoint_template_util import (
    fill_slide_from_structured_response,
)
from agentic_backend.agents.knowledge_extractor.tool_validator import (
    create_tool_call_validator_middleware,
    has_validation_error,
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

🚨 RÈGLE SPÉCIALE POUR LES DONNÉES FINANCIÈRES (prestationFinanciere) :
- Les montants, tarifs, TJM, budgets doivent être EXPLICITEMENT écrits dans les documents
- INTERDIT d'estimer, déduire, ou calculer des montants financiers
- Si le montant exact n'est pas écrit en toutes lettres → champ vide ("")
- Exemples :
  * Document dit "TJM: 600€" → ✅ tu peux utiliser 600
  * Document dit "profil senior" → ❌ ne déduis PAS un TJM, laisse vide
  * Document dit "budget conséquent" → ❌ laisse vide, pas de montant explicite

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
e) Informations financières (requête : "tarif coût TJM budget prestation" - si aucun montant EXPLICITE trouvé, laisse tous les champs financiers vides)

Paramètres : top_k=7, search_policy='semantic'
Si résultats insuffisants : reformule avec des synonymes et réessaie

⚠️ RAPPEL : Pour les données financières, cherche des MONTANTS EXPLICITES uniquement (nombres + devise). Aucune déduction autorisée.

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
- Appelle template_tool avec le JSON validé (sans afficher de texte, appel silencieux)
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
- **search_policy** : 'semantic' par défaut pour informations conceptuelles
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
- Après génération réussie : fournis le lien + résumé comme spécifié ci-dessous (sans montrer le JSON)

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

    async def astream_updates(self, state, *, config, **kwargs):
        """
        Clauded
        Override to add validation retry logic.
        If the agent generates a tool call validation error, automatically retry up to 2 times.
        """
        max_retries = 2
        current_state = state

        for attempt in range(max_retries + 1):
            logger.info(f"Agent execution attempt {attempt + 1}/{max_retries + 1}")

            # Collect events without yielding them yet (in case we need to retry)
            collected_events = []
            final_state_messages = []

            async for event in super().astream_updates(
                current_state,  # type: ignore
                config=config,
                **kwargs,
            ):
                collected_events.append(event)

                # Collect messages from events to check for validation errors
                for node_name, node_data in event.items():
                    if isinstance(node_data, dict) and "messages" in node_data:
                        final_state_messages = node_data["messages"]

            # Check if there's a validation error in the final state
            if has_validation_error(final_state_messages):
                if attempt < max_retries:
                    logger.warning(
                        f"⚠️ Validation error detected on attempt {attempt + 1}. "
                        f"Retrying automatically ({attempt + 1}/{max_retries} retries used)..."
                    )
                    # Update state with the error message for retry
                    current_state = {"messages": final_state_messages}
                    # DON'T yield events from failed attempts - discard them
                    # Continue to next retry
                    continue
                else:
                    logger.error(
                        f"❌ Validation errors persist after {max_retries} retries. "
                        f"Giving up and returning events with error."
                    )
                    # Yield the events even with error (last attempt)
                    for event in collected_events:
                        yield event
                    break
            else:
                # No validation error - success! Yield all collected events
                if attempt > 0:
                    logger.info(
                        f"✅ Agent succeeded after {attempt} retry(ies). Validation passed."
                    )
                for event in collected_events:
                    yield event
                break

    def get_compiled_graph(
        self, checkpointer: Checkpointer | None = None
    ) -> CompiledStateGraph:
        template_tool = self.get_template_tool()
        validator_tool = self.get_validator_tool()

        # Get all tool names for validation (including MCP tools)
        all_tool_names = ["template_tool", "validator_tool"]
        # Add MCP tool names dynamically
        mcp_tools = self.mcp.get_tools()
        all_tool_names.extend([t.name for t in mcp_tools])

        # Create validator middleware for all available tools
        tool_call_validator = create_tool_call_validator_middleware(
            tool_names=all_tool_names
        )

        @after_model
        def validate_tool_calls(state, runtime):
            """Validate tool calls and provide feedback if malformed"""
            return tool_call_validator(state, runtime)

        return create_agent(
            model=get_default_chat_model(),
            system_prompt=self.render(self.get_tuned_text("prompts.system") or ""),
            tools=[template_tool, validator_tool, *self.mcp.get_tools()],
            checkpointer=checkpointer,
            middleware=[validate_tool_calls],
        )

    def get_validator_tool(self):
        @tool
        async def validator_tool(data: dict):
            """
            Outil permettant de valider le format des données avant de les passer à l'outil de templetisation.
            L'outil retourne [] si le schéma est valide et la liste des erreurs sinon.
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

            validator = Draft7Validator(globalSchema)
            errors = " | ".join(
                [shorten_error_message(e) for e in validator.iter_errors(data)]
            )
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
            template_path = await self.fetch_config_blob_to_tempfile(
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
                upload_result = await self.upload_user_blob(
                    key=final_key,
                    file_content=f_out,
                    filename=f"Generated_Slide_{self.get_name()}.pptx",
                    content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )

                # 4. Construct the structured message for the UI
                final_download_url = upload_result.download_url

            return LinkPart(
                href=final_download_url,
                title=f"Download {upload_result.file_name}",
                kind=LinkKind.download,
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )

        return template_tool
