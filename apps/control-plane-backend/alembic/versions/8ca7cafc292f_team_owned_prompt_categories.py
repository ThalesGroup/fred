"""team-owned prompt categories (PROMPT-09)

Removes the platform-wide default-prompt catalog and the fixed
`PromptCategory` enum in favor of real, per-team, editable content:

- creates `prompt_category` (team-scoped, name only)
- adds `prompt.category_id` (nullable, points at `prompt_category.category_id`
  within the same team — no DB-level FK, matching every other team-scoped
  table in this schema)
- backfills the same starter kit new teams get at creation (4 categories, 4
  prompts) into every EXISTING team that currently has zero prompt rows —
  teams that already authored their own custom prompts are left untouched
- migrates existing prompts' legacy free-text `category` (the old fixed
  10-value enum slug) into a real per-team category row with the equivalent
  French label, then drops the old column
- drops `default_prompt_usage` (usage counters for the removed synthetic
  `default:{category}` prompts have no meaning once every prompt is a real
  row with its own `session_count`)

Self-contained (no app imports) and best-effort per team/row, matching the
style of `a1b2c3d4e5f7_drop_mcp_prefix_from_tuning.py`.

Revision ID: 8ca7cafc292f
Revises: c1d2e3f4a5b6
Create Date: 2026-07-30 00:00:00.000000

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8ca7cafc292f"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "c1d2e3f4a5b6"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Starter kit content — mirrors control_plane_backend/product/prompt_starter_kit.py.
# Duplicated here (not imported) so this migration keeps working unchanged even
# if that module is edited or removed later.
# ---------------------------------------------------------------------------

_STARTER_CATEGORY_NAMES = [
    "Création agent",
    "Analyse et synthèse",
    "Stratégie et idéation",
    "Communication",
]

_STARTER_PROMPTS = [
    (
        "Analyse et synthèse",
        "Vulgarisation Technique",
        "Simplifie un sujet technique en une explication claire et imagée, calibrée pour l'auditoire visé.",
        "Explique le concept de [Concept complexe] à un public de "
        "[Type de public, ex: débutants/décideurs]. Utilise une métaphore "
        "concrète et limite l'explication à trois points clés.",
    ),
    (
        "Stratégie et idéation",
        "Brainstorming Inversé",
        "Anticipe les causes d'échec d'un projet pour en tirer des actions préventives concrètes.",
        "Nous voulons réussir le projet suivant : [Description du projet]. "
        "Liste 5 façons infaillibles de faire échouer ce projet. Ensuite, "
        "pour chaque point d'échec, propose une action préventive pour l'éviter.",
    ),
    (
        "Communication",
        "Approche Diplomate",
        "Formule un message délicat de façon posée et constructive, pour débloquer une situation sans envenimer la relation.",
        "Rédige un email professionnel et diplomate à l'attention de "
        "[Nom du destinataire] pour lui signaler que [Raison du problème, "
        "ex: son livrable est en retard]. L'objectif est de débloquer la "
        "situation sans créer de conflit.",
    ),
    (
        "Création agent",
        "Agent : synthèse de document",
        "Configure un agent de synthèse documentaire strict, sans hallucination, avec un format de sortie fixe.",
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
        "[Mentionne ici si un passage du texte est tronqué, ambigu ou manque de contexte pour être pleinement compris]",
    ),
]

# Legacy PromptCategory enum slug -> French label, used only to name the
# per-team category rows created for prompts that already had a legacy
# `category` string.
_LEGACY_CATEGORY_LABELS = {
    "doc-assist": "Aide documentaire",
    "summary": "Résumé",
    "extraction": "Extraction",
    "writing": "Rédaction",
    "analysis": "Analyse",
    "monitoring": "Suivi",
    "migration": "Migration",
    "conversational": "Conversationnel",
    "integration": "Intégration",
    "other": "Autre",
}


def upgrade() -> None:
    op.create_table(
        "prompt_category",
        sa.Column("category_id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("category_id"),
        sa.UniqueConstraint("team_id", "name", name="uq_prompt_category_team_name"),
    )
    op.create_index(
        op.f("ix_prompt_category_team_id"), "prompt_category", ["team_id"], unique=False
    )
    op.add_column(
        "prompt",
        sa.Column("category_id", sa.String(), nullable=True),
    )
    op.create_index(
        op.f("ix_prompt_category_id"), "prompt", ["category_id"], unique=False
    )

    conn = op.get_bind()

    # --- Pass 1: backfill the starter kit into every existing team that has
    # zero prompt rows today (teams that already authored prompts keep them
    # untouched — this only replaces what the removed platform defaults used
    # to provide for free). ---
    team_ids = [
        row[0]
        for row in conn.execute(sa.text("SELECT id FROM teammetadata")).fetchall()
    ]
    populated_team_ids = {
        row[0]
        for row in conn.execute(
            sa.text("SELECT DISTINCT team_id FROM prompt")
        ).fetchall()
    }
    for team_id in team_ids:
        if team_id in populated_team_ids:
            continue
        category_id_by_name: dict[str, str] = {}
        for name in _STARTER_CATEGORY_NAMES:
            category_id = str(uuid.uuid4())
            conn.execute(
                sa.text(
                    "INSERT INTO prompt_category (category_id, team_id, name) "
                    "VALUES (:category_id, :team_id, :name)"
                ),
                {"category_id": category_id, "team_id": team_id, "name": name},
            )
            category_id_by_name[name] = category_id
        for category_name, name, description, text in _STARTER_PROMPTS:
            conn.execute(
                sa.text(
                    "INSERT INTO prompt "
                    "(prompt_id, team_id, name, description, category_id, text) "
                    "VALUES (:prompt_id, :team_id, :name, :description, :category_id, :text)"
                ),
                {
                    "prompt_id": str(uuid.uuid4()),
                    "team_id": team_id,
                    "name": name,
                    "description": description,
                    "category_id": category_id_by_name.get(category_name),
                    "text": text,
                },
            )

    # --- Pass 2: migrate legacy `category` string values on existing prompts
    # into real per-team category rows. ---
    legacy_rows = conn.execute(
        sa.text(
            "SELECT DISTINCT team_id, category FROM prompt "
            "WHERE category IS NOT NULL AND category_id IS NULL"
        )
    ).fetchall()
    for team_id, legacy_category in legacy_rows:
        label = _LEGACY_CATEGORY_LABELS.get(legacy_category, legacy_category)
        existing = conn.execute(
            sa.text(
                "SELECT category_id FROM prompt_category "
                "WHERE team_id = :team_id AND name = :name"
            ),
            {"team_id": team_id, "name": label},
        ).fetchone()
        if existing:
            category_id = existing[0]
        else:
            category_id = str(uuid.uuid4())
            conn.execute(
                sa.text(
                    "INSERT INTO prompt_category (category_id, team_id, name) "
                    "VALUES (:category_id, :team_id, :name)"
                ),
                {"category_id": category_id, "team_id": team_id, "name": label},
            )
        conn.execute(
            sa.text(
                "UPDATE prompt SET category_id = :category_id "
                "WHERE team_id = :team_id AND category = :category"
            ),
            {
                "category_id": category_id,
                "team_id": team_id,
                "category": legacy_category,
            },
        )

    op.drop_column("prompt", "category")
    op.drop_table("default_prompt_usage")


def downgrade() -> None:
    """Best-effort reverse.

    Re-adds `prompt.category` (populated from each prompt's category name,
    truncated to 64 chars — the legacy enum values are not recoverable from
    free-form names) and `default_prompt_usage` (empty — its counters cannot
    be reconstructed), then drops `prompt_category` and `prompt.category_id`.
    """

    op.add_column(
        "prompt",
        sa.Column("category", sa.String(length=64), nullable=True),
    )
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE prompt SET category = ("
            "  SELECT substr(pc.name, 1, 64) FROM prompt_category pc"
            "  WHERE pc.category_id = prompt.category_id"
            ") WHERE prompt.category_id IS NOT NULL"
        )
    )
    op.drop_index(op.f("ix_prompt_category_id"), table_name="prompt")
    op.drop_column("prompt", "category_id")
    op.drop_index(op.f("ix_prompt_category_team_id"), table_name="prompt_category")
    op.drop_table("prompt_category")
    op.create_table(
        "default_prompt_usage",
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("session_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("team_id", "category"),
    )
