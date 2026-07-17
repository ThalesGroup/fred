# swift-golive — what's left

Snapshot of the **`swift-golive`** GitHub milestone only, taken 2026-07-16.
16 open / 38 total. This file is a triage view, not a source of truth —
GitHub is. Re-generate rather than hand-edit as issues close.


---

## Dimitri — 6 issues, all "Must have"

- [ ] **#1994** — Ingestion upload failures before a task exists are silently dropped, no error shown to the user (bug, root cause identified — fix is in `streamDocumentUpload.tsx` + backend `ingestion_service.py`)
- [ ] **#1969** — Cherry-picks from Kea (umbrella issue, ~10 sub-items checklist inside — some marked `[needed]`/blocking for cutover, some `[good-to-have]`; open the issue, only the `[needed]` ones matter tonight)
- [ ] **#1962** — Disable user file sharing in personal space (security requirement)
- [ ] **#1954** — Finalize migration import/export: kea prompt mapping (`MIGR-05.11`) + full platform team-config export zip
- [ ] **#1950** — LICENSE-01: make pymupdf/pymupdf4llm optional, ship non-AGPL default path (3 unconditional import sites identified)
- [ ] **#1913** — Agent catalog admission — govern deployable templates by control-plane policy (RFC exists: `AGENT-VISIBILITY-RFC.md`; has its own scope checklist)

## Florian — 6 issues (4 "Must have", 2 unlabeled)

- [ ] **#1911** — Port agent documentation help link from Kea to Swift — *Must have*
- [ ] **#1906** — Port document-access toolkit additions (tree + summarize tools, rename) from Kea to Swift — *Must have*
- [ ] **#1905** — Port WritableDocument (agent↔user collaborative document) feature from Kea to Swift — *Must have*
- [ ] **#1903** — Port PPT Filler Toolkit feature from Kea to Swift — *Must have*
- [ ] **#1961** — Agent Capability — single abstraction for modular agent features (large, no priority label — confirm it's actually in scope for tomorrow, or re-milestone)
- [ ] **#1952** — Port #1940 to swift: finish agent audit fields (`updated_by` + name resolution) — Front-End scope, no priority label

## Simon — 2 issues, both "Must have" — **blocked: Simon is away, back 2026-07-20**

- [ ] **#1956** — Chat UI: review and close out remaining kea capability parity feedback
- [ ] **#1955** — Triage and fix dependency vulnerability alerts (GitLab scan)

If either is truly blocking for tomorrow, it needs reassignment tonight — it
will not move on its own while Simon is out.

## No owner yet

- [ ] **#1996** — Global: Kea vs Swift review (bugs and regressions) — no priority label, but a large multi-area checklist (navbar, agents, resources, prompts). Needs triage: who owns closing this out?
- [ ] **#1920** — CTRLP-12 follow-ups: task/erasure progress robustness — *Nice-to-have*, no owner. Lowest priority on this list — candidate to re-milestone to `swift ga` if time is short.

---

## Suggested read order for tonight

1. Skim **#1969** and **#1996** first — both are umbrella issues whose real
   scope is hidden inside a sub-checklist, not the title. They could each be
   "one thing" or "ten things" depending on what's actually still unchecked.
2. Confirm with Florian which of his 6 are realistically closeable tonight —
   3 are Kea→Swift ports of full features (#1905, #1903, #1906), not small fixes.
3. Decide now whether **#1956**/**#1955** (Simon, away) need a stand-in owner
   or can wait — don't discover this at the last minute.
4. Re-milestone **#1920** (and anything else that won't make it) to `swift ga`
   explicitly, rather than leaving it open under a milestone it will miss.
