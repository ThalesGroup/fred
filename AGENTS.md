# Codex / AI Assistant Instructions

This repository uses `CLAUDE.md` as the primary development workflow and governance guide.

Before making any code or documentation change, read and follow:

1. The root `CLAUDE.md`
2. This root `AGENTS.md`
3. Any nested `AGENTS.md`, `AGENTS.override.md`, or `CLAUDE.md` files in the target subdirectory

When `CLAUDE.md` refers to Claude or Claude Code, apply the same instruction to Codex unless the instruction is technically impossible in Codex.

**OpenSpec comes before implementation.** For agreed, scoped work, create or
update the OpenSpec change before writing code and use its tasks and acceptance
criteria to guide the implementation. After verification and independent
review, update the artifacts with the final evidence and archive the change.

**OpenSpec is the one exception worth spelling out.** CLAUDE.md's OpenSpec
workflow (see "RFC vs. OpenSpec vs. doc") is driven by the `openspec` CLI, not
by a Claude-Code-only feature - but the
`openspec-propose`/`-apply-change`/`-archive-change`/`-explore`/`-sync-specs`/`-update-change`
names are Claude Code Skill wrappers, and the procedure each one runs is real
work, not just one CLI call: `.agents/skills/<name>/SKILL.md` (mirrored at
`.claude/skills/<name>/SKILL.md`) is the actual, plain-markdown procedure - read
and follow it directly. A bare `openspec new change <name>` only scaffolds empty
files (`.openspec.yaml` plus placeholders); the proposal/design/tasks/spec-delta
content only gets written by following `openspec-propose`'s steps (`openspec
status --json` for the artifact order, `openspec instructions <artifact-id>
--change <name> --json` per artifact, then drafting each one before
implementation). Likewise, archiving well means following
`openspec-archive-change`'s steps (completion checks, delta-spec sync, then the
move), not just calling `openspec archive`. Codex has no Skill tool to
auto-invoke these, but every one of these SKILL.md files is a plain file in the
repo Codex already reads - follow it by hand.

Conflict resolution order:

1. Explicit user instruction
2. Closest nested `AGENTS.override.md`, `AGENTS.md`, or `CLAUDE.md`
3. Root `CLAUDE.md`
4. Root `AGENTS.md`
5. Root `AGENT.md`, if present

If there is a conflict that cannot be resolved safely, stop and ask for clarification before changing files.

Do not implement changes until the required workflow checks from `CLAUDE.md` have been completed.

## Branch and draft PR workflow

Before any implementation, create or identify the GitHub issue that tracks the
work, then create a dedicated topic branch for that issue. Keep unrelated local
changes out of commits. At the end of the implementation, push the branch and
open a draft pull request for review. If the user explicitly asks to skip
planning artifacts such as OpenSpec for a small issue fix, honor that scope and
record the skipped workflow step in the close-out.
