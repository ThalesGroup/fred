# RFC — Team-Owned Prompt Categories & Starter Kit

**Status:** Implemented (2026-07-30)
**Author:** Maxime Daragon (drafted with Claude Code)
**Date:** 2026-07-30
**Area:** `control-plane-backend`, `frontend`
**Current design:** [`PROMPTS.md`](../design/PROMPTS.md)
**Supersedes:** the "No change to the shipped default prompt catalog" non-goal in
[`PROMPT-SYSTEM-HARDENING-RFC.md`](./PROMPT-SYSTEM-HARDENING-RFC.md) §3
**Tracks:** `PROMPT-09`

## 1. Problem

The prompt library currently offers **platform-level default prompts**: 7
hardcoded `DefaultPromptSpec` entries
(`control_plane_backend/product/default_prompts.py`), injected at query time
into every team's prompt list with a synthetic id (`default:{category}`),
never persisted, and read-only in the UI. They are tied to a **fixed, global**
10-value `PromptCategory` enum shared by every team.

This contradicts the invariant already documented in
[`CONTROL-PLANE-PRODUCT-CONTRACT.md`](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md)
§3.6 — "prompt ownership is team-scoped" — and gives teams no way to adapt,
delete, or reorganize the prompts and categories they're shown: the catalog is
identical for every team, forever, and cannot be edited even by a team editor.

## 2. Proposed change

### 2.1 Remove the platform default-prompt mechanism

- Delete `default_prompts.py` (`DEFAULT_PROMPTS`, `DefaultPromptSpec`).
- Delete `_system_default_to_summary` and its use in `list_prompts` /
  `list_context_prompts` (`product/service.py`).
- Drop `is_default` from `PromptSummary` / `ContextPromptSummary`
  (`product/schemas.py`) — every prompt returned by the API is now a real,
  editable, deletable team row.
- Drop the `default_prompt_usage` table, `DefaultPromptUsageRow` model
  (`models/prompt_models.py`), and `PromptStore.increment_default_usage` /
  `get_default_usage` (`prompts/store.py`) — usage is tracked the same way for
  every prompt now (`PromptRow.session_count`), so the separate counter table
  has no remaining purpose.
- Frontend: remove the `viewingDefault` read-only modal branch and
  `[data-default]` dimmed styling in `PromptsPage.tsx` / `PromptCard.tsx`.
  Every prompt opens the normal edit form. `PromptCard`'s `canManage` stops
  being derived from `!prompt.is_default` (which never reflected real rights)
  and is computed from `useTeamCapabilities(team).canUpdateResources`
  instead — this also fixes the pre-existing display bug where the edit
  pencil was shown regardless of the viewer's actual permissions.

### 2.2 New team-scoped `prompt_category` table

```
category_id : str, primary key
team_id     : str, indexed
name        : str(120)
created_at, updated_at
UniqueConstraint(team_id, name)
```

No icon/color column — pill styling keeps using the existing hash-based
fallback palette already used today for prompts with no recognized category
(`PromptCard.colorIndex()`), so the manage-categories form stays a single
name field. This can be revisited later if teams want custom visuals.

`prompt.category` (currently a free `String(64)`, validated only by the
`PromptCategory` Pydantic enum at the API boundary) becomes
`prompt.category_id: str | None`, referencing a `prompt_category` row scoped
to the same team. The `PromptCategory` enum
(`product/prompt_category.py`) is removed — categories are no longer a fixed,
globally-shared taxonomy. `category_id` stays **optional**: a prompt with no
category is valid and rendered with the existing fallback styling, rather than
forcing every team to keep a synthetic "Other" bucket.

### 2.3 New endpoints

Mirrors the existing prompt CRUD shape (`product/api.py` /
`product/service.py`, backed by a new `prompts/category_store.py`):

| Route | Permission |
|---|---|
| `GET /teams/{team_id}/prompt-categories` | `CAN_USE_TEAM_AGENTS` (same read gate as `GET .../prompts`) |
| `POST /teams/{team_id}/prompt-categories` | `CAN_UPDATE_RESOURCES` (`team_editor`) |
| `PUT /teams/{team_id}/prompt-categories/{category_id}` | `CAN_UPDATE_RESOURCES` |
| `DELETE /teams/{team_id}/prompt-categories/{category_id}` | `CAN_UPDATE_RESOURCES` |

