# Fred Platform — Current Status

**Purpose**: One-page queryable snapshot of team activity. Updated each session.
Answers "what's next?", "who owns X?", "what was done this week?", "what's blocked?"

**AI assistants**: for structured queries read [`docs/data/id-legend.yaml`](data/id-legend.yaml)
first — it is faster than scanning prose. For sprint-level structured data, read
[`docs/data/sprint.yaml`](data/sprint.yaml).

Ask Claude Code directly: _"What is Simon working on?"_ · _"What tests cover MCP config?"_
· _"What is the next backend task for Dimitri?"_ · _"What's blocking Félix?"_

Last updated: 2026-05-29

---

## Team

| Personne    | Rôle                                                                      |
| ----------- | ------------------------------------------------------------------------- |
| **Dimitri** | Lead architect — contrats backend, runtime design, transversal            |
| **Félix**   | Frontend — design system rework, migration chat UI                        |
| **Simon**   | Backend — fred-runtime, fred-sdk, observabilité, validation E2E           |
| **Florian** | Backend — control-plane-backend, APIs, DB, session lifecycle              |
| **Marc**    | Conception agents complexes — multi-agent, évaluation, frontend si besoin |
| **Odélia**  | Évaluation agents — track deepeval (indépendant)                          |
| **Claire**  | Organisation équipe, planning                                             |
| **Arnaud**  | Organisation équipe, planning                                             |

---

## Semaine du 2026-05-11 — Disponibilités

| Personne    | Disponibilité             | Priorité                             |
| ----------- | ------------------------- | ------------------------------------ |
| **Dimitri** | Plein temps sur swift     | MEM-REMOTE → MEM-LOCAL → PROMPT-FORM |
| **Marc**    | Plein temps sur swift     | MEM-CHKPT → EVAL-HARNESS             |
| **Simon**   | Best effort (support kea) | MEM-CAP + préparation scripts RT-E2E |
| **Florian** | Best effort (support kea) | CP-DOC-RT1 + CP-TTL                  |
| **Félix**   | Indisponible              | —                                    |

---

## Tâches actives (semaine du 2026-05-11)

| ID           | Nom                                  | Owner   | Statut                       | Ref                                                                |
| ------------ | ------------------------------------ | ------- | ---------------------------- | ------------------------------------------------------------------ |
| MEM-CHKPT    | Mémoire : isolation checkpoints      | Marc    | En cours                     | [§F.1](backlog/MULTI-AGENT-MEMORY-BACKLOG.md)                      |
| MEM-REMOTE   | Mémoire : contrat agent distant      | Dimitri | En cours                     | [§F.2](backlog/MULTI-AGENT-MEMORY-BACKLOG.md)                      |
| MEM-LOCAL    | Mémoire : agent local unifié         | Dimitri | En cours                     | [§F.3](backlog/MULTI-AGENT-MEMORY-BACKLOG.md)                      |
| MEM-CAP      | Mémoire : cap historique équipe      | Simon   | Best effort                  | [§F.4](backlog/MULTI-AGENT-MEMORY-BACKLOG.md)                      |
| PROMPT-FORM  | Prompts : formulaire agent           | Dimitri | Après MEM-REMOTE + MEM-LOCAL | [BACKLOG §3d.9](backlog/BACKLOG.md)                                |
| EVAL-HARNESS | Évaluation : harness deepeval        | Marc    | Best effort mi-semaine       | [AGENT-EVALUATION-RFC](rfc/AGENT-EVALUATION-RFC.md)                |
| CP-DOC-RT1   | Doc : alignement contrat ChatContext | Florian | Best effort                  | [CONTROL-PLANE-CONTRACT](design/CONTROL-PLANE-PRODUCT-CONTRACT.md) |
| CP-TTL       | Config : durée des checkpoints       | Florian | Best effort                  | [BACKLOG §6.4](backlog/BACKLOG.md)                                 |
| RT-E2E       | Validation E2E live stack            | Simon   | **Bloqué** — pod manquant    | [BACKLOG §3b.7](backlog/BACKLOG.md)                                |
| CU-OPTIONS   | Chat UI : panneau options            | Félix   | **Suspendu** — indisponible  | [CHAT-UI-BACKLOG §3](backlog/CHAT-UI-BACKLOG.md)                   |
| PROMPT-CTX   | Prompts : sélecteur contexte         | Félix   | **Suspendu** — indisponible  | [BACKLOG §3d.9](backlog/BACKLOG.md)                                |

## File d'attente

