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

Last updated: 2026-06-09

## Active And Next Up

| Ticket | Sprint / file de travail | Responsable actuel | Statut PMO | Backlog | RFC / decision | Execution |
| ------ | ------------------------ | ------------------ | ---------- | ------- | -------------- | --------- |
| `QUALITY-02` | `QUALITY-02` | Florian | **En cours — deadline 2026-06-06** | [BACKLOG §Phase QUALITY](backlog/BACKLOG.md) | — | `TBD` |
| `FILES-01` | `AGENT-FILESYSTEM` | Florian | **En cours — deadline 2026-06-06** | [CHAT-UI-BACKLOG §4](backlog/CHAT-UI-BACKLOG.md) | [AGENT-FILESYSTEM-RFC](rfc/AGENT-FILESYSTEM-RFC.md) | `TBD` |
| `CHAT-04` | `CHAT-ATTACHMENTS-OPTION-A` | Simon | A lancer — branch dediee requise | [CHAT-UI-BACKLOG §4](backlog/CHAT-UI-BACKLOG.md) | Option A: composer upload UX, base64 image context, drag-and-drop ingestion; no full AGENT-FILESYSTEM backend implementation | GitHub issue #1706 |
| `VALID-01` | `VALIDATION-E2E` | Simon | Bloque | [BACKLOG §3b.7](backlog/BACKLOG.md) | — | `TBD` |
| `CHAT-03` | `CHAT-OPTIONS` | Marc | En cours | [CHAT-UI-BACKLOG §3](backlog/CHAT-UI-BACKLOG.md) | — | GitHub issue `#1730` |
| `MEMORY-02` | `MEMORY-CHECKPOINT-ISOLATION` | Marc | En cours | [MEMORY BACKLOG §F.1](backlog/MULTI-AGENT-MEMORY-BACKLOG.md) | [MULTI-AGENT-MEMORY-RFC](rfc/MULTI-AGENT-MEMORY-RFC.md) | `TBD` |
| `MEMORY-03` | `MEMORY-REMOTE-AGENT` | Dimitri | En cours | [MEMORY BACKLOG §F.2](backlog/MULTI-AGENT-MEMORY-BACKLOG.md) | [MULTI-AGENT-MEMORY-RFC](rfc/MULTI-AGENT-MEMORY-RFC.md) | `TBD` |
| `MEMORY-04` | `MEMORY-LOCAL-AGENT` | Dimitri | En cours | [MEMORY BACKLOG §F.3](backlog/MULTI-AGENT-MEMORY-BACKLOG.md) | [MULTI-AGENT-MEMORY-RFC](rfc/MULTI-AGENT-MEMORY-RFC.md) | `TBD` |
| `MEMORY-05` | `MEMORY-HISTORY-CAP` | Simon | Best effort | [MEMORY BACKLOG §F.4](backlog/MULTI-AGENT-MEMORY-BACKLOG.md) | [MULTI-AGENT-MEMORY-RFC](rfc/MULTI-AGENT-MEMORY-RFC.md) | `TBD` |
| `PROMPT-04` | `PROMPT-AGENT-FORM` | Dimitri | Planifie apres `MEMORY-REMOTE-AGENT` + `MEMORY-LOCAL-AGENT` | [BACKLOG §3d.9](backlog/BACKLOG.md) | [PROMPT-LIBRARY-RFC](rfc/PROMPT-LIBRARY-RFC.md) | `TBD` |
| `EVAL-01` | `EVAL-HARNESS` | Odelia | En cours | [AGENT-EVALUATION-BACKLOG](backlog/AGENT-EVALUATION-BACKLOG.md) | [AGENT-EVALUATION-RFC v3](rfc/AGENT-EVALUATION-RFC.md) | GitHub issue `#1733` — RFC v3 replace + backlog align |
| `TEAM-01` | `TEAM-CONFIG-RFC` | Dimitri | En cours (RFC-only) | [BACKLOG §3d.11](backlog/BACKLOG.md) | [TEAM RFC set](rfc/FRED-TEAM-CONFIG-RFC.md) | `TBD` |
| `CTRLP-10` | `CTRLP-10` | Dimitri | En cours — isolation personelle + durcissement runtime + 6.4.F livrés | [BACKLOG §6.4.F](backlog/BACKLOG.md) | [PERSONAL-TEAM-ISOLATION-RFC](rfc/PERSONAL-TEAM-ISOLATION-RFC.md) | Branche `1666-ctrlp-10-per-user-personal-space-replace-shared-team_id-constant` |
| `CTRLP-09` | `RUNTIME-DYNAMIC-ROUTING` | Simon | A lancer — RFC ecrit | [BACKLOG §3d.12](backlog/BACKLOG.md) | [DISCOVERED-RUNTIME-ROUTING-RFC](rfc/DISCOVERED-RUNTIME-ROUTING-RFC.md) | `TBD` |
| `PROMPT-05` | `PROMPT-CONTEXT-PICKER` | Dimitri | En attente de CHAT-OPTIONS | [BACKLOG §3d.9](backlog/BACKLOG.md) | [PROMPT-LIBRARY-RFC](rfc/PROMPT-LIBRARY-RFC.md) | `TBD` |
| `CTRLP-04` | `AGENT-MODEL-PROFILES` | Dimitri | En attente | [BACKLOG §3d](backlog/BACKLOG.md) | — | `TBD` |
| `PROMPT-06` | `PROMPT-MARKETPLACE` | Dimitri | En attente de `PROMPT-04` | [BACKLOG §3d.10](backlog/BACKLOG.md) | [PROMPT-LIBRARY-RFC](rfc/PROMPT-LIBRARY-RFC.md) | `TBD` |
| `UX-01` | `UX-AUDIT` | Dimitri | A lancer | [BACKLOG §UX-1](backlog/BACKLOG.md) | [COMPONENT-UX](ux/COMPONENT-UX.md) | `TBD` |
| `FRONT-05` | `FRONTEND-CLEANUP` | Dimitri | En attente de `CHAT-03` | [FRONTEND-BACKLOG §7](backlog/FRONTEND-BACKLOG.md) | — | `TBD` |
| `MIGR-00` | `KEA-SWIFT-CUTOVER` | Florian | A définir — 3 workstreams: cherry-picks, DB migration, feature parity | [KEA-MIGRATION-BACKLOG](backlog/KEA-MIGRATION-BACKLOG.md) | — | `TBD` |
| `DEVOPS-FREDLAB` | `DEVOPS-FREDLAB` | Sébastien | **⚠️ CRITIQUE — reste le Helm chart pour GCP / GKE Autopilot interne** | [BACKLOG §3b](backlog/BACKLOG.md) | — | `TBD` |
| `OPS-01` | `DEVOPS-HELM-CHART` | Simon | A lancer — prerequis CI + Docker clos | [BACKLOG §3b.11](backlog/BACKLOG.md) | [FRED-CHART-MODERNIZATION-RFC](rfc/FRED-CHART-MODERNIZATION-RFC.md) | GitHub issue `#1685` |
| `DEVOPS-FREDLAB` | `DEVOPS-FREDLAB` | Sébastien | **⚠️ CRITIQUE — chart Helm clos, lancer le déploiement interne GKE Autopilot** | [BACKLOG §3b](backlog/BACKLOG.md) | — | `TBD` |
| `OPS-05` | `DEVOPS-STORAGE-NAMING` | Simon | A lancer — RFC/backlog prets | [BACKLOG §OPS-05](backlog/BACKLOG.md) | [OBJECT-STORAGE-NAMING-RFC](rfc/OBJECT-STORAGE-NAMING-RFC.md) | `TBD` |

