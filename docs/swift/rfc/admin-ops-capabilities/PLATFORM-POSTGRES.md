# Capability spec: `platform_postgres` — read-only SQL over the platform database

**Status:** implemented 2026-08-27 (#2458) — still open: §4 result-format A/B evaluation, §7.3 agent-level evaluation
**Author:** fmuller
**Date:** 2026-08-27
**ID:** OPSCAP-01-PG (informal, per CLAUDE.md task-ID convention)
**Parent:** `docs/swift/rfc/ADMIN-OPS-AGENTS-RFC.md` (OPSCAP-01) — §2 packaging, §3 security
model, and §5 template mechanics apply and are not restated here.
**Related:** `docs/swift/capabilities/AUTHORING.md`; `add-fred-capability` Skill.

First capability of the admin-ops family (parent §4 item 1). Proves the whole chain:
package → entry point → admission → grant → enroll → chat, and ships the first
ready-made template.

---

## 1. Decisions at a glance

| Axis | Decision |
| --- | --- |
| Credential tier | **Tier B only** — reuse the pod's `storage.postgres` credentials via a runtime port. No Tier A env override, no DSN config field, zero setup. |
| Table filtering | **None.** The admin team roster is the entire trust boundary: operators grant this capability only to teams whose members already hold direct psql access. |
| Tools | **Two**: `postgres_list_tables` (zero-arg discovery) + `postgres_run_query(sql)`. |
| Config fields | **One**: `statement_timeout_s` (default 15, min 1, max 120). Everything else hard-coded. |
| Read-only enforcement | Server-side, three layers (§3). **No SQL string validator.** |
| Platform access | New generic **`PlatformSqlPort`** in fred-sdk; adapter + pool + enforcement in fred-runtime (§3). |
| Result format | JSON envelope with structure-preserving truncation (§4). A/B format evaluation is an explicit follow-up (§7). |
| HITL | No `HitlSpec`. Read-only + server-enforced ⇒ approval friction buys no security and defeats "chat instead of shelling in". |
| Observability | Metadata-only INFO log; no SQL text in logs; no new Prometheus metric in v1 (§6). |

Shared rules inherited from parent §4: `kind="tool"`, `team_scope` default
(ADMIN_GATED), `tools()` lane only (no `execution_models` restriction — runs on ReAct
and Graph), no router, no owned tables, no chat parts.

Family principle established here (applies to every later spec): **minimal tool
surface — roughly one query tool plus one discovery tool per data source.** Anything a
single query can express (describe-table, EXPLAIN, FK lookup) is *not* a tool.

## 2. Capability surface

- **Capability id:** `platform_postgres` (`platform_` prefix marks the
  platform-introspection family; catalog sorts the family together).
- **Package:** `libs/fred-capability-platform-ops/` (in-tree — closes parent §9.4),
  module `fred_capability_platform_ops`, per-concern subpackage `postgres/`.
  Entry point in the package's `pyproject.toml`:
  `platform_postgres = "fred_capability_platform_ops.postgres.capability:PlatformPostgresCapability"`.
- **Icon:** `database` (present in the frontend `materialIcons` list).
- **i18n:** `capability.platform_postgres.*` keys added to both `en` and `fr`
  `translation.json` in the same change.
- **`ConfigModel`:** one optional field `statement_timeout_s: float` — FieldSpec
  `type=number, default=15, min=1, max=120`, adapter re-clamps server-side. No
  `StoredConfigModel` (defaults to `ConfigModel`), no custom `validate_config` — the
  FieldSpec bounds are the whole validation, and no save-time connectivity probe is
  needed (Tier B credentials are the pod's own, proven at boot).
- **`TurnOptionsModel` / `TeamSettingsModel`:** `EmptyModel`.

### Tools

**`postgres_list_tables()`** — zero arguments. One-call grounding: plain-text lines,
one per table — `schema.table (~rowcount): col type, col type, …` — from a canned
catalog query (`pg_class.reltuples` for free row estimates), excluding `pg_catalog`
and `information_schema`. Runs through the same `execute_read` port as everything
else. Expected size for this database (~60–100 tables) fits the 40 KB cap; if a
deployment outgrows it, normal truncation applies and the model falls back to
catalog queries — degraded, not broken.

**`postgres_run_query(sql: str)`** — exactly one SQL statement (§3 makes >1
impossible). `WITH`/CTEs and `EXPLAIN` (without `ANALYZE`) work; anything multi-step
is two tool calls. Server errors (syntax, undefined column, statement-timeout
cancel) return as `is_error` tool results carrying the server's message so the agent
self-corrects — same pattern as `document_access`'s `DocumentPortCallError`
rendering, via a typed `PlatformSqlPortError`.

Per the hard split, tool signatures carry only LLM arguments; config and the port
come through the `CapabilityContext` closure.

## 3. `PlatformSqlPort` + the fred-runtime adapter

There is no SQL port in `RuntimeServices` today, and the hard split forbids handing
credentials (a DSN is a credential) to capability code — so enforcement cannot live
in the package. New contract in `fred_sdk/contracts/runtime.py`:

```python
class PlatformSqlPort(Protocol):
    async def execute_read(self, sql: str, *, timeout_s: float | None = None) -> SqlQueryResult: ...
```

The protocol is deliberately **generic** — nothing Postgres-, pool-, or
policy-specific in the contract; reusable by any future capability wanting read-only
platform SQL, re-implementable against another backend. All policy lives in the
adapter (fred-runtime, beside the existing engine wiring in `app/context.py`):

- **Dedicated engine/pool** built from `storage.postgres`: pool size 2,
  `max_overflow=0`, one pool per pod replica shared by all agent instances. Never
  the app engine's pool — a heavy analytical query can never starve the
  checkpointer/history hot path.
- **Enforcement stack** (all server-side; rationale below):
  1. **Single statement by construction** — asyncpg's prepared/extended-protocol
     query path; the server's parse step accepts exactly one statement, so
     `"SELECT 1; DELETE …"` is rejected before anything runs. The adapter must
     never use a script/multi-statement execution API.
  2. **Explicit `READ ONLY` transaction** around every execution — the server
     rejects writes regardless of the role's (read-write) grants.
  3. **`default_transaction_read_only = on`** set on every connection at connect
     time — belt-and-suspenders for any future adapter path that forgets layer 2.
- **Row cap**: hard-coded 200 rows; the adapter fetches 201 to set a
  `row_limit_hit` flag. An agent needing more should aggregate — taught by the
  template prompt, not by a config knob.
- **Timeout**: `timeout_s` clamped to [1, 120], applied server-side
  (`SET LOCAL statement_timeout` inside the transaction, or driver-level cancel).

**Why layer 1 is load-bearing (and why there is no SQL string validator):** layers 2
and 3 are transaction/session *state*, and a multi-statement script gets to execute
the very commands that mutate that state — `SET default_transaction_read_only = off;
COMMIT; DELETE …` is legal inside a READ ONLY transaction right up until it isn't.
Single-statement enforcement makes that state unreachable. A Python-side SQL parser
(à la KF tabular's `validate_read_query`) is the only layer that could *wrongly
reject* legitimate queries (CTEs, EXPLAIN, comments), adds maintenance, and per
parent §3.1 is "never the guarantee" — so it is deliberately omitted, not forgotten.

The port being the capability's *only* path to the database turns parent §3.1's
"small auditable executor" from a code-review promise into a structural guarantee.

## 4. Result formatting (capability-side)

`postgres_run_query` returns a JSON envelope; rows as arrays (column names once):

```json
{"columns": ["team", "members"], "rows": [["acme", 12]],
 "row_count": 1, "row_limit_hit": false, "rows_dropped": 0, "truncated_cells": 0}
```

Three hard-coded caps, applied in order so truncation preserves structure:

1. **Rows**: 200 (adapter, above) — `row_limit_hit: true` when more existed.
2. **Per-cell** ~1 000 chars: longer values (checkpoint/tuning JSON blobs, chat
   bodies) are cut in place with `…[truncated, <true length> chars]` — every row
   stays a structurally intact row, and the marker tells the model to re-query
   narrower (`->>` on JSON, explicit columns) instead of reasoning over a fragment.
3. **Total** ~40 KB: final backstop, cut at *row* granularity (drop trailing rows,
   report `rows_dropped`) — never mid-cell.

Per-cell + total (vs a single total cap) is deliberate: with total-only, one giant
first cell eats the budget and drops every other row, or the cut lands mid-cell and
breaks the table shape the model is parsing.

**Format choice is honest, not benchmark-backed:** published table-format benchmarks
put JSON mid-pack (markdown-KV often higher, CSV consistently worst) but test large
clean tables, not blob-laden ≤200-row ops results where CSV/markdown structurally
corrupt row boundaries. JSON is chosen for robustness under messy cells + first-class
truncation metadata. **Follow-up (explicit):** A/B-evaluate result formats (JSON vs
markdown-KV vs others) with the evaluation harness on the target models (Mistral
Small 4 / Medium 3.5, GPT-5). The formatter is one file with no contract or stored
config — swappable freely.

## 5. Ready-made template (`platform_ops`)

Ships **in the same PR** (parent §5/§7): `ReActAgentDefinition` in
`apps/fred-agents/fred_agents/registry.py`, prompt from a markdown file + editable
`FieldSpec(key="prompts.system", type="prompt")`, defaults `["platform_postgres"]`.
Each later capability WP appends itself to this template's default list.

Load-bearing prompt instructions:

1. Read-only operations assistant for this Fred deployment; you cannot modify anything.
2. Ground first: call `postgres_list_tables` before the first query of a session.
3. Aggregate in SQL, don't fetch raw rows — results cap at 200 rows; hitting the cap
   means the query is wrong (`GROUP BY` / `count` / `avg` instead).
4. `…[truncated …]` markers mean a fragment — re-query narrower, never reason over it.
5. On a query error, read the server message and fix the query; don't retry unchanged.

Deliberately absent (2026-08-27): "state which query produced each number" — per-query
attribution already lives in the session history's tool calls; prose citations are noise.

**Ordering dependency:** WP1 (AgentFormModal initializing the selection from
`default_capability_ids`, parent §5) lands first. If it slips, the template still
works with one manual tick — blocking the zero-click experience, not correctness.

## 6. Observability

Adapter emits one metadata-only INFO log per query: duration, row count,
`row_limit_hit`, error class — **never the SQL text**
(`OBSERVABILITY-AND-AUDIT.md` §7 content exclusion; the SQL is already durably
visible as a tool call in session history, with full conversation context — a better
audit surface than logs). No Prometheus metric in v1 (low-volume admin path; a
counter/duration histogram is the natural v2 if traffic appears, wired
Grafana-visible per the checklist). The log fires on the tool path ⇒ the
implementation PR runs `fred-performance-reviewer`.

## 7. Testing

1. **Capability unit tests** (stubbed `PlatformSqlPort`): both tools; truncation
   edges — giant cell, row-cap hit, empty result, server error → `is_error`; missing
   port fails loud; `registry.validate()` boot-invariant test.
2. **Adapter tests** — the executable form of §3's security claims. Real-Postgres
   integration (gated behind `FRED_PG_DSN`, precedent
   `libs/fred-core/fred_core/tests/integration/`) proving rejection of:
   `"SELECT 1; DELETE …"` (multi-statement), a write inside the transaction, and the
   `SET default_transaction_read_only = off; COMMIT; DELETE` escape.
3. **Agent-level evaluation (follow-up, external):** evaluate the `platform_ops`
   agent end-to-end with the Fred evaluator module (separate repo): a
   question/answer dataset of admin Postgres questions ("mean member count per
   team", "sessions created yesterday", …), runnable reproducibly against a
   **seeded fake Fred Postgres database** (prior art: the `seed-synthetic-corpus`
   skill's synthetic local-stack seeding). Also the vehicle for the §4 format A/B.

## 8. Delivery

One issue + one PR (consolidation-phase scope discipline), after WP1:

- fred-sdk: `PlatformSqlPort` + `SqlQueryResult` + `PlatformSqlPortError`.
- fred-runtime: adapter (pool + enforcement), `RuntimeServices.platform_sql` wiring.
- `libs/fred-capability-platform-ops/`: package scaffold + `postgres/` capability.
- fred-agents: `platform_ops` template + prompt file; en/fr i18n keys.
- Docs: capability row per AUTHORING.md; parent RFC §9.4/§9.5 already amended.
- No frozen-contract change expected (additive capability + template).