| ID         | Nom                             | Owner           | Attend                    |
| ---------- | ------------------------------- | --------------- | ------------------------- |
| CP-MODELS  | Control Plane : profils modèles | Dimitri         | Catalogue model-profiles  |
| CP-EXT-ROUTE | Runtimes externes : routage frontend dynamique | Simon | Revue RFC + priorisation impl |
| PROMPT-MKT | Prompts : marketplace           | Dimitri         | PROMPT-FORM               |
| FE-CLEANUP | Frontend : nettoyage agentic    | Félix           | CU-OPTIONS + retour Félix |
| PROMPT-KPI | Prompts : KPI tokens            | Simon + Dimitri | EVAL-HARNESS + fred-core  |
| OPS-CI     | CI : architecture moderne       | Sebastien       | cadrage pipeline          |
| OPS-DOCKER | Packaging : Dockerfiles runtime | Sebastien       | cadrage images            |
| OPS-CHART  | Helm : chart fred moderne       | Sebastien       | OPS-CI + OPS-DOCKER       |

---

## Fermé cette semaine (2026-05-01 → 2026-05-11)

| ID         | Nom                                                                       | Owner         | Fermé      | Tests                                                              |
| ---------- | ------------------------------------------------------------------------- | ------------- | ---------- | ------------------------------------------------------------------ |
| RUNTIME-02 | ChatContext typé (RuntimeContext, search_policy, context_prompt_text)     | Dimitri       | 2026-05-11 | 189 (fred-sdk), 302 (fred-runtime), 120 (control-plane), tsc clean |
| FRONT-06   | Wire ChatContext dans useChatSse (context_prompt_text, bound_library_ids) | Félix/Dimitri | 2026-05-11 | tsc clean, prettier clean                                          |
| PROMPT-03  | Extension backend prompts : versioning, analytics, context integration    | Dimitri       | 2026-05-10 | `test_main.py` (6 new tests, 120 passing)                          |
| R1b-A      | fred-runtime raw type-check cleanup + baseline emptied                    | Codex         | 2026-05-09 | `make code-quality`, `make test`, raw `basedpyright`               |
| CTRLP-03   | Pod catalog exposure + MCP tri-state selection                            | Dimitri       | 2026-05-06 | `test_mcp_config.py`, `test_agent_app.py`, `test_main.py`          |
| PROMPT-01  | Prompt safety : rendering fix + persistence validation                    | Dimitri       | 2026-05-07 | `test_prompt_utils.py`, `test_main.py`                             |
| CTRLP-02   | PATCH session endpoint (`updated_at`, `title`)                            | Florian       | 2026-05-06 | `test_main.py`                                                     |
| —          | fred-agents cleanup (remove simple_assistant, fix IDs)                    | Dimitri       | 2026-05-07 | `test_smoke.py`                                                    |
| —          | Version bumps : fred-core 2.0.3, fred-sdk 2.0.4, fred-runtime 2.0.5       | Dimitri       | 2026-05-07 | —                                                                  |
| —          | OPERATING_MODES.md — standalone vs full-stack guide                       | Dimitri       | 2026-05-07 | —                                                                  |

---

## Fermé récemment (30 derniers jours — référence)

| ID         | Nom                                                         | Owner         | Fermé      |
| ---------- | ----------------------------------------------------------- | ------------- | ---------- |
| CHAT-02    | Markdown rendering (react-markdown, CodeBlock, SourceBadge) | Dimitri       | 2026-05-04 |
| QUALITY-03 | Knowledge-flow : nouveau processeur PDF rapide              | Timothé       | 2026-05-27 |
| MEMORY-01  | Mémoire multi-agent conversationnelle — core (phases A–E)   | Dimitri       | 2026-05-05 |
| —          | Agent FieldSpec declarations (3 agents de production)       | Dimitri       | 2026-05-04 |
| —          | AgentFormModal refactor (template browser, tuning fields)   | Dimitri       | 2026-04-28 |
| OBSERV-01  | Prometheus cardinality fix + observabilité                  | Simon         | 2026-04-26 |
| RUNTIME-01 | Runtime CLI ergonomics + session purge                      | Simon/Dimitri | 2026-04-26 |
| CTRLP-05   | Control-plane developer CLI (`make cli`)                    | Dimitri       | 2026-04-25 |
| CHAT-01    | Chat UI architecture — new component tree ManagedChatPage   | Félix         | 2026-05-04 |
| CTRLP-01   | Session `updated_at` strategy + PATCH impl                  | Florian       | 2026-05-06 |
| QUALITY-01 | fred-runtime quality refactor (PROMPT-01–P5 only)           | Simon         | 2026-04-27 |