`DELETE` returns **409** if any prompt in the team still references that
`category_id` — matches the user-facing requirement literally ("impossible de
supprimer une catégorie s'il y a au moins un prompt associé"): a hard block,
no auto-reassignment of the orphaned prompts.

### 2.4 Starter kit at team creation

`create_team` (`teams/service.py:405-511`) currently seeds nothing beyond
`team_metadata` and ReBAC relations. After those succeed, it now also creates,
for the new `team_id`:

**Categories:** Création agent · Analyse et synthèse · Stratégie et idéation ·
Communication.

**Prompts** (one per category, full text in Appendix A):

| Category | Title |
|---|---|
| Analyse et synthèse | Vulgarisation Technique |
| Stratégie et idéation | Brainstorming Inversé |
| Communication | Approche Diplomate |
| Création agent | Agent : synthèse de document |

Seeding is **best-effort**: unlike the ReBAC relation writes (which roll back
team creation on failure because a team without correct relations is an
invalid/unsafe state), a seeding failure logs a warning and does not fail
team creation — a team with an empty prompt library is a degraded-but-valid
state, not a security problem. From that point on the starter kit is normal
team content: any `team_editor` can rename, edit, or delete every part of it,
including the 4 seed categories themselves.

The personal prompt space (reserved `personal` team) is **not** seeded — it
stays empty until the user creates their own prompts, per the current
request's scope (team creation only).

### 2.5 Data migration for existing teams

One Alembic migration, two passes:

1. **Backfill empty teams.** For every existing team with zero rows in
   `prompt`, insert the same starter kit as new teams get (2.4). Teams that
   already have at least one custom prompt are left untouched.
2. **Migrate legacy category strings.** For every existing `prompt` row with a
   non-null legacy `category` value (one of the 10 old enum slugs), get-or-create
   a `prompt_category` row in that prompt's team named after the legacy
   label (`doc-assist` → "Aide documentaire", `summary` → "Résumé", etc. — the
   current FR labels already shown in `promptCategories.ts`), and repoint
   `prompt.category_id` to it. This mixes pre-existing custom prompts'
   categories in with the new starter-kit categories per team, with no loss of
   categorization.
3. Drop `default_prompt_usage` and the old `category` string column once (2)
   has repointed every row to `category_id`.

### 2.6 Frontend rework

- `promptCategories.ts`'s static `PROMPT_CATEGORIES` / `PROMPT_CATEGORY_MAP`
  list is removed; categories are fetched per-team from the new endpoint
  (generated RTK Query hooks, regenerated via
  `cd apps/frontend && make update-control-plane-api` per the mandatory
  backend↔frontend contract rule). Only the hash-based fallback palette
  helper survives, now used for every category (all of them are "custom").
- `CategoryPicker` (prompt create/edit form) and the `FilterChips` row on
  `PromptsPage` read from the team's live category list.
- New "Gérer les catégories" icon button at the end of the category-chips row,
  opening a new `ManageCategoriesDialog` (list + Créer / Éditer / Supprimer
  per row). A delete blocked by the backend's 409 surfaces as a toast
  ("Cette catégorie est utilisée par N prompt(s)"), same pattern as the
  existing prompt-delete confirmation flow.
- `PromptCard` / `PromptsPage` drop every `is_default` branch (2.1).

### 2.7 Docs to update in the same change

| File | Change |
|---|---|
| `CONTROL-PLANE-PRODUCT-CONTRACT.md` §3.6 | Rewrite prompt-category invariants; new dated Contract Note for `PROMPT-09` |
| `docs/swift/design/PROMPTS.md` §3 | `category_id` replaces the `PromptCategory` enum field; remove `DefaultPromptSpec`/`default:` id references; document category CRUD + starter-kit seeding |
| `PROMPT-SYSTEM-HARDENING-RFC.md` §3 | Strike the now-false "No change to the shipped default prompt catalog" non-goal, point to this RFC |
| `docs/swift/ux/COMPONENT-UX.md` | New entry for `ManageCategoriesDialog` |
| `docs/swift/platform/authz-endpoint-matrix.yaml` | Add the 4 new `prompt-categories` routes (`pending_review`, matching the existing unreviewed prompt routes) |

## 3. Impact on existing contracts (breaking)

- `PromptSummary.category` / `ContextPromptSummary.category` /
  `CreatePromptRequest.category` / `UpdatePromptRequest.category`: type
  changes from the fixed `PromptCategory` enum to `category_id: str | None`.
  Any caller relying on the 10 fixed enum values breaks. Acceptable pre-GA
  (`swift-golive` milestone), but is a real OpenAPI contract break, not an
  additive change.
- `is_default` disappears from `PromptSummary` / `ContextPromptSummary`.
- `default_prompt_usage` table is dropped.
- `GET .../prompts/context` (chat-context picker) naturally simplifies —
  contract §13/§20's "team space returns team prompts + platform defaults"
  becomes "team space returns team prompts", no separate code path needed.

## 4. Alternatives considered

- **Global enum + per-team custom additions layered on top** — rejected: two
  taxonomies for the same concept, and contradicts "chaque équipe... fait
  évoluer ce kit de départ comme elle le souhaite" (implies full ownership,
  not additive customization on a fixed base).
