## Context

See `proposal.md` — Why, for the product motivation (GitHub #2568). This section only
grounds the approach in the current, as-built code, split into the four concerns this
change touches. All file:line references are current as of `swift` tip
(`7018f3f2fe752c90ac6fd19027eecb1a070e08a3`) and were re-verified for this design, not
carried over unchecked from the earlier exploration pass — two points in that pass are
corrected below where the code says something more precise.

### 1. Work-objective retention and completion

The production ReAct loop is stock LangChain `create_agent`
(`libs/fred-runtime/fred_runtime/react/react_tool_loop.py:151-157`); continue/call-tool/
final-answer decisions are LangChain's own, not Fred code. Fred wraps it in a fixed
middleware frame (`frame.py:75-99`): `CheckpointHygieneMiddleware`, `DynamicPromptMiddleware`,
`TracingKpiMiddleware`, `ToolObservabilityMiddleware`, `FredHitlMiddleware`. No
external plan/TODO artifact exists for ReAct outside the model's own conversation
context — grepped clean of any first-party `write_todos`/scratchpad wiring; the only
durable trace-shaped record is `ThoughtRecord`
(`libs/fred-sdk/fred_sdk/contracts/runtime.py:185-199`), explicitly for evaluation/replay,
not an executable plan.

The concrete loss mechanism: `CheckpointHygieneMiddleware.awrap_model_call`
(`libs/fred-runtime/fred_runtime/react/middleware/checkpoint_hygiene.py:115-188`) enforces
a 200,000-character history budget (`_V2_MAX_HISTORY_CHARS`,
`react_tool_loop.py:83`) via `trim_to_char_budget`
(`libs/fred-runtime/fred_runtime/support/tool_loop.py:276-303`), which drops messages from
the **front** of the list once the budget is exceeded — and a separate message-count trim
(`trim_to_human_boundary`, `tool_loop.py:188-206`, cap 500) does the same. The original
multi-step instruction is the first user message in the thread, so it is exactly what gets
dropped first in a long session with large tool outputs. Nothing today checks a "final"
turn against the original request's step list.

### 2. Tool-error classification

Authored capability tools already classify errors correctly: they self-catch and return a
typed result with `is_error=True` (e.g. `document_summarize`'s
`_document_tool_failure`, `document_summarize/capability.py:114-155`), and
`react_runtime.py`'s round-level suppression logic
(`libs/fred-runtime/fred_runtime/react/react_runtime.py:574-596`, §8.42 of
`RUNTIME-EXECUTION-CONTRACT.md`) reads that signal for every tool that follows this
convention — but only that signal, which is the gap below.

`react_runtime.py:567-574` derives `RuntimeEvent.is_error` **only** from
`artifact.is_error`, via `artifact = _normalize_tool_artifact(message.artifact)`. When the
underlying call raised and produced no Fred artifact (`message.artifact is None`), this
reads `is_error=False` regardless of `message.status` (confirmed: zero references to
`.status` anywhere under `libs/fred-runtime/fred_runtime/react/react_runtime.py`). This is
**not specific to the two built-in Workspace tools** (`artifacts.publish_text`,
`resources.fetch_text`, `react_tool_resolution.py:374-429`, whose closures had no
`try`/`except` and let a `workspace_fs` failure propagate uncaught through
`react_tool_binding.py:327-338` into LangGraph's default `ToolNode`
(`langgraph/prebuilt/tool_node.py:998-1012`), which produces exactly
`ToolMessage(status="error", artifact=None)`). The same gap is confirmed in
`_resolve_transport_declared_tool` (`react_tool_resolution.py:491-534` — the shared path
for registered/MCP/generic declared tools), which has no `try`/`except` around
`tool_invoker.invoke(...)` at all, and would hit the identical `artifact=None` shape on any
call failure.

**`ToolObservabilityMiddleware.awrap_tool_call` already classifies this correctly** and has
since #2073 (`middleware/tool_observability.py:301-328`):

```python
status_is_error = isinstance(result, ToolMessage) and result.status == "error"
failed = status_is_error or artifact_is_error
```

This is a true OR over two independent signals, not a fallback that only checks `status`
when no artifact exists — a tool can return a normal-looking `ToolMessage` carrying an
artifact whose `is_error` is `False` while `status` is still `"error"` (or vice versa), and
either one alone must be enough to classify the call as failed. `react_runtime.py`'s own
classification must read the same way, not invent a narrower rule.

**Correction to the earlier exploration pass:** the original finding correctly identified
the bug's *symptom* (a Workspace write/read failure reported as `is_error=False`) but
under-scoped its *cause* — it is not "these two tools forgot to self-catch," it is "the
shared classification point only trusts one of the two signals `ToolMessage` can carry."
Fixing the classification point removes the gap for every current and future tool source
at once, rather than requiring each one to independently remember to self-catch.

### 3. Scoped Workspace persistence

`WorkspaceFsPort` (`libs/fred-sdk/fred_sdk/contracts/runtime.py:487-558`) today declares
**nine** abstract methods including `bind` — eight of them data operations: `read_bytes`,
`read_text`, `read_user_bytes`, `read_team_bytes`, `write` (→ `PublishedArtifact`, line
539), `ls`, `delete` (line 547), `link_for` (→ `PublishedArtifact`, line 551).
**Correction to the earlier exploration pass:** the target four-operation Workspace
HTTP/domain contract (`list`/`read`/`write`/`link`, frozen by
`docs/swift/rfc/AGENT-FILESYSTEM-HARDENING-RFC.md` §9.2, tracked by issue #2498) is a
statement about the **remote Workspace API surface**, not a mandate to mechanically prune
the SDK's Python interface to exactly four methods — several of the current nine (`bind`,
`read_user_bytes`, `read_team_bytes`) may still be legitimate local/adapter-side operations
even after #2498 ships. Retained-consumer inventory for each method is #2498's own first
step (per its issue body), not something this change re-derives or pre-judges.

Its adapter, `FredWorkspaceFs`
(`libs/fred-runtime/fred_runtime/integrations/v2_runtime/adapters.py:1976-2189`), still
authenticates writes with the human bearer token
(`_workspace_access_token()`, lines 2247-2264) and still builds physical prefixes
client-side (`_resolve`/`_resolve_owned`/`_agent_root`, lines 2036-2119) — precisely what
#2498's M2M-hardened vertical slice replaces. **This design does not re-specify #2498.**
It is consumed here as a frozen external dependency: #2498 validates all four operations
(`list`, `read`, `write`, `link`) fail-closed against a verified
`(team_id, agent_instance_id, user_id, session_id)` binding, authenticated by the runtime's
own service-principal identity — **correction to the earlier exploration pass:** this
design does not preselect `KeycloakUser` as the type that carries that service-principal
identity; #2498's own implementation must use whichever narrowest correct
service-principal/auth dependency is appropriate, and must not model a service account as
a human user. This change's persistence-bearing slice (PR B, see `tasks.md`) is blocked on
#2498 landing and does not implement any part of it.

### 4. User artifact publication and history

The already-correct pattern: `ctx.write`/`ctx.link` (`fred_sdk/authoring/api.py:431-472,
602-620`) produce a `PublishedArtifact`
(`fred_sdk/contracts/context.py:868-893`) converted via `.to_link_part()` into a `LinkPart`
(`context.py:63`). This flows through `ToolResultRuntimeEvent`/`FinalRuntimeEvent`
`ui_parts` (`react_stream_adapter.py:316-383` merge logic, `react_runtime.py:565-628`),
is persisted on the assistant history row since issue #2462
(`agent_app.py:2482-2523`, `ChatMetadata.ui_parts`), and is rendered on reload by
`traceUtils.ts:261-271` (`uiPartsOf`) → `builtinPartRenderers.tsx:25-26` →
`ArtifactLinkChip.tsx`. `ppt_filler` follows this pattern correctly and self-catches upload
failures (`fill.py:846-853` → `is_error=True`).

Three representations coexist for capability-produced content: the `PublishedArtifact`/
`LinkPart` path above (ppt_filler, the built-in Workspace tools), `writable_document`'s own
Postgres-table-backed store and router (no `WorkspaceFsPort` reference in its package), and
`html_artifact`'s inline-text `UiPart` (no file, no storage, keyed by a fresh `uuid4`).
**Correction to the earlier exploration pass:** `writable_document` and `html_artifact` are
not duplicate downloadable-file stores by virtue of existing alongside `PublishedArtifact`/
`LinkPart` — they represent genuinely different product shapes (a persistently editable
document with its own lifecycle; inline rendered content that is never a downloadable
file). Only a capability that claims to produce a **persisted, downloadable file** is in
scope for convergence onto `PublishedArtifact`/`LinkPart`; this change does not fold
`writable_document` or `html_artifact` into that path, and does not ask either to change.

Two additional risks the exploration pass found, kept here as context (not fixed by this
change, since they are #2498's/the Workspace adapter's territory, not the error-classification
fix's): `KfWorkspaceClient._upload_blob` accepts silent defaults (`size=0`,
`download_url=None`) on a 200 response missing expected fields
(`kf_workspace_client.py:260-267`) before `FredWorkspaceFs.write` reports success
(`adapters.py:2153-2160`); and a plain `write()`'s href is an unsigned, session-authenticated
`/fs/download/{path}` (`mcp_fs_controller.py:213-217,87-92`), distinct from `link_for`'s
600-second HMAC-token route (`mcp_fs_controller.py:256-260`) — both are legacy-`/fs`-surface
concerns #2328/#2498 own, not this change.

## Goals / Non-Goals

**Goals:**
- Fix the one confirmed correctness bug (tool-error classification for the two built-in
  Workspace tools) with the smallest change that keeps one canonical error-classification
  boundary.
- Freeze the externally observable work-completion contract (`specs/agent-work-completion`)
  against the current ReAct runtime, so a later persistence-bearing slice (PR B) has a fixed
  target instead of a moving one.
- Name canonical owners for each of the four concerns above so no PR under this change
  creates a second owner for any of them.

**Non-Goals:**
- Re-specifying or partially implementing #2498's Workspace M2M hardening, or picking
  which of `WorkspaceFsPort`'s nine methods survive — that is #2498's own scoped work.
- Redesigning HITL (`FredHitlMiddleware`, the claim table) — retained as-is, per the closed
  product decision.
- Converging `writable_document` or `html_artifact` onto `PublishedArtifact`/`LinkPart`.
- Any Deep Agents (`CompositeBackend`/`FredWorkspaceBackend`) implementation — a later,
  optional slice gated on ReAct + Workspace being proven first.
- Any sub-agent (`run_subagent`/#2529) workspace-binding fix — that code does not exist in
  this tree today (only an unmerged POC branch) and is out of scope until separately merged.

## Decisions

**D1 — Error-classification boundary: `react_runtime.py`'s `is_error` derivation becomes a
true OR of both signals `ToolMessage` can carry, mirroring `ToolObservabilityMiddleware`'s
already-correct rule — not a per-tool catch.**

The original pass compared two alternatives — (a) normalize every built-in exception into a
typed error result by wrapping the two Workspace closures in a catch-and-return, or (b) make
the ReAct event adapter also honor `ToolMessage.status == "error"` — and chose (a), reasoning
that only two tools needed it and a second signal source would need reconciling everywhere.
That reasoning is invalidated by what implementing (a) actually found: the same gap exists in
`_resolve_transport_declared_tool` (registered/MCP/generic declared tools), and a second,
independently-shipped implementation of exactly the "reconcile both signals" rule this design
worried about already exists and is already correct (`tool_observability.py:301-328`). The
choice is revised to **(b), implemented as a true OR**:

```python
status_is_error = message.status == "error"
artifact_is_error = artifact is not None and artifact.is_error
is_error = status_is_error or artifact_is_error
```

**Not** a fallback ternary (`artifact.is_error if artifact is not None else message.status ==
"error"`) — that form only reads `status` when `artifact is None`, so a tool that returns a
normal `ToolMessage` carrying an artifact whose `is_error` is `False` while `status` is still
`"error"` (a real, distinct shape a tool can produce) would still be misclassified as
success. Either signal being true must be sufficient, exactly as `tool_observability.py`
already implements it.

**Chosen because:** it fixes the built-in Workspace tools, `_resolve_transport_declared_tool`,
and any future tool source at one shared boundary, with no per-source `try`/`except`; it
mirrors an already-shipped, already-correct implementation of the identical rule rather than
inventing a new one; and it is net less code than the per-tool approach (the two Workspace
closures' `try`/`except` and the `_workspace_tool_failure` helper are removed as redundant,
not kept alongside the generic fix). `ToolInvocationResult` remains the richer typed result
whenever a tool provides one (sources, `ui_parts`, structured blocks) — this only changes
what happens when a tool call fails without producing one.

`_resolve_transport_declared_tool` is deliberately **not** touched — no source-specific
`try`/`except` is added there. The generic classification fix covers it without any
resolver-level change, which is itself evidence the shared-boundary fix is the right depth.

**D2 — Freeze current history-trimming behavior before touching it.** PR B (blocked on
#2498) must add a regression test locking `CheckpointHygieneMiddleware`'s current front-drop
behavior *before* changing it, so the fix for objective retention is provably a behavior
change against a known baseline, not an incidental side effect.

**D3 — Treat #2498 as an opaque, versioned dependency, not a design input to restate.**
This design references #2498's frozen contract (`list`/`read`/`write`/`link`, fail-closed,
service-principal-authenticated) by name and does not restate its internal validation
design; `tasks.md` represents it as a blocking external gate.

**D4 — Revised after a blocking review finding: untyped tool failures are handled at a
trust boundary, not by parsing wrapper strings, and the trusted case never reuses
`message.content` either.** The first implementation pass's `_clean_tool_error_text()`
(stripping either Fred's `"Tool error:\n"` prefix or LangGraph's default `"Error:
{repr(exc)}\n Please fix your mistakes."` template) does not do what its own goal
required: for LangGraph's actual default content, stripping the prefix/suffix around
`repr(exc)` still returns `repr(exc)` itself — e.g. `ValueError('secret')` for a tool that
raised with a secret in its message. Independently, `ToolResultRuntimeEvent.content`
(`react_runtime.py:638`) was never routed through `_clean_tool_error_text()` at all — it
always carries the fully raw `message.content`, regardless of what the final answer
shows. Both are corrected by classifying trust rather than parsing content, and by
deriving the trusted case's text from the artifact itself rather than from
`message.content`:

- A `ToolMessage` whose failure signal includes a typed artifact with `is_error=True` is
  Fred's own explicit, user-facing error contract (the `artifact_is_error` signal from
  Decision D1). Its user-facing text is derived by calling the canonical
  `render_tool_result(artifact)` (`react_tool_rendering.py:42`) directly on the
  already-normalized `ToolInvocationResult`, then removing only Fred's own `"Tool
  error:\n"` presentation prefix where present — **not** by reusing `message.content`.
  `message.content` is not a reliable proxy for the artifact's rendered form:
  `_resolve_runtime_provider_tool` (`react_tool_resolution.py:493-534`) can return an
  arbitrary provider-supplied `rendered_content` string (`stringify_tool_output(raw_result[0])`,
  lines 530-534) as the `ToolMessage` content while still attaching a normalized,
  correctly-classified artifact — so `message.content` and `render_tool_result(artifact)`
  are two independently-produced values that happen to usually agree, not one value.
  Trusting `message.content` here would silently reopen the same class of gap this
  decision closes, the moment a provider tool's raw content diverges from its own
  artifact's rendering.
- A `ToolMessage` whose failure signal is `status == "error"` **without** such a typed
  `is_error=True` artifact (`artifact is None`, or a present artifact with
  `is_error=False`) is an untrusted representation of an uncaught exception — LangGraph's
  default `ToolNode` template today, but the boundary does not depend on recognizing that
  specific shape. `message.content` is not read, parsed, or inspected at all for this
  case — not even to check its shape. It collapses unconditionally to one bounded,
  generic user-facing message (e.g. "This step failed unexpectedly and could not be
  completed."; exact copy is an implementation-time detail, not a design constraint). No
  `repr(exc)`, no LLM-directed instruction, no path, URL, token, or other raw text is ever
  read from it.
- The same rendering decision feeds both `ToolResultRuntimeEvent.content` and (via
  `last_tool_error`) `FinalRuntimeEvent.content` — one function produces the user-facing
  text for a failed call from the normalized artifact (or the generic message), not two
  independently-maintained call sites and not `message.content`.
- An unrecognized or future upstream wrapper shape is not a third case: anything that is
  not the typed `is_error=True` artifact contract falls to the generic message by
  construction, regardless of what `message.content` happens to contain. Passing an
  unrecognized shape through unchanged (the first pass's behavior) is not a safe default —
  it is exactly how a real secret would leak in the scenario above.

`_clean_tool_error_text()`'s LangGraph-template-parsing branch is removed as
unnecessary — there is no longer a second wrapper shape to recognize and strip, only one
trusted shape (rendered fresh from the normalized artifact) and one untrusted catch-all
that never inspects `message.content`. Decision D1's true-OR classification expression
and the `react_tool_binding.py` span fix are unchanged by this revision.

## Risks / Trade-offs

- **[Risk]** A future tool source could still bypass classification entirely by never
  returning a `ToolMessage` at all (e.g. a `Command`-returning tool, already excluded by
  `tool_observability.py`'s own `else`-branch structure since a `Command` has no `.status`
  and is treated as success by design — LangGraph already redirected graph state, which is
  not a failure signal).
  **[Mitigation]** This is existing, accepted behavior for `Command`-returning tools
  (unrelated to this fix); the regression tests in `tasks.md` 1.3-1.4 cover the
  `ToolMessage`-with-no-artifact and `ToolMessage`-with-a-non-erroring-artifact-but-erroring-status
  shapes specifically, which is the actual gap this change closes.
- **[Risk]** PR B is blocked on #2498, whose timeline this change does not control.
  **[Mitigation]** PR A (the error-classification fix) and the `fred-corpus` specification
  are both independent of #2498 and can proceed immediately; PR B is explicitly gated in
  `tasks.md` rather than silently assumed to be next.
- **[Risk]** The reliability-measurement requirement (bounded runs, stated success rate) has
  no existing harness in this repository to execute it against.
  **[Mitigation]** The spec states the requirement in reusable, testable terms; the actual
  campaign execution is deferred to the `fred-corpus`/evaluator integration named in
  `tasks.md`, consistent with "reuse the existing evaluator path, do not build a second
  campaign runner in Fred."
- **[Risk]** Collapsing every untyped tool failure to one generic message removes the
  specific exception text a developer might have used to debug the failure from the
  user-facing chat.
  **[Mitigation]** That detail was never meant to reach the user in the first place.
  `ToolObservabilityMiddleware` already logs the full exception server-side via
  `logger.exception` (`tool_observability.py:290-292`) on every raised failure, which is
  the intended place to diagnose an uncaught exception. Spans, audit events
  (`emit_audit_log`), and KPI dimensions retain only a bounded `error_code`/`exception_type`
  (the exception's class name, never its message or arguments) — per the existing
  observability contract, not the full exception text.

## Migration Plan

No data migration. PR A is a pure behavior fix inside existing tool-resolution code, with
no public contract change (confirmed: no `WorkspaceFsPort`, OpenAPI, or `RuntimeEvent`
shape change). PR B, once unblocked by #2498, changes only internal middleware behavior
(history retention) and consumes #2498's already-migrated Workspace surface; it introduces
no new public API of its own. Rollback for either PR is a plain revert.

## Open Questions

- The exact stated minimum success rate and run count for the "bounded reliability across
  repeated runs" requirement (spec: `agent-work-completion`) is left as a parameter for the
  `fred-corpus` acceptance run to fix, once a baseline is recorded (`tasks.md`, fred-corpus
  slice) — this does not change the spec's shape or PR boundaries, only the numeric bar.
- ~~Found during PR A's implementation, not resolved here: `_resolve_transport_declared_tool`
  has the same root gap...~~ **Resolved.** The revised Decision D1 fixes this generically at
  `react_runtime.py`'s classification point — `_resolve_transport_declared_tool` needs no
  code of its own, and no follow-up decision is required.