---

## Milestones

| Milestone                                          | Items bloquants                     | Statut      | Avancement |
| -------------------------------------------------- | ----------------------------------- | ----------- | ---------- |
| Phase 3 complète — E2E + mémoire durcie            | RT-E2E + MEM-CHKPT/REMOTE/LOCAL/CAP | En cours    | ~60%       |
| Bibliothèque de prompts — PROMPT-FORM + PROMPT-CTX | PROMPT-FORM ✳ + PROMPT-CTX ⏸        | En cours    | ~40%       |
| Chat UI Phase 6 — CU-OPTIONS livré                 | CU-OPTIONS ⏸                        | En cours    | ~80%       |
| Frontend nettoyage agentic — FE-CLEANUP            | FE-CLEANUP                          | Non démarré | 0%         |
| Évaluation agents v1 — EVAL-HARNESS                | EVAL-HARNESS ✳                      | Démarrage   | ~5%        |
| Profils modèles — CP-MODELS                        | CP-MODELS                           | En attente  | 0%         |

> ✳ en cours cette semaine · ⏸ suspendu (Félix indisponible)

---

## Bloqueurs

| Item       | Bloqué sur                                         | Owner |
| ---------- | -------------------------------------------------- | ----- |
| RT-E2E     | Live pod disponible + `FRED_AGENT_INSTANCE_ID` set | Simon |
| CU-OPTIONS | Félix indisponible + gate RT-E2E                   | Félix |
| PROMPT-CTX | Félix indisponible                                 | Félix |
| OPS-CHART  | `OPS-CI` + `OPS-DOCKER`                            | Sebastien |

---

## Feature → Tests (référence rapide)

| Domaine | Fichier(s) de test | Package |
|---|---|---|
| Managed agent CRUD, tuning validation, execution prep | `test_main.py` | `control-plane-backend` |
| Control-plane developer CLI commands | `test_cli.py` | `control-plane-backend` |
| Session lifecycle, purge policies | `test_lifecycle_actions.py` | `control-plane-backend` |
| ReBAC policy engine | `test_policy_engine.py` | `control-plane-backend` |
| Agent runtime (tuning, MCP selection, `agent_instructions`, KPI) | `test_agent_app.py` | `fred-runtime` |
| MCP catalog loading + tri-state selection (CTRLP-03) | `test_mcp_config.py` | `fred-runtime` |
| Mémoire multi-agent — runtime wiring (MEMORY-01 phases C+D) | `test_conversational_memory.py` | `fred-runtime` |
| Prompt safety token registry + validation (PROMPT-01) | `test_prompt_utils.py` | `fred-sdk` |
| Mémoire multi-agent — SDK primitives (MEMORY-01 phases A+B) | `test_conversational_memory.py` | `fred-sdk` |
| SSE execution contracts, `ExecutionGrant`, events | `test_execution_contracts.py` | `fred-sdk` |
| Prometheus KPI cardinality + labels (OBSERV-01) | `test_prometheus_kpi_store.py` | `fred-core` |
| Structured KPI log output (OBSERV-01) | `test_log_kpi_store.py` | `fred-core` |
| CLI KPI ring buffer display (OBSERV-01/RUNTIME-01) | `test_kpi_display.py` | `fred-runtime` |
| History store, HITL persistence, session purge (RUNTIME-01) | `test_history.py` | `fred-runtime` |
| Pod client, CLI session commands | `test_client.py` | `fred-runtime` |

---

## Comment utiliser ce fichier (pour Claire et Arnaud)

Ouvrez ce dépôt dans **VS Code** et installez l'extension **Claude Code** (voir
[claude.ai/code](https://claude.ai/code)). Posez vos questions directement dans le panneau chat :

- _"Que fait Simon cette semaine ?"_
- _"Qu'est-ce qui a été fermé depuis lundi ?"_
- _"Qui est propriétaire du chat UI ?"_
- _"Quels tests couvrent la configuration MCP ?"_
- _"Qu'est-ce qui bloque Félix ?"_
- _"Où est tracée la bibliothèque de prompts ?"_

Claude Code lit ce fichier ainsi que les backlogs et le code liés pour répondre. Pas besoin de Jira.

Pour aller plus loin :

- Specs fonctionnelles → [`backlog/BACKLOG.md`](backlog/BACKLOG.md)
- Détails du sprint → [`WORKPLAN.md`](WORKPLAN.md)
- Décisions d'architecture → [`design/`](design/)
- Propositions techniques → [`rfc/`](rfc/)
