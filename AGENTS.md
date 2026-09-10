# Codex / AI Assistant Instructions

This repository uses `CLAUDE.md` as the primary development workflow and governance guide.

Before making any code or documentation change, read and follow:

1. The root `CLAUDE.md`
2. This root `AGENTS.md`
3. Any nested `AGENTS.md`, `AGENTS.override.md`, or `CLAUDE.md` files in the target subdirectory

When `CLAUDE.md` refers to Claude or Claude Code, apply the same instruction to Codex unless the instruction is technically impossible in Codex.

**OpenSpec is the one exception worth spelling out.** CLAUDE.md's OpenSpec workflow (see "RFC vs. OpenSpec vs. doc") is driven by the `openspec` CLI, not by a Claude-Code-only feature — the `openspec-propose`/`-apply-change`/`-archive-change`/`-explore`/`-sync-specs`/`-update-change` names are Claude Code Skill wrappers around that CLI. Codex has no Skill tool, so invoke the underlying commands directly (`openspec new change <name>`, `openspec archive <name>`, `openspec change validate <name>`, etc.) — same `openspec/changes/` and `openspec/specs/` files, same result, no Claude-specific step is actually required.

Conflict resolution order:

1. Explicit user instruction
2. Closest nested `AGENTS.override.md`, `AGENTS.md`, or `CLAUDE.md`
3. Root `CLAUDE.md`
4. Root `AGENTS.md`
5. Root `AGENT.md`, if present

If there is a conflict that cannot be resolved safely, stop and ask for clarification before changing files.

Do not implement changes until the required workflow checks from `CLAUDE.md` have been completed.
