import logging

from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph

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

# ---------------------------
# Tuning spec (UI-editable)
# ---------------------------
TUNING = AgentTuning(
    role="Jira backlog and test builder",
    description="Extracts requirements and user stories from project documents to fill a Jira board and build Zephyr tests.",
    mcp_servers=[MCPServerRef(name="mcp-knowledge-flow-mcp-text")],
    tags=[],
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description="You extract requirements and user stories from project documents",  # to fill a Jira board and build Zephyr tests.",
            required=True,
            default="""
Tout d'abord, tu es un Business Analyst expert. En te basant uniquement sur le besoin métier initial, génère une liste d'exigences formelles.

Consignes :
1.  **Génère des exigences fonctionnelles et non-fonctionnelles.**
2.  **Formalisme :** Rédige des exigences claires, concises, non ambiguës et testables.
3.  **ID Unique :** Assigne un ID unique à chaque exigence (ex: EX-FON-001 pour fonctionnelle, EX-NFON-001 pour non-fonctionnelle).
4.  **Priorisation :** Assigne une priorité (Haute, Moyenne, Basse) à chaque exigence.


Ensuite, tu es un Product Owner expert de classe mondiale. Ta mission est de transformer le besoin métier suivant en un ensemble de User Stories de haute qualité, prêtes à être intégrées dans un backlog.

Consignes pour la génération des User Stories :
- Pense comme un véritable Product Owner : décompose la fonctionnalité en stories atomiques, verticales et testables.
- **Cohérence :** Si des exigences sont fournies ci-dessus, assure-toi que les User Stories générées les couvrent et sont en parfaite cohérence avec elles.
- **Couverture Complète :** Couvre tous les parcours utilisateur, y compris le "happy path" et les cas d'erreur. Pense aux différents personas (ex: utilisateur final, administrateur).
- Rédige des titres clairs, des user stories bien formulées ("En tant que...") et des critères d'acceptation précis.

- **EXIGENCE CRITIQUE : Critères d'Acceptation Exhaustifs (Format Gherkin)**
  Pour chaque User Story, tu ne dois PAS te contenter de cas nominaux. Tu dois OBLIGATOIREMENT inclure des critères pour les catégories suivantes :

  1. **Cas Nominaux (Happy Path) :**
     - Le scénario idéal où tout fonctionne comme prévu.

  2. **Validations de Données (Input Validation) :**
     - Règles de format (ex: email invalide, mot de passe trop faible).
     - Champs obligatoires manquants.
     - Limites de caractères (min/max).
     - Types de fichiers non supportés ou trop volumineux.
     - Unicité des données (ex: email déjà utilisé).

  3. **Cas d'Erreur (Error Handling) :**
     - Erreurs techniques (ex: échec de l'appel API, timeout, erreur 500).
     - Erreurs métier (ex: stock insuffisant, solde négatif, droits insuffisants).
     - Gestion de la perte de connexion.

  4. **Cas Limites (Edge Cases) :**
     - Valeurs frontières (ex: 0, 1, max, max+1).
     - Listes vides ou très longues.
     - Dates limites (ex: 29 février, changement d'heure).

  5. **Feedback Utilisateur (UI/UX Messages) :**
     - Le texte EXACT des messages de succès (Toasts, Modales).
     - Le texte EXACT des messages d'erreur affichés à l'utilisateur.
     - États de chargement (Loading states) et boutons désactivés.

- **Formatage Gherkin Strict :** Chaque critère doit suivre la structure :
  "Étant donné que [contexte], Quand [action], Alors [résultat attendu]."

- **Aspects Transverses :** Inclus les aspects de sécurité (OWASP), d'accessibilité (WCAG - navigation clavier, lecteurs d'écran) et de conformité (RGPD) si pertinent.

- **Estimation & Priorisation :**
  - Estime l'effort (Fibonacci : 1, 2, 3, 5, 8, 13, 21).
  - Priorise (Must Have, Should Have, Could Have, Won't Have).

- **Dépendances :** Ordonne les stories logiquement. **AUCUNE dépendance circulaire.**

- **Questions de clarification :** Pour chaque story, ajoute 1 à 3 questions précises pour lever les ambiguïtés.



Finalement, tu es un expert en tests logiciels. Ton rôle est de créer des scénarios de tests détaillés et exploitables.

Instructions principales :
Génère des scénarios de tests complets à partir des informations fournies dans les User Stories (US) suivantes, en suivant le format Gherkin (Etant donné que-Lorsque-Alors) et en incluant les cas nominaux, limites et d'erreur. Toutes les US fournies doivent faire l'objet d'un test.
Tu peux également te baser sur les JDDs fournis en entrée pour les personas de chaque tests

Format de réponse attendu 📝 pour chaque scénario :
1. **ID du Scénario** : Un identifiant unique (ex: SC-001, SC-LOGIN-001).
2. **userStoryId**: L'ID de la User Story couverte par ce test.
3. **Titre du Scénario** : Un titre concis décrivant l'objectif du test.
4. **Description** : Une brève explication de ce que le scénario teste.
5. **Préconditions** : Les états ou données nécessaires avant l'exécution du test.
6. **Étapes** : Au format Gherkin présentées sous forme de tableau avec les colonnes suivantes : Numéro (#1, #2, ...), Action (Etant donné que - Lorsque), Résultat attendu (Alors).
7. **Données de test** : Jeux de données nécessaires
8. **Priorité** : (Haute, Moyenne, Basse) Indiquant l'importance du test.
9. **type**: Le type de cas de test (Nominal, Limite, Erreur).
""",
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="chat_options.attach_files",
            type="boolean",
            title="Allow file attachments",
            description="Show file upload/attachment controls for this agent.",
            required=False,
            default=False,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.libraries_selection",
            type="boolean",
            title="Document libraries picker",
            description="Let users select document libraries/knowledge sources for this agent.",
            required=False,
            default=False,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.search_policy_selection",
            type="boolean",
            title="Search policy selector",
            description="Expose the search policy toggle (hybrid/semantic/strict).",
            required=False,
            default=False,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.search_rag_scoping",
            type="boolean",
            title="RAG scope selector",
            description="Expose the RAG scope control (documents-only vs hybrid vs knowledge).",
            required=False,
            default=False,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.deep_search_delegate",
            type="boolean",
            title="Deep search delegate toggle",
            description="Allow delegation to a senior agent for deep search.",
            required=False,
            default=False,
            ui=UIHints(group="Chat options"),
        ),
    ],
)


@expose_runtime_source("agent.Jim")
class JiraAgent(AgentFlow):
    """Simple ReAct agent used for dynamic UI-created agents."""

    tuning = TUNING
    default_chat_options = AgentChatOptions(
        search_policy_selection=False,
        libraries_selection=False,
        search_rag_scoping=False,
        deep_search_delegate=False,
        attach_files=False,
    )

    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context=runtime_context)
        self.mcp = MCPRuntime(agent=self)
        await self.mcp.init()

    async def aclose(self):
        await self.mcp.aclose()

    def get_compiled_graph(self) -> CompiledStateGraph:
        base_prompt = self.render(self.get_tuned_text("prompts.system") or "")
        return create_agent(
            model=get_default_chat_model(),
            system_prompt=base_prompt,
            tools=[*self.mcp.get_tools()],
            checkpointer=self.streaming_memory,
        )
