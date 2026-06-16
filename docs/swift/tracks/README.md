# docs/swift/tracks/

A **track** is a named body of work tied to one or more related task IDs, owned
by a specific person or pair, with a designated RFC (or explicit "none") and a
single backlog file as source of truth. Track manifests give coordinators and AI
assistants a one-page picture without reading the full backlog.

---

## Index of tracks

### Active

| Track     | Title                                         | Owner   | Status                                  | Manifest                                                           |
| --------- | --------------------------------------------- | ------- | --------------------------------------- | ------------------------------------------------------------------ |
| MEMORY-01 | Multi-agent conversational memory             | Dimitri | Core done — 4 hardening branches open   | [MEMORY-01-multi-agent-memory.md](MEMORY-01-multi-agent-memory.md) |
| PROMPT-01 | Prompt safety + library                       | Dimitri | Active — D1b, D2, D3 open; E/F deferred | _to write_                                                         |
| VALID-01  | E2E live stack validation                     | Simon   | In progress — blocked on live pod       | _to write_                                                         |
| CHAT-03   | Chat UI — agent options panel + session title | Dimitri   | In progress — blocked on VALID-01 gate  | _to write_                                                         |
| CTRLP-03  | Pod catalog + agent instance config           | Dimitri | Mostly done — model profiles deferred   | _to write_                                                         |
| FRONT-05  | Frontend agentic-backend cleanup              | Dimitri   | Not started                             | _to write_                                                         |
| EVAL-01   | Agent evaluation harness (deepeval)           | Odélia  | In progress — RFC exists                | _to write_                                                         |

### Recently closed

| Track                 | Title                                       | Owner           | Closed     | Manifest   |
| --------------------- | ------------------------------------------- | --------------- | ---------- | ---------- |
| RUNTIME-02 / FRONT-06 | Typed ChatContext round-trip                | Dimitri / Dimitri | 2026-05-11 | _to write_ |
| QUALITY-01            | fred-runtime quality refactor               | Simon           | 2026-04-27 | _to write_ |
| CTRLP-05              | Control-plane developer CLI                 | Dimitri         | 2026-04-25 | _to write_ |
| F track               | Session lifecycle APIs (CTRLP-01, CTRLP-02) | Florian         | 2026-05-06 | _to write_ |
| CHAT-01 / CHAT-02     | Chat UI architecture + markdown rendering   | Dimitri / Dimitri | 2026-05-04 | _to write_ |
| FRONT-01–FRONT-04     | Frontend migration phases                   | Multiple        | 2026-05-04 | _to write_ |

Manifests marked _to write_ will be filled in during follow-up sessions.

---

## Track manifest template

```markdown
# Track: <ID> — <Title>

| Field      | Value                                |
| ---------- | ------------------------------------ |
| Owner      |                                      |
| Status     | open / in_progress / done / deferred |
| RFC        | path or "none — mechanical"          |
| Backlog    | path to backlog section              |
| Blocked on | description or "none"                |

## What this track delivers

One paragraph.

## Open items

- [ ] ID — description

## Closed items

- [x] ID — description (date)

## Notes

Cross-track dependencies or constraints.
```

---

## Rules for track manifests

1. One file per track, named `<ID>-<slug>.md`. Use the canonical ID from `id-legend.yaml`.
2. Maximum 80 lines per manifest.
3. Every ID referenced must exist in `docs/swift/data/id-legend.yaml`. Do not invent IDs.
4. The RFC link must point to an actual file in `docs/swift/rfc/`. If none, say "none — mechanical".
5. The backlog link must point to an actual section in a backlog file under `docs/swift/backlog/`.
6. Do not duplicate spec content — link to the RFC and backlog instead.
7. Status must match `id-legend.yaml`. Update both files together.
