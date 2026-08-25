from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import uuid4

from fred_core.common import TeamId

from control_plane_backend.prompts.category_store import (
    PromptCategoryAlreadyExistsError,
    PromptCategoryRecord,
    PromptCategoryStore,
)
from control_plane_backend.prompts.store import (
    PromptAlreadyExistsError,
    PromptRecord,
    PromptStore,
)


@dataclass(frozen=True)
class StarterPromptSpec:
    """One prompt seeded into a team's library at team creation (PROMPT-09).

    Unlike the platform default prompts this replaces, starter-kit prompts are
    real, persisted, per-team rows: every team gets its own editable copy, not
    a shared read-only catalog projected at query time.
    """

    category_name: str
    name: str
    description: str
    text: str


# Category names seeded for every new team. Real `prompt_category` rows are
# created from this list — editors can then rename, add to, or delete them
# freely; this is only the starting point.
STARTER_CATEGORY_NAMES: list[str] = [
    "Création agent",
    "Analyse et synthèse",
    "Stratégie et idéation",
    "Communication",
]


STARTER_PROMPTS: list[StarterPromptSpec] = [
    StarterPromptSpec(
        category_name="Analyse et synthèse",
        name="Vulgarisation Technique",
        description="Simplifie un sujet technique en une explication claire et imagée, calibrée pour l'auditoire visé.",
        text=(
            "Explique le concept de [Concept complexe] à un public de "
            "[Type de public, ex: débutants/décideurs]. Utilise une métaphore "
            "concrète et limite l'explication à trois points clés."
        ),
    ),
    StarterPromptSpec(
        category_name="Stratégie et idéation",
        name="Brainstorming Inversé",
        description="Anticipe les causes d'échec d'un projet pour en tirer des actions préventives concrètes.",
        text=(
            "Nous voulons réussir le projet suivant : [Description du projet]. "
            "Liste 5 façons infaillibles de faire échouer ce projet. Ensuite, "
            "pour chaque point d'échec, propose une action préventive pour l'éviter."
        ),
    ),
    StarterPromptSpec(
        category_name="Communication",
        name="Approche Diplomate",
        description="Formule un message délicat de façon posée et constructive, pour débloquer une situation sans envenimer la relation.",
        text=(
            "Rédige un email professionnel et diplomate à l'attention de "
            "[Nom du destinataire] pour lui signaler que [Raison du problème, "
            "ex: son livrable est en retard]. L'objectif est de débloquer la "
            "situation sans créer de conflit."
        ),
    ),
    StarterPromptSpec(
        category_name="Création agent",
        name="Agent : synthèse de document",
        description="Configure un agent de synthèse documentaire strict, sans hallucination, avec un format de sortie fixe.",
        text=(
            "# MISSION\n"
            'Tu es "Synthex", un agent IA expert en analyse documentaire et en extraction d\'informations complexes. \n'
            "Ton objectif unique est de traiter les documents fournis par l'utilisateur pour en restituer des synthèses fidèles, structurées et directement actionnables.\n"
            "\n"
            "# POSTURE ET TON\n"
            "- Professionnel, neutre et purement factuel.\n"
            "- Tu ne fais pas de conversation superflue. Tu vas directement à l'essentiel.\n"
            "- Tu n'exprimes aucune opinion personnelle sur le contenu analysé.\n"
            "\n"
            "# RÈGLES COGNITIVES ET GARDE-FOUS (STRICT)\n"
            "1. FRACTURE COGNITIVE : Tu dois considérer tes connaissances pré-entraînées et le document de l'utilisateur comme deux mondes strictement isolés. \n"
            "2. VÉRITÉ ABSOLUE : La seule source de vérité acceptable est le contenu explicite du document fourni (ou du contexte injecté).\n"
            "3. ANTI-HALLUCINATION : Si une information n'est pas dans le texte, tu ne l'inventes pas. Si l'utilisateur pose une question dont la réponse ne figure pas dans le document, tu dois répondre EXACTEMENT : \"L'information demandée ne figure pas dans le document fourni.\"\n"
            "4. AUCUNE DÉDUCTION HASARDEUSE : Ne fais pas de liens logiques qui ne sont pas explicitement justifiés par l'auteur du document.\n"
            "\n"
            "# PROTOCOLE DE TRAITEMENT\n"
            "Lorsque tu reçois un document, applique silencieusement la méthodologie suivante avant de générer ta réponse :\n"
            "- Étape 1 (Macro) : Identifie la thèse principale ou l'intention de l'auteur.\n"
            "- Étape 2 (Méso) : Repère les arguments clés, les données chiffrées pertinentes et les décisions/actions.\n"
            '- Étape 3 (Micro) : Exclus le "bruit" (anecdotes secondaires, répétitions).\n'
            "\n"
            "# STRUCTURE DE SORTIE PAR DÉFAUT\n"
            "Sauf instruction contraire de l'utilisateur, toute synthèse globale doit obligatoirement respecter ce format Markdown :\n"
            "\n"
            "## 🎯 Executive Summary\n"
            "[Un paragraphe de 3 à 5 phrases résumant l'essence du document]\n"
            "\n"
            "## 🔑 Points Clés\n"
            "- [Point 1 : Idée + donnée ou justification chiffrée si présente]\n"
            "- [Point 2 : ...]\n"
            "- [Point 3 : ...]\n"
            "\n"
            "## 🚀 Actions & Décisions\n"
            '- [Action 1 : Quoi + Qui + Quand, si applicable. Sinon, indiquer "Aucune action explicite identifiée"]\n'
            "\n"
            "## ⚠️ Zones d'Ombre (Optionnel)\n"
            "[Mentionne ici si un passage du texte est tronqué, ambigu ou manque de contexte pour être pleinement compris]"
        ),
    ),
]


