# Swift comments

<!--
This file is an aggregation of all comment, questions... From fmuller on the new Swift version of Fred.

INSTRUCTION:
Each time, reference the code with links (to the right line) and put in code blocks small parts of the mentionned code
 -->


# Security

## [Bug] Session listing ignores user ownership — all team sessions visible to everyone

[`list_by_team`](apps/control-plane-backend/control_plane_backend/sessions/store.py#L118) filters only on `team_id`, so every member sees every other member's sessions (including personal spaces). `user_id` is stored but never used as a filter. Fix: add `list_by_team_and_user`, add a compound index on `(team_id, user_id)` ([currently un-indexed](apps/control-plane-backend/control_plane_backend/models/session_metadata_models.py#L26)), and thread the user id through [`list_sessions`](apps/control-plane-backend/control_plane_backend/product/service.py#L1556).


## [Bug] Runtime session endpoints are IDOR in prod — no ownership check

[`GET /agents/sessions`](libs/fred-runtime/fred_runtime/app/agent_app.py#L2079) and [`GET /agents/sessions/{session_id}/messages`](libs/fred-runtime/fred_runtime/app/agent_app.py#L2104) use `dependencies=_auth_deps`, which only verifies that a valid JWT is present — the authenticated user is never injected into the handler:

```python
_auth_deps = [Depends(get_current_user)] if security_enabled else []

@router.get("/sessions", dependencies=_auth_deps)
async def list_sessions(user_id: str) -> list[str]:  # user_id comes from query param, never verified
    return await history_store.list_sessions(user_id=user_id)
```

Any authenticated user can pass an arbitrary `user_id` and enumerate another user's sessions, then read their full conversation history via the messages endpoint. These endpoints are intended for CLI/dev tooling only (used by [`repl.py`](libs/fred-runtime/fred_runtime/cli/repl.py#L593) via [`pod_client.py`](libs/fred-runtime/fred_runtime/cli/pod_client.py#L228)), but they are always mounted in prod with no ownership guard.

Fix options (pick one):
1. Inject the current user and assert `current_user.sub == user_id` (for list) / that the session belongs to the caller (for messages).
2. Restrict these endpoints to M2M tokens only, since their only legitimate caller is the CLI.


# Architecture  /Code

## [Architecture] `SessionHistoryRow` is the only table not managed by Alembic

[`PostgresHistoryStore`](libs/fred-core/fred_core/history/postgres_history_store.py) manages its own DDL entirely outside of Alembic, making `session_history` the **only table in the codebase not covered by the standard migration pipeline**.

It uses two private methods for this: [`_ensure_tables`](libs/fred-core/fred_core/history/postgres_history_store.py#L162) (runs `CREATE TABLE IF NOT EXISTS` via an advisory lock) and [`_migrate_columns`](libs/fred-core/fred_core/history/postgres_history_store.py#L188) (hand-rolled `ALTER TABLE … ADD COLUMN IF NOT EXISTS` for each column added after initial creation, since `create_all` is a no-op on an existing table).

This should not stay as-is:
- Schema changes are invisible to `alembic history` and any tooling that depends on revision ordering.
- `_migrate_columns` must be manually kept in sync with the SQLAlchemy model — any column added to `SessionHistoryRow` and forgotten there silently breaks existing databases.
- Inconsistent ops story: every other table migrates with `alembic upgrade head`, this one does not.

Fix: move `session_history` into the standard Alembic track, drop `_ensure_tables` and `_migrate_columns`, and generate proper revisions for each column currently listed in `_migrate_columns`.

## [Typing] `checkpointer` and `history_store` typed as `Any` in `RuntimeContext`

[`RuntimeContext`](libs/fred-runtime/fred_runtime/runtime_context.py#L129-L130) declares two properties with `Any` type to avoid a circular import:

```python
checkpointer: Any | None = None  # FredSqlCheckpointer — avoids circular import
history_store: Any | None = None  # PostgresHistoryStore — avoids circular import
```

The comments name the real types (`FredSqlCheckpointer`, `PostgresHistoryStore`) but they can't be used directly. This silently drops type-safety for two central runtime objects. Worth resolving so callers benefit from proper type inference.



## [DRY] Two endpoints list sessions — not DRY

Session listing exists in two backends:

- **Control plane** [`GET /teams/{team_id}/sessions`](apps/control-plane-backend/control_plane_backend/product/api.py#L610) — team-scoped, returns rich `SessionListItem` metadata, used by the UI sidebar.
- **Runtime** [`GET /agents/sessions?user_id=`](libs/fred-runtime/fred_runtime/app/agent_app.py#L2079) — user-scoped, returns raw `list[str]` session IDs, used only by the CLI REPL ([`repl.py:593`](libs/fred-runtime/fred_runtime/cli/repl.py#L593)).

Both ultimately query the same underlying data. The runtime endpoint predates the control plane taking over session metadata and was never removed. The CLI REPL could call the control plane instead, allowing `BaseHistoryStore.list_sessions` and the runtime endpoint to be deleted.

## `prepare-execution` URLs bypass RTK Query — no caching, no drift detection

[`ExecutionPreparation`](apps/control-plane-backend/control_plane_backend/product/schemas.py#L150) returns three runtime URLs that the frontend resolves at call time:

```python
execute_url: str          # non-streaming execution
execute_stream_url: str   # SSE streaming
messages_url_template: str  # history fetch, {session_id} expanded client-side
```

All three are called with raw `fetch()` (see [`useSessionHistory.ts:49`](frontend/src/rework/components/pages/ManagedChatPage/useSessionHistory.ts#L49) for messages), not through RTK Query. Two consequences:

1. **No caching** — no deduplication, no invalidation tags, every call hits the runtime pod unconditionally.
2. **No API drift detection** — the generated `runtimeOpenApi.ts` is checked against the OpenAPI spec in CI. These `fetch` calls are not. If the runtime endpoint signature changes, CI won't catch the mismatch.

This is an intentional tradeoff: the URLs are dynamic (pod-specific, ingress-relative), so they can't be baked into a static RTK Query endpoint. Worth investigating whether a wrapper pattern (e.g. a custom RTK Query `baseQuery` that reads the URL from `ExecutionPreparation` state) could recover caching and type-safety without giving up the dynamic dispatch.

## ReAct agents: two system prompts, one winner

A ReAct agent carries two things that look like a system prompt:

- [`system_prompt_template`](apps/fred-agents/fred_agents/general_assistant.py#L91) — author-defined default, baked into the class
- [`FieldSpec(key="prompts.system")`](apps/fred-agents/fred_agents/general_assistant.py#L92) — admin-editable override, filled via the control-plane UI

At execution time, [`_apply_runtime_tuning`](libs/fred-runtime/fred_runtime/app/agent_app.py#L851) does a **full replacement** — no merging:

```python
system_prompt = tuning.values.get("prompts.system")
if isinstance(system_prompt, str) and system_prompt.strip():
    update["system_prompt_template"] = system_prompt  # admin text wins entirely
```

Only one reaches the LLM: the admin override when set, the author default otherwise.

### Questions

**Q1 — Why not use [`FieldSpec.default`](libs/fred-sdk/fred_sdk/contracts/models.py#L101) to carry the author default?**

The `FieldSpec` model has a `default` field. Setting `default=_SYSTEM_PROMPT` would pre-fill the textarea in the UI and make `_apply_runtime_tuning` treat `prompts.system` like any other tuning value — no special-case branch needed.

**Q2 — Why does `system_prompt_template` need to be a first-class property at all?**

The special-case `if isinstance(definition, ReActAgentDefinition)` in `_apply_runtime_tuning` looks like a compatibility shim. Is `system_prompt_template` expected to go away once `prompts.system` is the canonical path, or is it intentionally kept as a "compile-time default" separate from the tuning surface?


# UI

## To improve

- Prompt card do not show the description (only weird empty body)

## Bug

- can't scroll while text is generating (making scroll go up and down)

- RAG not working with "Document-grounded RAG expert" agent (hit always return an empty array)



# Configuration

- no up to date instruction to run the project ? (and agent is making lots of error if I ask it how)
- missing `.env.template` for fred-agent (forced to guess needed env variable)
- no `make run-prod` in fred-agent - why not use `scripts/makefiles/python-run.mk` like other backends ?
- `.vscode/fred.code-workspace` not updated
- `.vscode/tasks.json` not updated