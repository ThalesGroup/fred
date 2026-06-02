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

Last updated: 2026-06-01

## Active And Next Up

| Ticket | Sprint / file de travail | Responsable actuel | Statut PMO | Backlog | RFC / decision | Execution |
| ------ | ------------------------ | ------------------ | ---------- | ------- | -------------- | --------- |
| `QUALITY-02` | `QUALITY-02` | Florian | **En cours — deadline 2026-06-06** | [BACKLOG §Phase QUALITY](backlog/BACKLOG.md) | — | `TBD` |
| `FILES-01` | `AGENT-FILESYSTEM` | Florian | **En cours — deadline 2026-06-06** | [CHAT-UI-BACKLOG §4](backlog/CHAT-UI-BACKLOG.md) | [AGENT-FILESYSTEM-RFC](rfc/AGENT-FILESYSTEM-RFC.md) | `TBD` |
| `VALID-01` | `VALIDATION-E2E` | Simon | Bloque | [BACKLOG §3b.7](backlog/BACKLOG.md) | — | `TBD` |
| `CHAT-03` | `CHAT-OPTIONS` | Felix | En cours | [CHAT-UI-BACKLOG §3](backlog/CHAT-UI-BACKLOG.md) | — | `TBD` |
| `MEMORY-02` | `MEMORY-CHECKPOINT-ISOLATION` | Marc | En cours | [MEMORY BACKLOG §F.1](backlog/MULTI-AGENT-MEMORY-BACKLOG.md) | [MULTI-AGENT-MEMORY-RFC](rfc/MULTI-AGENT-MEMORY-RFC.md) | `TBD` |
| `MEMORY-03` | `MEMORY-REMOTE-AGENT` | Dimitri | En cours | [MEMORY BACKLOG §F.2](backlog/MULTI-AGENT-MEMORY-BACKLOG.md) | [MULTI-AGENT-MEMORY-RFC](rfc/MULTI-AGENT-MEMORY-RFC.md) | `TBD` |
| `MEMORY-04` | `MEMORY-LOCAL-AGENT` | Dimitri | En cours | [MEMORY BACKLOG §F.3](backlog/MULTI-AGENT-MEMORY-BACKLOG.md) | [MULTI-AGENT-MEMORY-RFC](rfc/MULTI-AGENT-MEMORY-RFC.md) | `TBD` |
| `MEMORY-05` | `MEMORY-HISTORY-CAP` | Simon | Best effort | [MEMORY BACKLOG §F.4](backlog/MULTI-AGENT-MEMORY-BACKLOG.md) | [MULTI-AGENT-MEMORY-RFC](rfc/MULTI-AGENT-MEMORY-RFC.md) | `TBD` |
| `PROMPT-04` | `PROMPT-AGENT-FORM` | Dimitri | Planifie apres `MEMORY-REMOTE-AGENT` + `MEMORY-LOCAL-AGENT` | [BACKLOG §3d.9](backlog/BACKLOG.md) | [PROMPT-LIBRARY-RFC](rfc/PROMPT-LIBRARY-RFC.md) | `TBD` |
| `EVAL-01` | `EVAL-HARNESS` | Marc | Best effort | — | [AGENT-EVALUATION-RFC](rfc/AGENT-EVALUATION-RFC.md) | `TBD` |
| `TEAM-01` | `TEAM-CONFIG-RFC` | Dimitri | En cours (RFC-only) | [BACKLOG §3d.11](backlog/BACKLOG.md) | [TEAM RFC set](rfc/FRED-TEAM-CONFIG-RFC.md) | `TBD` |
| `CTRLP-10` | `CTRLP-10` | Dimitri | En cours — isolation personelle + durcissement runtime + 6.4.F livrés | [BACKLOG §6.4.F](backlog/BACKLOG.md) | [PERSONAL-TEAM-ISOLATION-RFC](rfc/PERSONAL-TEAM-ISOLATION-RFC.md) | Branche `1666-ctrlp-10-per-user-personal-space-replace-shared-team_id-constant` |
| `CTRLP-09` | `RUNTIME-DYNAMIC-ROUTING` | Simon | A lancer — RFC ecrit | [BACKLOG §3d.12](backlog/BACKLOG.md) | [DISCOVERED-RUNTIME-ROUTING-RFC](rfc/DISCOVERED-RUNTIME-ROUTING-RFC.md) | `TBD` |
| `PROMPT-05` | `PROMPT-CONTEXT-PICKER` | Felix | En attente de CHAT-OPTIONS | [BACKLOG §3d.9](backlog/BACKLOG.md) | [PROMPT-LIBRARY-RFC](rfc/PROMPT-LIBRARY-RFC.md) | `TBD` |
| `CTRLP-04` | `AGENT-MODEL-PROFILES` | Dimitri | En attente | [BACKLOG §3d](backlog/BACKLOG.md) | — | `TBD` |
| `PROMPT-06` | `PROMPT-MARKETPLACE` | Dimitri | En attente de `PROMPT-04` | [BACKLOG §3d.10](backlog/BACKLOG.md) | [PROMPT-LIBRARY-RFC](rfc/PROMPT-LIBRARY-RFC.md) | `TBD` |
| `UX-01` | `UX-AUDIT` | Felix | A lancer | [BACKLOG §UX-1](backlog/BACKLOG.md) | [COMPONENT-UX](ux/COMPONENT-UX.md) | `TBD` |
| `FRONT-05` | `FRONTEND-CLEANUP` | Felix | En attente de `CHAT-03` | [FRONTEND-BACKLOG §7](backlog/FRONTEND-BACKLOG.md) | — | `TBD` |
| `DEVOPS-FREDLAB` | `DEVOPS-FREDLAB` | Sébastien | **⚠️ CRITIQUE — cible semaine: GCP / GKE Autopilot interne** | [BACKLOG §3b](backlog/BACKLOG.md) | — | `TBD` |
| `OPS-02` | `DEVOPS-CI-PIPELINE` | Sébastien | En cours — artefacts modernes pour GKE Autopilot | [BACKLOG §3b.12](backlog/BACKLOG.md) | [FRED-CHART-MODERNIZATION-RFC](rfc/FRED-CHART-MODERNIZATION-RFC.md) | GitHub issue `#1663` |
| `OPS-03` | `DEVOPS-DOCKER-PACKAGING` | Simon | En cours — Dockerfiles/images pour GKE Autopilot | [BACKLOG §3b.13](backlog/BACKLOG.md) | [FRED-CHART-MODERNIZATION-RFC](rfc/FRED-CHART-MODERNIZATION-RFC.md) | GitHub issue `#1664` |
| `OPS-01` | `DEVOPS-HELM-CHART` | Sébastien | A lancer cette semaine apres cloture CI + Docker | [BACKLOG §3b.11](backlog/BACKLOG.md) | [FRED-CHART-MODERNIZATION-RFC](rfc/FRED-CHART-MODERNIZATION-RFC.md) | `TBD` |

## Execution Refs Already Known

| Ticket | Responsable | Statut | Backlog | Execution | Note PMO |
| ------ | ----------- | ------ | ------- | --------- | -------- |
| `CHAT-09` | Dimitri | Clos | [CHAT-UI-BACKLOG §10](backlog/CHAT-UI-BACKLOG.md) | GitHub issue `#1654` | Streaming block-fence UX durcie: shell CodeBlock unique pendant le stream pour Mermaid, code, math et directives; rendu final specialise a la fermeture du fence. Validation live pod reste non bloquante. |
| `CTRLP-06` | Florian | Ouvert | [BACKLOG §3.10](backlog/BACKLOG.md) | GitHub issue `kea #1601` | Correctif partiel deja fait; il reste l'agregation des erreurs et le corps 422 structure. |

`TEAM RFC set` currently means:

- `FRED-TEAM-CONFIG-RFC.md`
- `TEAM-PLATFORM-POLICY-RFC.md`
- `TEAM-ROUTING-POLICY-RFC.md`
- `PROMPT-LIBRARY-TEAM-SCOPE-AMENDMENT-RFC.md`
