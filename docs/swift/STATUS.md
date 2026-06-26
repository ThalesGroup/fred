# Fred Platform — Current Status

**Purpose**: One-page queryable snapshot of team activity. Updated each session.
Answers "what's next?", "who owns X?", "what was done this week?", "what's blocked?"

**AI assistants**: for structured queries read [`docs/data/id-legend.yaml`](data/id-legend.yaml)
first — it is faster than scanning prose. For sprint-level structured data, read
[`docs/data/sprint.yaml`](data/sprint.yaml).

Ask Claude Code directly: _"What is Simon working on?"_ · _"What tests cover MCP config?"_
· _"What is the next backend task for Dimitri?"_ · _"What's blocking Marc?"_

Last updated: 2026-06-18

---

## Team

### Area leads

| Personne      | Domaine                 | Rôle                                                                                           |
| ------------- | ----------------------- | ---------------------------------------------------------------------------------------------- |
| **Simon**     | Core architecture & dev | **Area lead — core** — fred-runtime, fred-sdk, observabilité, validation E2E                   |
| **Sébastien** | Ops & déploiement       | **Area lead — ops** — CI, Docker, Helm, déploiement, environnements                            |
| **Marc**      | Agents & graph SDK      | **Area lead — agentic** — graph agent SDK, validation, multi-agent, évaluation, business logic |
| **Dimitri**   | Full stack transversal  | Lead architect — contrats backend, runtime design, frontend, transversal                       |

### Core area (Simon)

| Personne    | Domaine | Rôle                                               |
| ----------- | ------- | -------------------------------------------------- |
| **Florian** | Backend | Control-plane-backend, APIs, DB, session lifecycle |

### Ops area (Sébastien)

| Personne   | Domaine | Rôle                                     |
| ---------- | ------- | ---------------------------------------- |
| **Arthur** | Ops dev | DevOps, scripts, infrastructure, tooling |

### Agentic area (Marc)

| Personne    | Domaine       | Rôle                                          |
| ----------- | ------------- | --------------------------------------------- |
| **Timothé** | Data / Python | Knowledge-flow, PDF processing, agents Python |
| **Odélia**  | Évaluation    | Track deepeval (indépendant)                  |

### Design & UX

| Personne   | Domaine   | Rôle                                 |
| ---------- | --------- | ------------------------------------ |
| **Maxime** | UX design | Design system, composants, maquettes |

### Organisation

| Personne   | Rôle                          |
| ---------- | ----------------------------- |
| **Claire** | Organisation équipe, planning |
| **Arnaud** | Organisation équipe, planning |

---

## Semaine du 2026-05-11 — Disponibilités

| Personne    | Disponibilité             | Priorité                                                     |
| ----------- | ------------------------- | ------------------------------------------------------------ |
| **Dimitri** | Plein temps sur swift     | MEMORY-REMOTE-AGENT → MEMORY-LOCAL-AGENT → PROMPT-AGENT-FORM |
| **Marc**    | Plein temps sur swift     | MEMORY-CHECKPOINT-ISOLATION → EVAL-HARNESS                   |
| **Simon**   | Best effort (support kea) | MEMORY-HISTORY-CAP + préparation scripts VALIDATION-E2E      |
| **Florian** | Best effort (support kea) | DOC-CHATCONTEXT-ALIGNMENT + CHECKPOINT-EXPIRY-CONFIG         |
| **Dimitri** | Indisponible              | —                                                            |

---

## Tâches actives (semaine du 2026-05-11)

