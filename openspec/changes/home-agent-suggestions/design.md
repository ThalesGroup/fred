# Design

## Context
See proposal.md. SQL session_metadata already records owner, team and instance. Its updated_at has ORM onupdate and cannot prove an exchange. The chat explicitly PATCHes updated_at on send and persistence; reuse that signal rather than introducing a runtime callback.

## Goals / Non-Goals
Keep the launcher independent of analytics and runtime availability. Do not change sidebar semantics or inspect runtime histories on home requests.

## Decisions
- Add nullable last_activity_at to session_metadata and an owner/instance/activity index. Only an explicit activity PATCH stamps it with server UTC, monotonically. Title/context changes and empty session creation do not. Legacy dates stay NULL. This reuses the existing authenticated owner-scoped signal; it is activity, not proof of successful LLM execution.
- Resolve allowed team ids with CAN_USE_TEAM_AGENTS using the existing ReBAC lookup, including personal space. Suggestions are limited to default teams plus personal; recent usable instances may come from any permitted team.
- Aggregate max(last_activity_at) per caller/instance across non-deleted conversations, join enabled non-suspended instances and apply permissions before LIMIT 5. Alphabetical names and ids break ties. Query returns at most five records, no per-team runtime catalog calls or N+1.
- GET /me/home-agents returns existing instance summaries and history_unavailable. On a SQL history-query error, retry a bounded suggestions-only query and report partial failure. Other failures remain explicit errors.
- Frontend consumes the generated hook. Existing KPI presets remain for analytics consumers.

## Risks / Trade-offs
- Older conversations lose recent priority until new activity: unknown dates are preserved rather than fabricated.
- The browser activity PATCH is best-effort today: reuse its existing semantics, without claiming server-verified completed turns. Multi-pod correctness comes from SQL, not process state.
- Access revocation is checked per request; running an agent still uses its existing execution authorization.

## Migration Plan
Add the nullable column and index before serving new queries through the existing Alembic upgrade. No backfill or new configuration. Roll back application code first; old code ignores the new column.
