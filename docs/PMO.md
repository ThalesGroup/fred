# docs/PMO.md

Coordination guide for Claire and Arnaud. No coding background required.
This guide tells you how to get project status, track progress, and update
planning files using Claude Code — without reading code.

---

## 1. One-time setup

1. Install **VS Code** — download from [code.visualstudio.com](https://code.visualstudio.com).
2. In VS Code, open Extensions (left sidebar), search **Claude Code** and install it.
3. Open this repository: File → Open Folder → select the `swift` folder.
4. Open the Claude panel (bottom status bar, or `Ctrl+Shift+P` → "Claude Code").
5. Sign in with your Anthropic account when prompted.

You are ready. Ask Claude questions directly in the chat panel.

---

## 2. The four files that matter

You do not need to browse the whole repository. These four files answer every
coordination question:

| File                             | What it tells you                                                |
| -------------------------------- | ---------------------------------------------------------------- |
| `docs/swift/STATUS.md`           | Who is working on what, what was delivered, what is blocked      |
| `docs/swift/data/sprint.yaml`    | Structured sprint data — current items, owners, status           |
| `docs/swift/data/id-legend.yaml` | Registry of every tracked feature with its ID and owner          |
| `docs/swift/tracks/`             | One file per active track — summary, RFC reference, backlog link |

You never need to edit these files manually. Ask Claude to read them and summarise,
or ask Claude to make a specific update (see §5).

---

## 3. Questions to ask Claude

Type these directly into the Claude Code chat panel. Claude reads the files above
and answers in plain language.

**Status and ownership**

- _"What is Simon working on this week?"_
- _"Who owns the chat UI?"_
- _"What features are blocked right now, and why?"_
- _"What was closed since Monday?"_

**Feature progress**

- _"What is the status of the prompt library feature?"_
- _"How far along is chat UI Phase 6?"_
- _"What is PROMPT-04?"_

**Planning and roadmap**

- _"What are the next three things Dimitri will work on?"_
- _"Which milestones are on track and which are at risk?"_
- _"What is still open from last sprint?"_

**Sanity checks**

- _"Are there any features listed as in progress but with no owner?"_
- _"Which items in sprint.yaml are marked done but not closed in STATUS.md?"_

---

## 4. Weekly rhythm

**Monday — refresh**
Ask Claude: _"Summarise what changed since last Friday and what the team is
starting this week."_ Use the answer as your Monday sync input.

**Wednesday — check**
Ask Claude: _"Are there any blocked items? What decisions are pending?"_
Surface blockers to the relevant developer if they have not already raised them.

**Friday — closure**
Ask Claude: _"What was completed this week? Are any sprint items that should be
closed still marked open?"_ Flag discrepancies to the item owner.

---

## 5. Updating files with Claude's help

When you need to close a sprint item, add a tracked feature, or record a decision,
ask Claude to do it:

- _"Mark MEMORY-02 as done in id-legend.yaml and STATUS.md."_
- _"Add a new tracked item for the onboarding flow review, owned by Claire,
  in the next sprint."_
- _"Update STATUS.md to show that VALID-01 is now unblocked."_

Claude will show you the proposed change before writing anything. Review it and
confirm. You do not need to understand the file format — Claude handles that.

Always ask Claude to explain what it changed and why, so you can catch mistakes.
If something looks wrong, say so — Claude will correct it.

---

## 6. When to ask Claude vs ask a human

| Situation                                          | Ask                                                 |
| -------------------------------------------------- | --------------------------------------------------- |
| Current status of a feature or person              | Claude                                              |
| What a task ID means                               | Claude                                              |
| Whether something is blocked                       | Claude                                              |
| Closing or updating a tracked item                 | Claude                                              |
| A technical decision (architecture, API design)    | A developer                                         |
| A priority conflict between two tracks             | Dimitri                                             |
| Something feels inconsistent across multiple files | Claude first, then a developer                      |
| A deadline needs to be set or changed              | Discuss with the team, then ask Claude to record it |

---

## 7. How work gets done — the team workflow

This team follows a **repo-first, issue-second** development process.
Every feature, fix, or improvement goes through these steps in order:

```
1. RFC (or RFC amendment)     docs/swift/rfc/
      ↓ design agreed
2. Backlog entry              docs/swift/backlog/BACKLOG.md (or sub-backlog)
      ↓ scope confirmed
3. Sprint entry + owner       docs/swift/data/sprint.yaml + id-legend.yaml
      ↓ developer confirms
4. GitHub issue created       links to RFC, backlog ref, and task ID
      ↓ execution handoff
5. Implementation             developer + code assistant (Claude Code)
      ↓ code quality + tests green
6. Close-out                  backlog ✓, sprint → recently_closed, STATUS.md updated
```

**Why this order matters:**

- Planning happens in the repository, not in issue trackers. The RFC and backlog
  are the source of truth for _what_ and _why_.
- The GitHub issue is the **execution handoff** — it signals that the work is
  scoped, assigned, and ready to implement. It references the repo docs; it does
  not replace them.
- A developer and their code assistant pick up the GitHub issue and implement it.
  The code assistant reads the RFC and backlog to understand the full context.

**As PMO, your role in this workflow:**

- Confirm that new tracked items appear in `sprint.yaml` and `id-legend.yaml`
  before a developer starts work.
- Ask Claude: _"Is there a GitHub issue for MCP-BEHAV?"_ to check step 4.
- If an item is being implemented but has no RFC, flag it to Dimitri.

---

## 8. What this guide does not cover

- **Writing code** — handled by the development team.
- **Architecture decisions** — see `docs/ARCHITECTURE.html` for orientation,
  then ask a developer.
- **Feature specifications** — tracked in `docs/swift/backlog/`. Ask Claude to
  summarise a spec; ask a developer to change it.
- **RFC proposals** — technical proposals in `docs/swift/rfc/`. Ask a developer
  to walk you through one if needed.

For developer onboarding and technical conventions, start with `docs/swift/README.md`.