- **Soft delete / auto-reassign prompts on category delete** — rejected: the
  request explicitly asks for a hard block when prompts still reference the
  category.

## 5. Non-goals

- No icon/color customization for categories (name only, for now).
- No seeding of the personal prompt space.
- No change to the global prompt marketplace (already a separate, deferred
  surface per contract §3.6/§798).
- Does not address the other `PROMPT-SYSTEM-HARDENING-RFC` gaps (agent-form
  import/save UX, `promote_prompt` metadata, KPI aggregation) — separate,
  unaffected track.

## Appendix A — Starter kit prompt content

**Analyse et synthèse — Vulgarisation Technique**
> Description: Simplifie un sujet technique en une explication claire et imagée, calibrée pour l'auditoire visé.
>
> Explique le concept de [Concept complexe] à un public de [Type de public, ex: débutants/décideurs]. Utilise une métaphore concrète et limite l'explication à trois points clés.

**Stratégie et idéation — Brainstorming Inversé**
> Description: Anticipe les causes d'échec d'un projet pour en tirer des actions préventives concrètes.
>
> Nous voulons réussir le projet suivant : [Description du projet]. Liste 5 façons infaillibles de faire échouer ce projet. Ensuite, pour chaque point d'échec, propose une action préventive pour l'éviter.

**Communication — Approche Diplomate**
> Description: Formule un message délicat de façon posée et constructive, pour débloquer une situation sans envenimer la relation.
>
> Rédige un email professionnel et diplomate à l'attention de [Nom du destinataire] pour lui signaler que [Raison du problème, ex: son livrable est en retard]. L'objectif est de débloquer la situation sans créer de conflit.

**Création agent — Agent : synthèse de document**
> Description: Configure un agent de synthèse documentaire strict, sans hallucination, avec un format de sortie fixe.
>
> ```
> # MISSION
> Tu es "Synthex", un agent IA expert en analyse documentaire et en extraction d'informations complexes.
> Ton objectif unique est de traiter les documents fournis par l'utilisateur pour en restituer des synthèses fidèles, structurées et directement actionnables.
>
> # POSTURE ET TON
> - Professionnel, neutre et purement factuel.
> - Tu ne fais pas de conversation superflue. Tu vas directement à l'essentiel.
> - Tu n'exprimes aucune opinion personnelle sur le contenu analysé.
>
> # RÈGLES COGNITIVES ET GARDE-FOUS (STRICT)
> 1. FRACTURE COGNITIVE : Tu dois considérer tes connaissances pré-entraînées et le document de l'utilisateur comme deux mondes strictement isolés.
> 2. VÉRITÉ ABSOLUE : La seule source de vérité acceptable est le contenu explicite du document fourni (ou du contexte injecté).
> 3. ANTI-HALLUCINATION : Si une information n'est pas dans le texte, tu ne l'inventes pas. Si l'utilisateur pose une question dont la réponse ne figure pas dans le document, tu dois répondre EXACTEMENT : "L'information demandée ne figure pas dans le document fourni."
> 4. AUCUNE DÉDUCTION HASARDEUSE : Ne fais pas de liens logiques qui ne sont pas explicitement justifiés par l'auteur du document.
>
> # PROTOCOLE DE TRAITEMENT
> Lorsque tu reçois un document, applique silencieusement la méthodologie suivante avant de générer ta réponse :
> - Étape 1 (Macro) : Identifie la thèse principale ou l'intention de l'auteur.
> - Étape 2 (Méso) : Repère les arguments clés, les données chiffrées pertinentes et les décisions/actions.
> - Étape 3 (Micro) : Exclus le "bruit" (anecdotes secondaires, répétitions).
>
> # STRUCTURE DE SORTIE PAR DÉFAUT
> Sauf instruction contraire de l'utilisateur, toute synthèse globale doit obligatoirement respecter ce format Markdown :
>
> ## 🎯 Executive Summary
> [Un paragraphe de 3 à 5 phrases résumant l'essence du document]
>
> ## 🔑 Points Clés
> - [Point 1 : Idée + donnée ou justification chiffrée si présente]
> - [Point 2 : ...]
> - [Point 3 : ...]
>
> ## 🚀 Actions & Décisions
> - [Action 1 : Quoi + Qui + Quand, si applicable. Sinon, indiquer "Aucune action explicite identifiée"]
>
> ## ⚠️ Zones d'Ombre (Optionnel)
> [Mentionne ici si un passage du texte est tronqué, ambigu ou manque de contexte pour être pleinement compris]
> ```