| ID                          | Nom                                                           | Owner   | Statut                                                                        | Ref                                                 |
| --------------------------- | ------------------------------------------------------------- | ------- | ----------------------------------------------------------------------------- | --------------------------------------------------- |
| MEMORY-CHECKPOINT-ISOLATION | Memory: checkpoint isolation                                  | Marc    | In progress                                                                   | [§F.1](backlog/MULTI-AGENT-MEMORY-BACKLOG.md)       |
| MEMORY-REMOTE-AGENT         | Memory: remote agent contract                                 | Dimitri | In progress                                                                   | [§F.2](backlog/MULTI-AGENT-MEMORY-BACKLOG.md)       |
| MEMORY-LOCAL-AGENT          | Memory: unified local agent execution                         | Dimitri | In progress                                                                   | [§F.3](backlog/MULTI-AGENT-MEMORY-BACKLOG.md)       |
| MEMORY-HISTORY-CAP          | Memory: TeamAgent history cap                                 | Simon   | Best effort                                                                   | [§F.4](backlog/MULTI-AGENT-MEMORY-BACKLOG.md)       |
| PROMPT-AGENT-FORM           | Prompts : formulaire agent                                    | Dimitri | Après MEMORY-REMOTE-AGENT + MEMORY-LOCAL-AGENT                                | [BACKLOG §3d.9](backlog/BACKLOG.md)                 |
| EVAL-HARNESS                | Évaluation : harness deepeval                                 | Marc    | Best effort mi-semaine                                                        | [AGENT-EVALUATION-RFC](rfc/AGENT-EVALUATION-RFC.md) |
| QUALITY-02                  | KF quality parity + migration vers apps/                      | Florian | **Priorité haute** — deadline 2026-06-06                                      | [BACKLOG §Phase QUALITY](backlog/BACKLOG.md)        |
| AGENT-FILESYSTEM            | Filesystem agent/user exchange — 4 UI roots, KF MCP FS, simple SDK ctx.fs, LinkPart replay | Dimitri | En cours — design as-built + RFC hardening séparé autour de Resources / Mon espace / Espace d'equipe / Agents | [FILESYSTEM](design/FILESYSTEM.md) |
| CTRLP-10                    | Isolation espace personnel par utilisateur (`personal-{uid}`) | Dimitri | En cours — durcissement core/runtime + §6.4.F (PATCH/DELETE ownership) livrés | [BACKLOG §6.4.F](backlog/BACKLOG.md)                |
| VALIDATION-E2E              | Validation E2E live stack                                     | Simon   | **Bloqué** — pod manquant                                                     | [BACKLOG §3b.7](backlog/BACKLOG.md)                 |
| CHAT-OPTIONS                | Chat UI : panneau options                                     | Dimitri | En cours                                                                      | [CHAT-UI-BACKLOG §3](backlog/CHAT-UI-BACKLOG.md)    |
| CHAT-11                     | Chat UI : dictée vocale dans le composer                      | Dimitri | En cours — MVP dictation Knowledge Flow + mic composer                        | [CHAT-UI-BACKLOG §12](backlog/CHAT-UI-BACKLOG.md)   |
| PROMPT-CONTEXT-PICKER       | Prompts : sélecteur contexte                                  | Dimitri | En cours (après CHAT-OPTIONS)                                                 | [BACKLOG §3d.9](backlog/BACKLOG.md)                 |

## File d'attente

| ID                      | Nom                                            | Owner           | Attend                                                                                |
| ----------------------- | ---------------------------------------------- | --------------- | ------------------------------------------------------------------------------------- |
| AGENT-MODEL-PROFILES    | Control Plane : profils modèles                | Dimitri         | Catalogue model-profiles                                                              |
| RUNTIME-DYNAMIC-ROUTING | Runtimes externes : routage frontend dynamique | Simon           | Revue RFC + priorisation impl                                                         |
| PROMPT-MARKETPLACE      | Prompts : marketplace                          | Dimitri         | PROMPT-AGENT-FORM                                                                     |
| KNOWLEDGE-WORKSPACE-REWORK | Ressources rework : browser fichiers/ressources paginé | Dimitri         | RFC proposé; première tranche documents possible, fichiers générés liés à FILES-01    |
| FRONTEND-CLEANUP        | Frontend : nettoyage agentic                   | Dimitri         | CHAT-OPTIONS + retour Dimitri                                                         |
| PROMPT-KPI              | Prompts : KPI tokens                           | Simon + Dimitri | EVAL-HARNESS + fred-core                                                              |
| DEVOPS-HELM-CHART       | Helm chart fred moderne                        | Simon           | À lancer — prérequis CI + Docker fermés le 2026-06-03                                 |
| OPS-05                  | Object storage naming cleanup                  | Simon           | À lancer — RFC/backlog prêts; [BACKLOG §OPS-05](backlog/BACKLOG.md), retour SeaweedFS |
| **DEVOPS-FREDLAB**      | **GCP fredlab + CI auto-deploy**               | **Sébastien**   | **CRITIQUE — cible semaine: Swift interne sur GKE Autopilot**                         |

