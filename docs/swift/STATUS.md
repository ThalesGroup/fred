# Fred Platform — Current Status

**Purpose**: quick orientation for humans and assistants — who's around, what
the focus is, and where the real tracking lives. This file is deliberately
thin: it does not mirror GitHub, and it does not try to be a project
management system for a 3-person team.

Last updated: 2026-07-16

---

## Team (through end of July)

| Personne    | Focus                                     |
| ----------- | ------------------------------------------ |
| **Dimitri** | Full stack, architecture, lead             |
| **Florian** | Control-plane-backend, APIs, DB            |
| **Odelia**  | Agent evaluation (deepeval), parallel track |

Simon (core architecture — fred-runtime, fred-sdk, observability) returns the
week of 2026-07-20. Everyone else is on leave.

---

## Where the work actually lives

**GitHub Issues + Milestones are the single source of truth for active work.**
This file does not mirror them — query GitHub directly for the real list.

| Milestone                      | Due        | Open / Total | Link                                                    |
| ------------------------------- | ---------- | ------------- | -------------------------------------------------------- |
| **swift-golive**                | 2026-07-31 | 16 / 38       | https://github.com/ThalesGroup/fred/milestone/21          |
| **swift ga**                    | 2026-09-30 | 24 / 28       | https://github.com/ThalesGroup/fred/milestone/20          |
| Remediations CVSSI (Part 1)     | 2026-10-30 | 4 open        | https://github.com/ThalesGroup/fred/milestone/22          |
| Remediations CVSSI (Part 2)     | —          | 2 open        | https://github.com/ThalesGroup/fred/milestone/23          |

> If the `swift-golive` due date above doesn't match the real internal target,
> the GitHub milestone needs updating — that date, not this file, drives work.

For design/architecture decisions: `docs/swift/rfc/`. For a stable ID tied to
an RFC or a cross-cutting architecture decision: `docs/swift/data/id-legend.yaml`.
That registry's scope is intentionally narrow now (see below) — it is not a
mirror of every GitHub issue.

---

## This week

_Freeform, hand-edited each session. Replace this section, don't accumulate a
history in it — that's what closed GitHub issues are for._

- (nothing recorded yet — first entry after this reset)

---

## Retired docs (2026-07-16, updated 2026-07-21)

`docs/swift/backlog/BACKLOG.md` and `docs/swift/WORKPLAN.md` are frozen. They
tracked one finite migration project and a larger team, both now outdated —
`BACKLOG.md`'s migration is ~90% done, and the team is 3 people, not 6. They're
kept as historical record, not maintained.

`docs/swift/PMO-BOARD.md` and `docs/swift/data/sprint.yaml` were removed
(2026-07-21) rather than frozen — they duplicated GitHub without ever being
kept current. Current tracking = GitHub Issues/Milestones + this file. Never
recreate either file; if you need sprint/PMO-facing status, query GitHub
directly.

`docs/swift/data/id-legend.yaml` scope narrowed at the same time: register an
ID only when the work is tied to an RFC or a genuine cross-cutting
architecture decision — not for every issue. For everything else, the GitHub
issue itself (title, label, milestone) is the tracking unit; do not duplicate
it here or in a registry.

---

## Talking to Claude Code

Ask directly — Claude Code can query GitHub issues/milestones itself, no need
to keep a parallel list here:

- _"What's open in swift-golive?"_
- _"What's Florian working on this week?"_
- _"Is there an RFC covering X?"_
- _"What closed since Monday?"_ (ask it to check `gh issue list --state closed`)
