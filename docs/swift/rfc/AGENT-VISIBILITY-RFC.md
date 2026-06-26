# RFC — Agent visibility in the template catalog

**Status:** Draft for team review
**Author:** Dimitri Tombroff
**Date:** 2026-06-25
**Area:** `fred-runtime`, `control-plane-backend`, `frontend`, `fred-agents`
**Touches:** `RUNTIME-EXECUTION-CONTRACT.md` (`/agents/templates`), `CONTROL-PLANE-PRODUCT-CONTRACT.md` (`/teams/{id}/agent-templates`)

---

## 1. Problem

Internal agents — the self-test agent (VALID-02), and sub-agents only invoked via
`context.invoke_agent()` — should not appear in the "create agent" catalog, yet must
remain registered and executable. Today there is no way to hide an agent from that
catalog while keeping it enrollable.

## 2. The field already exists — reuse it

`AgentDefinition.public: bool = True` already encodes exactly this intent
(`libs/fred-sdk/fred_sdk/contracts/models.py`):

> "Public agents (the default) appear in /v1/models and /agents listings… Set to
> False for sub-agents that are only invoked internally… They must still be
> registered so the runtime can find and execute them, but they should not be
> presented as top-level chat models."

Per the prime directive (extend, do not duplicate), we **reuse `public`** rather than
add a parallel `visibility` field. The only gap is consistency: `/v1/models` honors
`public` (`openai_compat_router.py`), but the runtime **`/agents/templates`** endpoint
— which feeds the control-plane catalog and the "create agent" UI — does **not**. So a
non-public agent is correctly hidden from OpenAI-compat clients but still leaks into the
template picker.

## 3. Change

1. **fred-runtime `/agents/templates`** (`agent_app.py`): exclude `public=False`
   definitions by default; accept `?include_non_public=true` to include them.
2. **control-plane** (`product/service.py`): `list_agent_templates` and the
   `GET /teams/{team_id}/agent-templates` route accept an `include_non_public` flag and
   forward it to the runtime fetch. Default `false`.
3. **frontend**: the "create agent" catalog calls the endpoint normally (internal agents
   stay hidden); only the self-test harness's `provisionAgentInstance` passes
   `include_non_public=true` to discover + enroll its agent. Regenerate the OpenAPI types.
4. **fred-agents**: the self-test agent sets `public = False`.

No new contract field — only a new optional, default-false query parameter on two
read-only catalog endpoints.

### 3.1 Authorization boundary — non-public means admin-only to execute

Enforcement is layered: **control-plane is the policy layer; the runtime is the execution
layer.** Both must honor the boundary.

**Control-plane (policy).** Each path resolves the target with the caller's privilege
(`include_non_public = "admin" in user.roles`), so a non-admin who guesses a hidden id
gets "not found":

- **Listing** — `GET /teams/{id}/agent-templates` honors `include_non_public` only for admins.
- **Enrollment** — `enroll_agent_instance` resolves with caller privilege → non-admin 404.
- **Direct-prepare** — `prepare_runtime_agent_execution` (the evaluation `agent_id` route)
  validates visibility before issuing a grant → non-admin 404.

**Runtime (execution).** The bare-`agent_id` execute path takes *no grant*, so it is the
real execution boundary. It now **refuses non-public agents** (`_resolve_agent_instance`
→ 404), so a non-public agent can only run through a managed instance — whose enrollment is
admin-gated above. Sub-agents invoked in-process via `context.invoke_agent()` are
unaffected (not the HTTP path).

Tests: `test_enrolling_internal_template_is_admin_only`,
`test_direct_execution_of_internal_agent_is_admin_only` (control-plane),
`test_non_public_agent_is_hidden_and_not_directly_executable` (runtime).

**Known limitation — runtime catalog enumeration.** The runtime `/agents/templates`
endpoint has no per-call auth; like every runtime endpoint it trusts the deployment's
control-plane-fronted reachability boundary (secure-reachability, BACKLOG Phase 3c). With
`include_non_public=true` a caller who can reach the runtime *directly* can enumerate
internal agent IDs. This discloses IDs only — with the execution guard above, a leaked id
is neither executable nor enrollable without admin. Hardening direct runtime reachability
is owned by the runtime-reachability work, not this RFC.

**Eval-worker note:** the evaluation worker calls the direct-prepare route over M2M. Public
agents remain executable by it (the normal case); only *non-public* agents now require an
admin-roled principal. No eval flow targets a non-public agent today.

## 4. Backward compatibility

- `public` defaults to `True`; the new query param defaults to `false`. Existing
  callers and agents are unaffected.
- **One intended behavior change:** agents that already set `public=False` (internal
  sub-agents) stop appearing in the "create agent" catalog. That is the documented
  purpose of the flag — `/agents/templates` simply wasn't honoring it. Existing enrolled
  instances keep working (only new enrollment from the catalog is affected); the escape
  hatch (`include_non_public=true`) still lists them for tooling.

## 5. Alternatives considered

- **A new `visibility: public|internal` enum.** Rejected — duplicates the existing
  `public` boolean. The enum's only advantage (future values like `experimental`) is not
  needed now and can be introduced later without breaking this change.
- **Hide via a reserved tag + frontend filter.** Rejected — UI-only, not enforced
  server-side, and trivially bypassed.

## 6. Tracking

Part of VALID-02 (the self-test harness needs its agent hidden). No separate ID; recorded
in `docs/swift/backlog/BACKLOG.md §3b.7` under the VALID-02 items.