---

## Fermé cette semaine (2026-05-01 → 2026-05-11)

| ID         | Nom                                                                       | Owner           | Fermé      | Tests                                                              |
| ---------- | ------------------------------------------------------------------------- | --------------- | ---------- | ------------------------------------------------------------------ |
| PROMPT-05  | Multi-prompt chat context (ordered pills + scope-grouped picker)           | Dimitri         | 2026-06-19 | control-plane 167 + frontend 243; tsc/prettier clean               |
| RUNTIME-02 | ChatContext typé (RuntimeContext, search_policy, context_prompt_text)     | Dimitri         | 2026-05-11 | 189 (fred-sdk), 302 (fred-runtime), 120 (control-plane), tsc clean |
| FRONT-06   | Wire ChatContext dans useChatSse (context_prompt_text, bound_library_ids) | Dimitri/Dimitri | 2026-05-11 | tsc clean, prettier clean                                          |
| PROMPT-03  | Extension backend prompts : versioning, analytics, context integration    | Dimitri         | 2026-05-10 | `test_main.py` (6 new tests, 120 passing)                          |
| R1b-A      | fred-runtime raw type-check cleanup + baseline emptied                    | Codex           | 2026-05-09 | `make code-quality`, `make test`, raw `basedpyright`               |
| CTRLP-03   | Pod catalog exposure + MCP tri-state selection                            | Dimitri         | 2026-05-06 | `test_mcp_config.py`, `test_agent_app.py`, `test_main.py`          |
| PROMPT-01  | Prompt safety : rendering fix + persistence validation                    | Dimitri         | 2026-05-07 | `test_prompt_utils.py`, `test_main.py`                             |
| CTRLP-02   | PATCH session endpoint (`updated_at`, `title`)                            | Florian         | 2026-05-06 | `test_main.py`                                                     |
| —          | fred-agents cleanup (remove simple_assistant, fix IDs)                    | Dimitri         | 2026-05-07 | `test_smoke.py`                                                    |
| —          | Version bumps : fred-core 2.0.3, fred-sdk 2.0.4, fred-runtime 2.0.5       | Dimitri         | 2026-05-07 | —                                                                  |
| —          | OPERATING_MODES.md — standalone vs full-stack guide                       | Dimitri         | 2026-05-07 | —                                                                  |

---

## Fermé récemment (30 derniers jours — référence)

| ID         | Nom                                                                                                                                                           | Owner         | Fermé      |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- | ---------- |
| OPS-03     | Docker moderne — packaging aligné sur `fred-agents` pour la pile swift                                                                                        | Simon         | 2026-06-03 |
| OPS-01     | Helm chart moderne — runtime topology migrée vers `fred-agents`                                                                                               | Simon         | 2026-06-04 |
| OPS-02     | CI moderne — build/push des 4 artefacts swift + validation chart alignée                                                                                      | Sébastien     | 2026-06-03 |
| CHAT-04    | Chat attachments — composer upload, session persistence, drawer preview, strong delete                                                                         | Simon         | 2026-06-11 |
| FRONT-07   | Rework UI architecture compliance — SearchField, FilterChips, TagInput molecules; PromptsPage + TuningFieldRenderer migrated; `--outline-variant` token added | Dimitri       | 2026-06-02 |
| CHAT-02    | Markdown rendering (react-markdown, CodeBlock, SourceBadge)                                                                                                   | Dimitri       | 2026-05-04 |
| QUALITY-03 | Knowledge-flow : nouveau processeur PDF rapide                                                                                                                | Timothé       | 2026-05-27 |
| MEMORY-01  | Multi-agent conversational memory — core (phases A–E)                                                                                                         | Dimitri       | 2026-05-05 |
| —          | Agent FieldSpec declarations (3 agents de production)                                                                                                         | Dimitri       | 2026-05-04 |
| —          | AgentFormModal refactor (template browser, tuning fields)                                                                                                     | Dimitri       | 2026-04-28 |
| OBSERV-01  | Prometheus cardinality fix + observabilité                                                                                                                    | Simon         | 2026-04-26 |
| RUNTIME-01 | Runtime CLI ergonomics + session purge                                                                                                                        | Simon/Dimitri | 2026-04-26 |
| CTRLP-05   | Control-plane developer CLI (`make cli`)                                                                                                                      | Dimitri       | 2026-04-25 |
| CHAT-01    | Chat UI architecture — new component tree ManagedChatPage                                                                                                     | Dimitri       | 2026-05-04 |
| CTRLP-01   | Session `updated_at` strategy + PATCH impl                                                                                                                    | Florian       | 2026-05-06 |
| QUALITY-01 | fred-runtime quality refactor (PROMPT-01–P5 only)                                                                                                             | Simon         | 2026-04-27 |

