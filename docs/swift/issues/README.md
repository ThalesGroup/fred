# Swift Technical Issues (Pre-Backlog)

Purpose: track important technical risks and architecture issues in a short, easy-to-read format before they are promoted to backlog execution.

Use this folder when:
- the issue is real but not yet scheduled
- you need concise evidence and decision-ready context
- a long GitHub issue would add noise

Do not use this folder when:
- execution is already approved and planned in backlog
- the item is done or purely historical

## Lifecycle

1. Create `ISSUE-XXX-short-name.md` with status `open`.
2. Keep the file short and factual.
3. If accepted for execution, add one backlog item and set:
   - `Status: promoted`
   - `Promoted to: <backlog ref>`
4. If resolved without backlog, set `Status: done` and add one-line resolution.

## Naming

- File format: `ISSUE-001-topic.md`
- Increment by 1
- Keep topic in lowercase with hyphens

## Required Sections

- Title
- Status
- Owner
- Target window
- Problem
- Why it matters
- Current evidence
- Scope
- Proposed fix
- Acceptance checks
- Promotion

## Template

```md
# ISSUE-XXX - <short title>

Status: open
Owner: TBD
Target window: TBD

## Problem
<2-5 lines>

## Why it matters
<1-3 bullets>

## Current evidence
- <file path + short fact>
- <file path + short fact>

## Scope
- Active paths:
- Not in scope:

## Proposed fix
- Option A:
- Option B:

## Acceptance checks
- [ ]
- [ ]

## Promotion
Promoted to: none
Notes: 
```
