# PMO Board

Compact PMO-facing view of tracked work. Source of truth remains:

- `docs/swift/backlog/`
- `docs/swift/rfc/`
- `docs/swift/STATUS.md`
- `docs/swift/data/id-legend.yaml`
- `docs/swift/data/sprint.yaml`
- `docs/swift/tracks/`

Do not add new scope or statuses here that are absent from the source docs.

**Maintenance rules**

- Update this file in the same change whenever a tracked item's PMO-visible
  fields change in any source doc.
- PMO-visible fields are: owner, status, blocker, backlog ref, RFC/decision ref,
  and execution ref.
- Common trigger files: `docs/swift/backlog/`, `docs/swift/rfc/`,
  `docs/swift/STATUS.md`, `docs/swift/data/id-legend.yaml`,
  `docs/swift/data/sprint.yaml`, `docs/swift/tracks/`.
- Keep one row per active, blocked, next-up, or RFC-first tracked item.
- `Execution` column priority: GitHub issue -> PR -> working branch -> `TBD`.
- When an execution ref is known, mirror it under the backlog item as `Execution: ...`.

Last updated: 2026-06-20

## Active And Next Up

| Ticket | Sprint / file de travail | Responsable actuel | Statut PMO | Backlog | RFC / decision | Execution |
| ------ | ------------------------ | ------------------ | ---------- | ------- | -------------- | --------- |
| `QUALITY-02` | `QUALITY-02` | Florian | **En cours — deadline 2026-06-06** | [BACKLOG §Phase QUALITY](backlog/BACKLOG.md) | — | `TBD` |
| `FILES-01` | `AGENT-FILESYSTEM` | Dimitri | En cours — MCP filesystem-first target refreshed 2026-06-18 | [CHAT-UI-BACKLOG §4.5](backlog/CHAT-UI-BACKLOG.md) | [AGENT-FILESYSTEM-RFC](rfc/AGENT-FILESYSTEM-RFC.md) | `TBD` |
| `FILES-02` | `MINDMAP-AGENT` | Marc | A lancer — reservation de code | `TBD` | [AGENT-FILESYSTEM-RFC](rfc/AGENT-FILESYSTEM-RFC.md) | `TBD` |
| `FILES-03` | `COMPARISON-AGENT` | Dimitri | Livre — agent `fred.dt.comparison.graph`, code-quality + tests verts | [BACKLOG §Phase AGENTS](backlog/BACKLOG.md) | [SIMILARITY-COMPARISON-AGENT-RFC](rfc/SIMILARITY-COMPARISON-AGENT-RFC.md) | branch `1772-…-kf-similarity-search` |
| `FILES-04` | `UNIFIED-FILESYSTEM` | Dimitri | RFC-only — brouillon 2026-06-20, en attente de confirmation (layout unifié `/etc` + `/teams/{team}/`, breaking/no-compat) | [CHAT-UI-BACKLOG §4.6](backlog/CHAT-UI-BACKLOG.md) | [AGENT-FILESYSTEM-UNIFIED-LAYOUT-RFC](rfc/AGENT-FILESYSTEM-UNIFIED-LAYOUT-RFC.md) | `TBD` |
| `CHAT-04` | `CHAT-ATTACHMENTS-OPTION-A` | Simon | A lancer — branch dediee requise | [CHAT-UI-BACKLOG §4](backlog/CHAT-UI-BACKLOG.md) | Option A: composer upload UX, base64 image context, drag-and-drop ingestion; MCP filesystem hardening tracked separately in FILES-01 | GitHub issue #1706 |
| `VALID-01` | `VALIDATION-E2E` | Simon | Bloque | [BACKLOG §3b.7](backlog/BACKLOG.md) | — | `TBD` |
| `CHAT-03` | `CHAT-OPTIONS` | Marc | En cours | [CHAT-UI-BACKLOG §3](backlog/CHAT-UI-BACKLOG.md) | — | GitHub issue `#1730` |
| `CHAT-11` | `CHAT-VOICE-DICTATION` | Dimitri | En cours | [CHAT-UI-BACKLOG §12](backlog/CHAT-UI-BACKLOG.md) | [CHAT-VOICE-DICTATION-RFC](rfc/CHAT-VOICE-DICTATION-RFC.md) | Waived GitHub issue for local Codex session |
| `MEMORY-02` | `MEMORY-CHECKPOINT-ISOLATION` | Marc | En cours | [MEMORY BACKLOG §F.1](backlog/MULTI-AGENT-MEMORY-BACKLOG.md) | [MULTI-AGENT-MEMORY-RFC](rfc/MULTI-AGENT-MEMORY-RFC.md) | `TBD` |
| `MEMORY-03` | `MEMORY-REMOTE-AGENT` | Dimitri | En cours | [MEMORY BACKLOG §F.2](backlog/MULTI-AGENT-MEMORY-BACKLOG.md) | [MULTI-AGENT-MEMORY-RFC](rfc/MULTI-AGENT-MEMORY-RFC.md) | `TBD` |
| `MEMORY-04` | `MEMORY-LOCAL-AGENT` | Dimitri | En cours | [MEMORY BACKLOG §F.3](backlog/MULTI-AGENT-MEMORY-BACKLOG.md) | [MULTI-AGENT-MEMORY-RFC](rfc/MULTI-AGENT-MEMORY-RFC.md) | `TBD` |
| `MEMORY-05` | `MEMORY-HISTORY-CAP` | Simon | Best effort | [MEMORY BACKLOG §F.4](backlog/MULTI-AGENT-MEMORY-BACKLOG.md) | [MULTI-AGENT-MEMORY-RFC](rfc/MULTI-AGENT-MEMORY-RFC.md) | `TBD` |
| `PROMPT-04` | `PROMPT-AGENT-FORM` | Dimitri | Planifie apres `MEMORY-REMOTE-AGENT` + `MEMORY-LOCAL-AGENT` | [BACKLOG §3d.9](backlog/BACKLOG.md) | [PROMPT-LIBRARY-RFC](rfc/PROMPT-LIBRARY-RFC.md) | `TBD` |
| `EVAL-01` | `EVAL-HARNESS` | Marc | Best effort | [AGENT-EVALUATION-BACKLOG](backlog/AGENT-EVALUATION-BACKLOG.md) | [AGENT-EVALUATION-RFC](rfc/AGENT-EVALUATION-RFC.md) | `TBD` |
| `TEAM-01` | `TEAM-CONFIG-RFC` | Dimitri | En cours (RFC-only) | [BACKLOG §3d.11](backlog/BACKLOG.md) | [TEAM RFC set](rfc/FRED-TEAM-CONFIG-RFC.md) | `TBD` |
| `CTRLP-10` | `CTRLP-10` | Dimitri | En cours — isolation personelle + durcissement runtime + 6.4.F livrés | [BACKLOG §6.4.F](backlog/BACKLOG.md) | [PERSONAL-TEAM-ISOLATION-RFC](rfc/PERSONAL-TEAM-ISOLATION-RFC.md) | Branche `1666-ctrlp-10-per-user-personal-space-replace-shared-team_id-constant` |
| `CTRLP-09` | `RUNTIME-DYNAMIC-ROUTING` | Simon | A lancer — RFC ecrit | [BACKLOG §3d.12](backlog/BACKLOG.md) | [DISCOVERED-RUNTIME-ROUTING-RFC](rfc/DISCOVERED-RUNTIME-ROUTING-RFC.md) | `TBD` |
| `PROMPT-05` | `PROMPT-CONTEXT-PICKER` | Dimitri | Clos 2026-06-19 — multi-prompt (0..N ordonnés) câblé : table `session_context_prompts`, `context_prompt_ids`, concaténation control-plane, pills + picker scope-groupé | [BACKLOG §3d.9](backlog/BACKLOG.md) | [PROMPT-LIBRARY-RFC](rfc/PROMPT-LIBRARY-RFC.md) | Branche `1779-fully-wire-prompts-in-the-chat-ui-page` |
| `CTRLP-04` | `AGENT-MODEL-PROFILES` | Dimitri | En attente | [BACKLOG §3d](backlog/BACKLOG.md) | — | `TBD` |
| `RUNTIME-05` | `REACT-THOUGHT-SURFACE` | Dimitri | En cours — Layer 1 + 2b + 2c livrés (Mistral reasoning → THOUGHT_*, fix fuite JSON + fix replay HTTP 422 multi-tours) ; Layer 2 / démo Rico différés | [FRED-RUNTIME-QUALITY §RUNTIME-05](backlog/FRED-RUNTIME-QUALITY.md) | [AGENT-THINKING-API-RFC §Amendment A](rfc/AGENT-THINKING-API-RFC.md) | GitHub issue `#1757` / branche `1757-featruntime-05-support-mistral-reasoning-chunks-in-thought-stream` |
| `PROMPT-06` | `PROMPT-MARKETPLACE` | Dimitri | En attente de `PROMPT-04` | [BACKLOG §3d.10](backlog/BACKLOG.md) | [PROMPT-LIBRARY-RFC](rfc/PROMPT-LIBRARY-RFC.md) | `TBD` |
| `FRONT-09` | `KNOWLEDGE-WORKSPACE-REWORK` | Dimitri | En cours — A/C/D livrés 2026-06-18 : `TeamResourcesPage` à `/team/:teamId/resources` (arbre + liste paginée + CRUD, documents uniquement). Reste B (backend browse hardening), E (drawer détail), rename (pas d'endpoint) | [FRONTEND-BACKLOG §15](backlog/FRONTEND-BACKLOG.md) | [KNOWLEDGE-WORKSPACE-REWORK-RFC](rfc/KNOWLEDGE-WORKSPACE-REWORK-RFC.md) | branche `1772-…-kf-similarity-search` |
| `UX-01` | `UX-AUDIT` | Dimitri | A lancer | [BACKLOG §UX-1](backlog/BACKLOG.md) | [COMPONENT-UX](ux/COMPONENT-UX.md) | `TBD` |
| `FRONT-05` | `FRONTEND-CLEANUP` | Dimitri | En attente de `CHAT-03` | [FRONTEND-BACKLOG §7](backlog/FRONTEND-BACKLOG.md) | — | `TBD` |
| `FRONT-08` | `FRONTEND-AUTH-CONFIG` | Simon | En cours — implémenté sur branche, en attente de revue | [FRONTEND-BACKLOG §14](backlog/FRONTEND-BACKLOG.md) | [FRONTEND-AUTH-CONFIG-ENDPOINT-RFC](rfc/FRONTEND-AUTH-CONFIG-ENDPOINT-RFC.md) | GitHub issue `#1748` / branche `1748-front-08-frontend-auth-config` |
| `MIGR-00` | `KEA-SWIFT-CUTOVER` | Florian | Modèle migration: 4 topics (identity → data → metadata → products) + cherry-picks/parité | [KEA-MIGRATION-BACKLOG](backlog/KEA-MIGRATION-BACKLOG.md) | — | `TBD` |
| `MIGR-04` | `KEYCLOAK-IDENTITY-BOOTSTRAP` | Sébastien | Prérequis plateforme — préserver le `sub` (UUID) sur S3NS avant tout import de données | [KEA-MIGRATION-BACKLOG §0](backlog/KEA-MIGRATION-BACKLOG.md) | [KEYCLOAK-IDENTITY-BOOTSTRAP-S3NS](ops/KEYCLOAK-IDENTITY-BOOTSTRAP-S3NS.md) | `TBD` |
| `MIGR-06` | `MIGRATION-DATA-MIRROR` | Dimitri | Topic **data** — mc mirror MinIO key-for-key (laptop bridge, ~25 GB) | [KEA-MIGRATION-BACKLOG §0ter](backlog/KEA-MIGRATION-BACKLOG.md) | — | `TBD` |
| `MIGR-05` | `PLATFORM-IMPORT-SERVICE` | Dimitri | Topic **metadata** — RFC écrit, en attente de validation (config-only, fresh-target) | [KEA-MIGRATION-BACKLOG §0bis](backlog/KEA-MIGRATION-BACKLOG.md) | [PLATFORM-IMPORT-RFC](rfc/PLATFORM-IMPORT-RFC.md) | `TBD` |
| `MIGR-07` | `MIGRATION-PRODUCTS-REVECTORIZE` | Dimitri | Topic **products** — re-vectorisation sur la cible (Temporal sur output_process, RFC écrit) | [KEA-MIGRATION-BACKLOG §0quater](backlog/KEA-MIGRATION-BACKLOG.md) | [CORPUS-REVECTORIZE-RFC](rfc/CORPUS-REVECTORIZE-RFC.md) | `TBD` |
| `DEVOPS-FREDLAB` | `DEVOPS-FREDLAB` | Sébastien | **⚠️ CRITIQUE — reste le Helm chart pour GCP / GKE Autopilot interne** | [BACKLOG §3b](backlog/BACKLOG.md) | — | `TBD` |
| `OPS-01` | `DEVOPS-HELM-CHART` | Simon | A lancer — prerequis CI + Docker clos | [BACKLOG §3b.11](backlog/BACKLOG.md) | [FRED-CHART-MODERNIZATION-RFC](rfc/FRED-CHART-MODERNIZATION-RFC.md) | GitHub issue `#1685` |
| `OPS-04` | `TASK-EVENT-STREAM` | Dimitri | En cours — correctif local memory scheduler pour debloquer les taches ingestion pending | [BACKLOG §OPS-04](backlog/BACKLOG.md) | [TASK-EVENT-STREAM-RFC](rfc/TASK-EVENT-STREAM-RFC.md) | Waived GitHub issue for local session |
| `DEVOPS-FREDLAB` | `DEVOPS-FREDLAB` | Sébastien | **⚠️ CRITIQUE — chart Helm clos, lancer le déploiement interne GKE Autopilot** | [BACKLOG §3b](backlog/BACKLOG.md) | — | `TBD` |
| `OPS-05` | `DEVOPS-STORAGE-NAMING` | Simon | A lancer — RFC/backlog prets | [BACKLOG §OPS-05](backlog/BACKLOG.md) | [OBJECT-STORAGE-NAMING-RFC](rfc/OBJECT-STORAGE-NAMING-RFC.md) | `TBD` |

## Execution Refs Already Known

| Ticket     | Responsable | Statut | Backlog                                             | Execution                                                                                                    | Note PMO                                                                                                                                                                                                                                                                                           |
| ---------- | ----------- | ------ | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `FRONT-07` | Dimitri     | Clos   | [FRONTEND-BACKLOG §13](backlog/FRONTEND-BACKLOG.md) | GitHub issue `#1668` / branche `1668-rework-frontend-ui-architecture-compliance`                             | SearchField + FilterChips + TagInput molecules extraits; PromptsPage + TuningFieldRenderer migrés; token `--outline-variant` ajouté; CSS mort supprimé.                                                                                                                                            |
| `CHAT-04`  | Simon       | Clos   | [CHAT-UI-BACKLOG §4](backlog/CHAT-UI-BACKLOG.md)    | GitHub issue `#1706` / branche `1706-chat-04-chat-attachments-option-a-composer-upload-ux-scheduler-task-ui` | CHAT-04 complet pour Swift: UX Option A du composer + drag-and-drop, persistence control-plane `session_attachments` (`summary_md` + `storage_key`), drawer latéral de fichiers avec preview markdown, réhydratation au reload, et suppression forte orchestrée via Knowledge Flow. Validation: control-plane, knowledge-flow et frontend `make code-quality` + `make test`. |
| `OPS-01`   | Simon       | Clos   | [BACKLOG §3b.11](backlog/BACKLOG.md)                | GitHub issue `#1685`                                                                                         | Chart Helm modernisé vers `fred-agents`; `runtime_catalog_sources`, `/fred/agents/v2`, overlays `k3d`, proxy frontend et probes alignés; validation `helm template` + `make code-quality` + `make test`.                                                                                           |
| `CHAT-10`  | Marc        | Clos   | [CHAT-UI-BACKLOG §11](backlog/CHAT-UI-BACKLOG.md)   | Branche `feature/swift-test`                                                                                 | `MarkdownRenderer` reconnaît désormais les fences `mindmap` / `mindmap-json` et les route vers `MindMapBlock`, avec validation JSON, garde-fou sur le nombre de noeuds, arbre interactif et fallback brut en cas d'erreur de parsing.                                                              |
| `OPS-03`   | Simon       | Clos   | [BACKLOG §3b.13](backlog/BACKLOG.md)                | GitHub issue `#1664`                                                                                         | Packaging Docker moderne aligne sur `fred-agents`; images et startup contracts consideres fermes pour la pile swift cible GKE Autopilot.                                                                                                                                                           |
| `OPS-02`   | Sébastien   | Clos   | [BACKLOG §3b.12](backlog/BACKLOG.md)                | GitHub issue `#1663`                                                                                         | CI Swift alignee sur les artefacts modernes: build/push `fred-agents`, `control-plane-backend`, `knowledge-flow-backend`, `frontend`, avec validation chart toujours calée sur `deploy/charts/fred`.                                                                                               |
| `CHAT-09`  | Dimitri     | Clos   | [CHAT-UI-BACKLOG §10](backlog/CHAT-UI-BACKLOG.md)   | GitHub issue `#1654`                                                                                         | Streaming block-fence UX durcie: shell CodeBlock unique pendant le stream pour Mermaid, code, math et directives; rendu final specialise a la fermeture du fence. Validation live pod reste non bloquante.                                                                                         |
| `CTRLP-06` | Florian     | Ouvert | [BACKLOG §3.10](backlog/BACKLOG.md)                 | GitHub issue `kea #1601`                                                                                     | Correctif partiel deja fait; il reste l'agregation des erreurs et le corps 422 structure.                                                                                                                                                                                                          |
| `CHAT-12`  | Dimitri     | Clos   | [CHAT-UI-BACKLOG §13](backlog/CHAT-UI-BACKLOG.md)   | Branche `1772-featknowledge-flow-targeted-similarity-comparison-search-kf-similarity-search`                 | Molecule partagée `MenuPopover` + `MenuPopoverItem` extraite (grammaire du menu profil); `UserProfile` et `SearchConfig` en sont désormais deux instances. `SearchConfig` perd ses encadrés + libellés en capitales: bouton "Joindre des fichiers" devenu un item, Document/Recherche/Portée en items homogènes avec valeur en ligne + chevron. Ligne "Prompts" (PROMPT-05) prête mais non câblée (bloquée par PROMPT-03). Frontend `make code-quality` + `make test`. |

`TEAM RFC set` currently means:

- `FRED-TEAM-CONFIG-RFC.md`
- `TEAM-PLATFORM-POLICY-RFC.md`
- `TEAM-ROUTING-POLICY-RFC.md`
- `PROMPT-LIBRARY-TEAM-SCOPE-AMENDMENT-RFC.md` _(superseded 2026-06-19 — folded into `PROMPT-LIBRARY-RFC.md`; kept for rationale)_