---

## Milestones

| Milestone                               | Cible          | Items bloquants                                                                                              | Statut          | Avancement |
| --------------------------------------- | -------------- | ------------------------------------------------------------------------------------------------------------ | --------------- | ---------- |
| **fredlab GCP live** ⚠️                 | **2026-06-30** | **DEVOPS-FREDLAB**                                                                                           | **En cours**    | **~70%**   |
| **Production go-live** ⚠️               | **2026-07-15** | **DEVOPS-FREDLAB**                                                                                           | **Non démarré** | **0%**     |
| Phase 3 complete - E2E + hardened memory | TBD            | VALIDATION-E2E + MEMORY-CHECKPOINT-ISOLATION + MEMORY-REMOTE-AGENT + MEMORY-LOCAL-AGENT + MEMORY-HISTORY-CAP | In progress     | ~60%       |
| Bibliothèque de prompts                 | TBD            | PROMPT-AGENT-FORM ✳ + PROMPT-CONTEXT-PICKER ✳                                                              | En cours        | ~40%       |
| Chat UI Phase 6 — CHAT-OPTIONS          | TBD            | CHAT-OPTIONS ✳                                                                                              | En cours        | ~80%       |
| Frontend nettoyage agentic              | TBD            | FRONTEND-CLEANUP                                                                                             | Non démarré     | 0%         |
| Évaluation agents v1                    | TBD            | EVAL-HARNESS ✳                                                                                              | Démarrage       | ~5%        |
| Profils modèles                         | TBD            | AGENT-MODEL-PROFILES                                                                                         | En attente      | 0%         |

> ✳ en cours cette semaine · ⚠️ deadline ferme

---

## Production Readiness Kickoff (semaine du 2026-06-01)

Objectif: consolider les gates de go-live sans créer un nouveau système de suivi.
Ce tableau ne crée pas de nouveaux tickets; il relie uniquement les items déjà
présents dans backlog/sprint/PMO.

| Gate                            | Owner     | Source of truth                                               | Target this week                                                                                                                            | État        |
| ------------------------------- | --------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| Runtime validation live-stack   | Simon     | VALIDATION-E2E (`docs/swift/backlog/BACKLOG.md §3b.7`)        | Exécuter 3 scénarios live et fermer le blocage pod/env                                                                                      | 🔴 Bloqué   |
| CI adaptation (modern topology) | Sébastien | OPS-02 (`docs/swift/backlog/BACKLOG.md §3b.12`)               | Pipeline moderne fermée: build/push `fred-agents`, `control-plane-backend`, `knowledge-flow-backend`, `frontend` + validation chart alignée | ✅ Clos     |
| Docker packaging alignment      | Simon     | OPS-03 (`docs/swift/backlog/BACKLOG.md §3b.13`)               | Packaging moderne clos pour la pile `fred-agents`                                                                                           | ✅ Clos     |
| Helm deployment migration       | Simon     | OPS-01 (`docs/swift/backlog/BACKLOG.md §3b.11`)               | Chart Helm moderne validé; déploiement interne GKE Autopilot désormais débloqué                                                             | ✅ Clos     |
| Runtime/SDK hardening baseline  | Simon     | QUALITY-01 + VALIDATION-E2E (`docs/swift/STATUS.md` + sprint) | Confirmer qu'aucun gap critique runtime n'est hors backlog                                                                                  | 🟠 En cours |
| Observability release signal    | Simon     | OBSERV-01 + Phase 3b.5 (`docs/swift/backlog/BACKLOG.md`)      | Vérifier logs/KPI/metrics exploitables en fredlab                                                                                           | 🟠 En cours |

