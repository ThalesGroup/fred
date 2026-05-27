# Fred Repository Orientation

This file is a lightweight orientation guide for AI coding assistants and new contributors.

It is not the primary instruction file.

For mandatory development workflow, governance, and implementation rules, read these files first:

1. `CLAUDE.md` — primary team development workflow and governance guide
2. `AGENTS.md` — Codex / AI assistant entrypoint and instruction bridge
3. Any nested `AGENTS.md`, `AGENTS.override.md`, or `CLAUDE.md` files in the target subdirectory

If this file conflicts with `CLAUDE.md` or `AGENTS.md`, follow `CLAUDE.md` and `AGENTS.md`.

---

## What Fred Is

Fred is an agentic platform organized around several platform planes:

- Execution/runtime plane
- Product and tenancy plane
- Knowledge plane
- Frontend/user-experience plane

The repository contains multiple applications, services, shared packages, and documentation areas. Before making changes, understand which plane and package own the behavior you are modifying.

---

## Repository Navigation

Start with:

- `CLAUDE.md` for workflow, governance, and development process
- `AGENTS.md` for Codex-compatible assistant instructions
- `README.md` for repository-level overview
- Relevant package-level `README.md` files
- Relevant `Makefile` targets before inventing new commands

Do not assume that similar-looking services have identical contracts or runtime behavior. Check the local package documentation and tests.

---

## Development Principle

Prefer small, targeted, reversible changes.

Before modifying code:

1. Identify the owning package or service.
2. Read the relevant local documentation.
3. Check existing patterns in nearby code.
4. Reuse existing abstractions instead of creating parallel ones.
5. Run the relevant quality and test commands defined by the package.

---

## Identity Concepts

Fred commonly distinguishes between:

- `agent_instance_id` — the configured/deployed agent instance
- `session_id` — a user interaction or conversation session
- request/message identifiers — individual runtime or transport-level events

Do not conflate these concepts. If changing persistence, runtime execution, tracing, or knowledge integration, verify the expected identity model in the relevant code and contracts.

---

## Common Commands

Prefer existing `make` targets over ad-hoc commands.

Common targets may include:

```bash
make run
make test
make code-quality
make lint
make type-check
```
