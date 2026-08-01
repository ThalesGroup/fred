---
title: Security & authorization
order: 20
description: OIDC identity, per-request pod-side ReBAC authorization, policy-first governance.
icon: shield
---

# Security & authorization

The security model rests on a clean separation: `control-plane` **resolves**
execution but **issues no capability**; each agent pod **authenticates and
authorizes** the requests it receives itself.

## Identity

The user authenticates via **OIDC (`Keycloak`)**. The frontend holds the user's
**JWT** and presents it as `Authorization: Bearer` on every call — to
`control-plane`, and then directly to the agent pod.

## No ExecutionGrant

This is the defining point of the current model (decision RUNTIME-07 rev. 2,
June 2026):

> `control-plane` **issues no authorization token**, signed or unsigned. There
> is **no `ExecutionGrant` type**, no capability. `prepare-execution` resolves
> only _where_ the agent runs (the URLs) and the session context.

The browser therefore calls the pod with the **user's own Keycloak JWT**, not a
derived token: `control-plane` never mints a credential the pod would have to
trust.

## Pod-side, per-request authorization

On every request, the pod runs (`_authorize_and_resolve` in `agent_app`):

1. **Identity from the token, never the body** — `user_id` is stamped from the
   validated JWT; any body-supplied `access_token` / `refresh_token` is
   neutralized.
2. **`Keycloak` JWT validation** — strict `iss`/`aud` under the `c3` profile.
3. **Session ownership** — an existing `session_id` must belong to the caller.
4. **`team` scope authorization**, by case:
   - **collaborative team** → **ReBAC `OpenFGA`** `CAN_USE_TEAM_AGENTS` check on
     `runtime_context.team_id`;
   - **personal space** (`personal-<uid>`) → **intrinsic ownership** by exact
     identity comparison, **never** via `OpenFGA`;
   - **service-agent** (the evaluation worker, `service_agent` role) → a
     dedicated, team-scoped rule that doesn't consult `OpenFGA`.

The model is **fail-closed**: a missing `team_id` returns `403`.

> **Per-tool-call re-verification.** `team` authorization isn't checked only at
> turn start: it is **re-verified on every tool call** (least privilege), so a
> membership revoked mid-turn isn't trusted through the end of the turn.

## Policy-first governance

Execution decisions — model choice, allowed tools/MCP, prompts, agent, data
scope — are resolved from **policies**, not hardcoded. All execution is
**team-scoped** and authorized.

## Standalone mode (no authentication)

For a developer workstation or an **airgapped** deployment,
`KEYCLOAK_ENABLED=false` runs the pod **without authentication**: a mock user
(`uid="admin"`) is injected, and `team_id` defaults to `"personal"`.
Checkpoints, history and KPI labels then all carry `team_id="personal"`, keeping
metrics comparable across restarts.