Règle simple: si un gate reste rouge vendredi, la date de go-live ne bouge pas
dans ce fichier; seuls les blockers de la ligne sont mis à jour.

---

## Bloqueurs

| Item           | Bloqué sur                                          | Owner   |
| -------------- | --------------------------------------------------- | ------- |
| VALIDATION-E2E | Live pod disponible + `FRED_AGENT_INSTANCE_ID` set  | Simon   |
| CHAT-OPTIONS   | Soft gate VALIDATION-E2E (sign-off final seulement) | Dimitri |

---

## Feature → Tests (référence rapide)

| Domaine                                                          | Fichier(s) de test              | Package                 |
| ---------------------------------------------------------------- | ------------------------------- | ----------------------- |
| Managed agent CRUD, tuning validation, execution prep            | `test_main.py`                  | `control-plane-backend` |
| Control-plane developer CLI commands                             | `test_cli.py`                   | `control-plane-backend` |
| Session lifecycle, purge policies                                | `test_lifecycle_actions.py`     | `control-plane-backend` |
| ReBAC policy engine                                              | `test_policy_engine.py`         | `control-plane-backend` |
| Agent runtime (tuning, MCP selection, `agent_instructions`, KPI) | `test_agent_app.py`             | `fred-runtime`          |
| MCP catalog loading + tri-state selection (CTRLP-03)             | `test_mcp_config.py`            | `fred-runtime`          |
| Multi-agent memory — runtime wiring (MEMORY-01 phases C+D)       | `test_conversational_memory.py` | `fred-runtime`          |
| Prompt safety token registry + validation (PROMPT-01)            | `test_prompt_utils.py`          | `fred-sdk`              |
| Multi-agent memory — SDK primitives (MEMORY-01 phases A+B)       | `test_conversational_memory.py` | `fred-sdk`              |
| SSE execution contracts, `ExecutionGrant`, events                | `test_execution_contracts.py`   | `fred-sdk`              |
| Prometheus KPI cardinality + labels (OBSERV-01)                  | `test_prometheus_kpi_store.py`  | `fred-core`             |
| Structured KPI log output (OBSERV-01)                            | `test_log_kpi_store.py`         | `fred-core`             |
| CLI KPI ring buffer display (OBSERV-01/RUNTIME-01)               | `test_kpi_display.py`           | `fred-runtime`          |
| History store, HITL persistence, session purge (RUNTIME-01)      | `test_history.py`               | `fred-runtime`          |
| Pod client, CLI session commands                                 | `test_client.py`                | `fred-runtime`          |

---

## Comment utiliser ce fichier (pour Claire et Arnaud)

Ouvrez ce dépôt dans **VS Code** et installez l'extension **Claude Code** (voir
[claude.ai/code](https://claude.ai/code)). Posez vos questions directement dans le panneau chat :

- _"Que fait Simon cette semaine ?"_
- _"Qu'est-ce qui a été fermé depuis lundi ?"_
- _"Qui est propriétaire du chat UI ?"_
- _"Quels tests couvrent la configuration MCP ?"_
- _"Qu'est-ce qui bloque Dimitri ?"_
- _"Où est tracée la bibliothèque de prompts ?"_

Claude Code lit ce fichier ainsi que les backlogs et le code liés pour répondre. Pas besoin de Jira.

Pour aller plus loin :

- Specs fonctionnelles → [`backlog/BACKLOG.md`](backlog/BACKLOG.md)
- Détails du sprint → [`WORKPLAN.md`](WORKPLAN.md)
- Décisions d'architecture → [`design/`](design/)
- Propositions techniques → [`rfc/`](rfc/)