async def seed_starter_kit(
    team_id: TeamId,
    *,
    prompt_store: PromptStore,
    category_store: PromptCategoryStore,
) -> None:
    """Write the starter categories + prompts into one team's prompt library.

    Why this function exists:
    - two call sites need the exact same content and linkage: `create_team`
      (PROMPT-09, collaborative teams) and the lazy personal-space seeding in
      `product.service` (#2410, personal teams are virtual and never go
      through `create_team`)

    Convergent by design: each category and each prompt is created by
    `(team_id, name)`, and a duplicate hitting the store's unique constraint
    is swallowed for that item alone. Calling this twice - or concurrently
    from two requests of the same user - therefore converges on one starter
    kit instead of raising or duplicating rows.

    Not best-effort on its own: a non-duplicate failure propagates, and each
    caller decides how to degrade (both currently log and swallow, because an
    empty prompt library is degraded but not unsafe).
    """

    async def _ensure_category(name: str) -> tuple[str, str | None]:
        try:
            record = await category_store.create(
                PromptCategoryRecord(
                    category_id=str(uuid4()), team_id=team_id, name=name
                )
            )
            return name, record.category_id
        except PromptCategoryAlreadyExistsError:
            return name, None

    # Each category is independent of its siblings - only the prompt phase
    # below depends on this one having finished (it needs every category_id
    # to link prompts to their category).
    pairs = await asyncio.gather(*(_ensure_category(n) for n in STARTER_CATEGORY_NAMES))
    category_id_by_name = {name: cid for name, cid in pairs if cid is not None}
    if len(category_id_by_name) < len(STARTER_CATEGORY_NAMES):
        # At least one name was already taken (a pre-existing category, or a
        # concurrent seeding that won the race): re-read the team's rows so
        # the prompts below still link to a real category id.
        for record in await category_store.list_by_team(team_id):
            category_id_by_name.setdefault(record.name, record.category_id)

    async def _ensure_prompt(spec: StarterPromptSpec) -> None:
        try:
            await prompt_store.create(
                PromptRecord(
                    prompt_id=str(uuid4()),
                    team_id=team_id,
                    name=spec.name,
                    description=spec.description,
                    category_id=category_id_by_name.get(spec.category_name),
                    text=spec.text,
                    created_by=None,
                )
            )
        except PromptAlreadyExistsError:
            pass

    # Independent of each other too - each prompt only needs its own
    # (already-resolved) category id, not any sibling prompt.
    await asyncio.gather(*(_ensure_prompt(s) for s in STARTER_PROMPTS))
