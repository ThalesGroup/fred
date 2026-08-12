# GEMINI.md

This repository uses `CLAUDE.md` as the primary development workflow and governance guide.

Before making any code or documentation change, read and follow:

1. The root `CLAUDE.md`
2. This root `GEMINI.md`
3. Any nested `AGENTS.md`, `AGENTS.override.md`, or `CLAUDE.md` files in the target subdirectory

When `CLAUDE.md` refers to Claude or Claude Code, apply the same instruction to Gemini unless the instruction is technically impossible in Gemini.

Minimum required behavior:

- Keep implementation minimal.
- Do not over-engineer.
- Run `make code-quality` and `make test` in touched projects.
- Keep default tests offline; mark external dependency tests as `integration`.

If there is a conflict that cannot be resolved safely, stop and ask for clarification before changing files.
