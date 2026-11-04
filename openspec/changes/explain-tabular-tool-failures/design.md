## Context

See `proposal.md` and #3458. `ContextAwareTool` creates an empty error artifact outside the curated SQL 400 path. The resolver trusts that artifact and `render_tool_result` returns `Tool error:` without useful text. `genericToolPayload` intentionally suppresses arbitrary content; only recognized results and the curated failed-SQL path have richer drawer views.

The completed `reliable-agent-work-completion` change and runtime contract section 8.74 require untrusted provider detail to remain hidden. The active delegated-execution contract additionally preserves authority-stop semantics. Neither is replaced by this change.

The follow-up investigation distinguishes API campaigns from browser use: all 156 correlated expired-token failures are campaign calls, with matching exchange/correlation/request identifiers. The CLI refreshes within 30 seconds of expiry; the browser requests 120 seconds and checks a 30-second floor immediately before streaming. A long bearer-based turn can still outlive the token already sent to the pod. Historical results and model-input captures also confirm repeated successful SQL calls after earlier identical results were delivered.

## Goals / Non-Goals

**Goals:** repair useful error feedback using existing result content, show the call arguments and recorded error in an explanatory drawer, and make tool instructions more precise without substantial prompt growth.

**Non-Goals:** change credential ownership or lifetime, pass refresh tokens to the pod, add retries or caches, substitute document identifiers, change models, or redesign trace navigation. Repeated-success prevention needs a separately agreed policy for freshness and deliberate repeats.

## Decisions

### 1. Classify at the existing trusted source boundary

In `common/context_aware_tool.py`, create non-empty Fred-owned text blocks for caught failures. Use a small fixed catalog based on a recognized HTTP envelope/status (including both installed HTTP client exception types): invalid arguments, authentication required, unavailable document/scope, overload, timeout and generic service failure. Unknown exceptions use the existing generic message. Each catalog entry includes a short recovery instruction for the model; it must not imply that an inaccessible document exists.

Only `read_query` HTTP 400 retains the existing already-redacted SQL detail. Keep `AuthorityLostError`, cancellation and other run-stop errors propagating. The MCP mount's existing generic authority-refusal behavior remains intact. Do not expose response bodies for other cases or infer permission causes from SQL alias rejection text. Fix the shared renderer's empty-block fallback as a defensive measure.

Reusing typed artifacts and text avoids a new diagnostic event, SDK field, history column or error framework. A frontend-only fix cannot reconstruct causes discarded at this boundary; copying raw exception text would violate the existing contract.

### 2. Extend the existing drawer with a curated failure view

Dispatch failed calls before success-shape parsing in `TraceDetailDrawer`. Show the existing localized action/status, the recorded call arguments and the error preserved by the trusted boundary. The drawer is explanatory: do not add a next-step section, reconnection advice or other recovery instructions. Recovery guidance supplied to the model remains outside this user-facing projection.

For tabular calls, expose only their recorded business parameters: `document_uids`, `dataset_uids`, `sql`, `keyword`, `max_rows`, `max_rows_per_table` and `max_matching_tables` where the named tool supports them. Preserve actual submitted values, including mistyped UIDs, so the user can diagnose the invocation. Do not substitute inferred values or claim that these are the full HTTP wire arguments. Render no-argument discovery honestly. Keep SQL in its existing code view and the recorded identifiers in the argument block; human-readable document names can additionally come from earlier authorized results. Do not expose injected credentials, grants or runtime scope internals. Other tool argument schemas require their existing curated policy, not a blanket raw-arguments fallback.

For generic MCP failures, recognize only the fixed Fred-owned catalog messages and display their diagnostic portion without their recovery hint, ignoring arbitrary appended or malformed content. Preserve the existing curated SQL engine error instead of replacing it with editorial advice. Unknown or historical empty/unrecognized failures get a localized non-empty fallback explaining that no further diagnostic was recorded. Provider content, private URLs and traces remain hidden. Existing supported native-tool detail views retain their own trust rules. This preserves historical safety instead of displaying all failed-result content indiscriminately.

Use existing `ToolResultRuntimeEvent.content` and `ToolResultPart.content`, so live and reloaded conversations share the same parsing. Do not add raw diagnostic strings to trace-row summaries or toast every failed attempt; the row remains a failure and its existing drawer supplies the explanation. Use existing design-system tokens and French/English translations.

### 3. Put concise guidance next to tool arguments

Update the descriptions of `document_uids`, `dataset_uids` and `sql` in the tabular controller/models: UIDs come from authorized discovery, an alias names a SQL table, and SQL uses DuckDB. Do not impose a UUID syntax on opaque UIDs or rename fields. Regenerate Knowledge Flow OpenAPI and its frontend client through existing commands.

Rewrite the whole packaged tabular prompt into a compact workflow, identifiers/types, and result/error handling. Remove repeated requirements while preserving mandatory schema inspection, exact aliases, source boundaries, the CSV/Excel distinction, the catalog-based absence rule, value-search bounds and typed filtering. Keep at most one compact date expression, `date_column + INTERVAL '7 days'`; explain the unsupported SQLite signature and text conversion. Require exact categorical text values. The revised prompt must not exceed the previous word count, and parameter descriptions must not repeat examples.

Add optional `RawSQLResponse.message`, set to "Requête exécutée avec succès : 0 ligne correspondant aux conditions." only when a query succeeds with `rows=[]`. Keep `error=None`, SQL and dataset references intact. This is also visible to the model through MCP's structured result; the frontend renders a localized empty-success message. A returned aggregate row containing zero or null is not a zero-row result. Add the short instruction to reuse a successful result and inspect types/filters before a changed query when emptiness is unexpected. No execution guard, result cache or duplicate-call limit is added.

The seven-execution empty-result example filtered a string month by `2026-10-01`, while the returned categories contained `2026-10-01 00:00:00`. A successful empty rowset is a real response; choosing an incorrect filter is separate from SQL execution failure.

## Risks / Trade-offs

- Historical results cannot recover discarded causes -> show an honest fallback rather than inventing a diagnosis.
- Broader display could expose untrusted content -> per-tool business-argument allowlists, credential redaction, exact fixed-message recognition, the existing SQL-only detail exception, bounded display and adversarial regression cases.
- Concise guidance cannot eliminate model reasoning errors -> validate representative calls and correctness; do not promise a reduction percentage from these synthetic campaigns.
- Multiple tool calls and pods -> this adds no cross-request state or cache. Classification is bounded per result and argument previews share a 20,000-character budget. Keep existing read and connection budgets; the drawer does not add lookups or network calls.

## Migration Plan

Deploy the runtime classifier and frontend together for richer explanations; either side alone remains compatible with the existing string result schema. Add an operator note with impact `none`, explaining that historical empty errors stay generic. Rollback restores earlier rendering without data migration. Before readiness, run focused runtime/frontend/security tests, generated-client checks, root quality checks and the branch audit with independent review.