## Execution Refs Already Known

| Ticket | Responsable | Statut | Backlog | Execution | Note PMO |
| ------ | ----------- | ------ | ------- | --------- | -------- |
| `FRONT-07` | Dimitri | Clos | [FRONTEND-BACKLOG §13](backlog/FRONTEND-BACKLOG.md) | GitHub issue `#1668` / branche `1668-rework-frontend-ui-architecture-compliance` | SearchField + FilterChips + TagInput molecules extraits; PromptsPage + TuningFieldRenderer migrés; token `--outline-variant` ajouté; CSS mort supprimé. |
| `OPS-01` | Simon | Clos | [BACKLOG §3b.11](backlog/BACKLOG.md) | GitHub issue `#1685` | Chart Helm modernisé vers `fred-agents`; `runtime_catalog_sources`, `/fred/agents/v2`, overlays `k3d`, proxy frontend et probes alignés; validation `helm template` + `make code-quality` + `make test`. |
| `CHAT-10` | Marc | Clos | [CHAT-UI-BACKLOG §11](backlog/CHAT-UI-BACKLOG.md) | Branche `feature/swift-test` | `MarkdownRenderer` reconnaît désormais les fences `mindmap` / `mindmap-json` et les route vers `MindMapBlock`, avec validation JSON, garde-fou sur le nombre de noeuds, arbre interactif et fallback brut en cas d'erreur de parsing. |
| `OPS-03` | Simon | Clos | [BACKLOG §3b.13](backlog/BACKLOG.md) | GitHub issue `#1664` | Packaging Docker moderne aligne sur `fred-agents`; images et startup contracts consideres fermes pour la pile swift cible GKE Autopilot. |
| `OPS-02` | Sébastien | Clos | [BACKLOG §3b.12](backlog/BACKLOG.md) | GitHub issue `#1663` | CI Swift alignee sur les artefacts modernes: build/push `fred-agents`, `control-plane-backend`, `knowledge-flow-backend`, `frontend`, avec validation chart toujours calée sur `deploy/charts/fred`. |
| `CHAT-09` | Dimitri | Clos | [CHAT-UI-BACKLOG §10](backlog/CHAT-UI-BACKLOG.md) | GitHub issue `#1654` | Streaming block-fence UX durcie: shell CodeBlock unique pendant le stream pour Mermaid, code, math et directives; rendu final specialise a la fermeture du fence. Validation live pod reste non bloquante. |
| `CTRLP-06` | Florian | Ouvert | [BACKLOG §3.10](backlog/BACKLOG.md) | GitHub issue `kea #1601` | Correctif partiel deja fait; il reste l'agregation des erreurs et le corps 422 structure. |

`TEAM RFC set` currently means:

- `FRED-TEAM-CONFIG-RFC.md`
- `TEAM-PLATFORM-POLICY-RFC.md`
- `TEAM-ROUTING-POLICY-RFC.md`
- `PROMPT-LIBRARY-TEAM-SCOPE-AMENDMENT-RFC.md`
