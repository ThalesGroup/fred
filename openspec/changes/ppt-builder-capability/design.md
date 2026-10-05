## Context

`ppt_builder` lives beside `ppt_filler` in `libs/capabilities/fred-capability-ppt-filler/` and reuses its bounded python-pptx work (`concurrency.py`), run-merging traversal (`traversal.py`), image placement (`fill.py`, `folder_resolution.py`), `text_metrics.py`, LibreOffice conversion (`fred_core.convert_office_bytes_to_pdf`), the `ppt_preview` chat part and side pane. The first iteration (pattern inventory + model-chosen pattern ids + composition layer) failed end to end; see proposal. This design replaces it; the acquired rendering pieces stay.

Facts that constrain the design (verified in code):

- `validate_config` receives `SaveContext(identity, services)` (`fred_sdk/contracts/capability/context.py:79`). The save path builds a full `BoundRuntimeContext` but only injects `workspace_fs`, `agent_assets`, `document_folders` (`fred_runtime/app/agent_app.py` `_build_capability_save_services`, ~3676). There is **no model port** on the save path or in capability routes; `ChatModelFactoryPort.build(definition, binding)` (`fred_sdk/contracts/runtime.py:556`) is turn-shaped. The process-wide factory is `get_runtime_context().config.chat_model_factory` (`RoutedChatModelFactory`, `fred_runtime/model_routing/provider.py:104`, enforcing `binding.usable_model_ids`). `ModelProfile` (`model_routing/contracts.py:145`) has no vision flag; `models_catalog.yaml` profiles are all `capability: chat`, default `chat.mistral.small`.
- A capability can change its stored config **only** through `validate_config`'s return value; nothing writes it back later. `agent_assets` is bound to the saving user's token, which may expire after the request.
- fred-agents runs several replicas. In-process helpers exist (`fred_runtime/common/background_tasks.spawn`, in-memory). Temporal workers run in knowledge-flow, control-plane and knowledge-base pods, not in fred-agents. `fred_core.tasks` (`cp_task_run`) has a closed task-kind union owned by control-plane. Capabilities may own tables (`cap_<id>_*`, own Alembic tree, `migrations_location()`); `fred-capability-writable-document/store.py` is the pattern (overridable module-level store provider, router authorises on the row).
- The analysis takes ~50 s, beyond what a synchronous save should hold.
- The feature is not on `swift`: stored configs exist only on local dev agents, so the config shape may change without `upgrade_config`.

## Goals / Non-Goals

**Goals:** the template's own slides, chosen right, every time or an explicit error; analysis that understands real corporate slides; a save that never waits on analysis; one code path for customer and built-in templates; measurable deck quality.

**Non-Goals:** drawing shapes the template does not hold (composition is parked, not abandoned); charts/SmartArt/tables as generated content; vision checks of the rendered output (text checks only); in-place editing of a generated deck.

## Decisions

### D1. Park composition, delete the generated theme

The composition layer moves to branch `parked/ppt-builder-composition` with the `ppt-builder-composition` change. `Box`, `ZoneRole`, `TEXT_ROLES` move from `design_system.py` into `models.py`. `theme.py` is deleted (dependents: `capability.py` middleware, `validate_config`, the `/theme` routes and the registration warm-up; tests `test_builder_capability.py` and the parked composition tests; frontend `usePatternsPreview.ts` via `/theme/preview.pdf`). Alternative — keep composition behind a switch — rejected: it is the code path that replaced good template slides, and keeping it doubles every test surface.

### D2. Analysis: deterministic structure, vision meaning

1. **Deterministic pass (kept, amended).** Layouts are classified from typed placeholders as today. On example slides **every text-bearing shape is a slot by default**; excluded only when its text repeats on ≥ 2 slides, or it is a date/footer/slide-number field (`a:fld` type or footer/date/sldNum placeholder). Repeat groups, capacities (`text_metrics`), exclusion of chart/table/icon-bank slides and the annotation channels stay. Copyable relationships drop slide-to-slide hyperlinks from the blockers (they are not copied, D6). The sample-text lexicon no longer decides fillability.
2. **Vision pass (new, `labelling.py`).** Example slides are rendered once (patterns deck → LibreOffice PDF → per-page PNG via `pypdfium2`), each slot's box is overlaid with its number (set-of-mark), and a vision model returns, per slide, a typed JSON: `kind`, `label`, per-slot `purpose`, `max_items`, `reusable`. Calls run with bounded concurrency. Layouts are not sent (placeholders already say what they are).
3. **Merge.** Vision decides `kind`, `reusable` and slot purposes; geometry and capacity stay deterministic. A slide whose vision answer is missing or invalid keeps its heuristic label and `labelled_by="heuristic"`, shown in the review panel — analysis never fails because the model did.

**One closed vocabulary**, `SlideKind`: `cover, agenda, section, bullets, two_columns, comparison, cards, figures, process, timeline, team, quote, image_text, closing, other`. It replaces `Intent` in the inventory, the overrides and the plan.

### D3. Model access outside a turn

Add a turn-free port to the SDK: `CapabilityModelPort` (optional field appended to `RuntimeServices`), `async ainvoke(messages, *, profile_id: str | None, require_vision: bool) -> AIMessage`, implemented in fred-runtime over `RoutedChatModelFactory.select`/`build_for_chat` (`model_routing/provider.py`), which resolves **the model the agent uses by default**: platform binding, then `resolve_effective_chat_profile` (`fred_sdk/contracts/context.py` ~600: agent override → team `chat_default_profile_id` → catalogue default), checked against `usable_model_ids`.

Gap found: the save binding (`_build_capability_save_services`) has no team routing policy, no `usable_model_ids` and no platform binding; control-plane sends those only at prepare-execution. So the validate-config call gains the same routing fields control-plane already computes for prepare-execution (WP10), the save binding carries them, and the background job keeps that binding. No agent-tuning model field exists; routing is keyed by `agent_id`, so the port uses the saved agent's id.

Override: optional `PptBuilderConfig.labelling_model` (profile id), rendered by a new stock widget id `model_profile` fed by the existing `GET /teams/{team_id}/routing-policy/available-models`; save checks only that the profile is known; usability and vision are enforced by the port. Unset → agent default.

**Vision toggle.** `PptBuilderConfig.use_vision: bool = True`. Off → the job makes no model call and labels by rules only. The selector shows only while the toggle is on and lists only vision-capable profiles. The form knows whether vision is possible from the existing `available-models` endpoint plus `effective-chat-model`, both extended with `supports_vision` (WP10). If neither the agent's resolved model nor any selectable profile has vision, the toggle is shown disabled and forced off, with "No vision-capable model is available for this agent; slides are labelled by rules". The job applies the same rule when the port is absent or refuses. `ModelProfile` gains optional `supports_vision`; capable profiles are flagged in `models_catalog.yaml`; the port fails closed when the resolved profile lacks it (→ heuristic labels, D2.3). Images go as LangChain `image_url` content parts. This touches the frozen runtime contract: dated entry in `RUNTIME-EXECUTION-CONTRACT.md` §8, and ships as its own PR (consolidation scope rule). Alternative — the capability reading the process-global runtime context directly — rejected: it bypasses the `RuntimeServices` boundary every capability is held to.

### D4. Background analysis with an owned table

- **Save** (`validate_config`): read the upload with python-pptx (an unreadable or oversized file still fails the save), store the bytes via `agent_assets`, compute `template_sha256`, upsert a `pending` row, `spawn` the job with the bytes in memory and the save's `CapabilityModelPort`, return at once. The stored config holds `template_sha256`, `use_vision`, `labelling_model` and the overrides — the inventory and `patterns_path` leave the config.
- **Store** `cap_ppt_builder_analysis` keyed by `(agent_instance_id, template_sha256, labelling_key)`, where `labelling_key` is `rules` or `vision:<profile id or agent-default>`, so toggling vision or changing the model re-runs the analysis: `status` (`pending|running|succeeded|failed`), `lease_until`, `inventory_json`, `patterns_pdf` (thumbnails), `error`, `team_id`, `saved_by`, timestamps. The job heartbeats the lease and writes the result in one transaction; it needs no Knowledge Flow token after the request.
- **Reads:** the middleware loads the row by `(instance, sha)`; a `succeeded` row is immutable, so a per-process cache keyed by the hash is replica-safe and costs one DB read per template per pod. `GET /analysis/{instance_id}` (status + summary + inventory) and `GET /analysis/{instance_id}/patterns.pdf` serve the form; authorised for users who can **edit** the agent: there is no `agent_instance` FGA type; control-plane checks `TeamPermission.CAN_UPDATE_AGENTS` (`team.can_update_agents: team_editor`, `schema.fga`) on the instance's team (`product/api.py`). Capability routers are mounted with authentication only (`agent_app.py` ~4741), so the router checks the same permission on the row's `team_id` through the pod's `rebac_engine` (`runtime_context.py`, used as `check_user_permission_or_raise` in `agent_app.py`), exposed to capabilities as a small dependency (WP1).
- **Recovery:** a row whose lease expired is `stale`; the next save or turn on any replica (both hold `agent_assets`) refetches the template and re-runs. The form shows "analysis interrupted" with the re-run action.
- **Re-analysis on rule change:** a `succeeded` row older than `ANALYSIS_VERSION` triggers the same job at the next save.

Alternatives: JSON result in the asset store (needs a valid user token when the job ends and a KF fetch per turn); Temporal worker in fred-agents (new worker deployment for a one-minute job); `fred_core.tasks` (closed union in a control-plane hotspot). The table is the smallest durable, replica-safe option that follows an existing capability pattern.

### D5. Agent unavailable until analysis succeeds

The agent itself is unavailable while its analysis is `pending`, `running`, `failed` or `stale`, reusing the existing suspension machinery: `AgentInstanceRow.suspension_reason` (`control_plane_backend/models/agent_instance_models.py`), closed enum `SuspensionReason` (`agent_instances/suspension.py`). Every guard already treats a non-null reason as unavailable: run → 409 (`product/service.py` ~3243), locked toggle (`AgentCard.tsx`), hidden from non-managers (`TeamAgentsPage.tsx`), chat picker / recents / search filter on `!suspension_reason`.

- Add `SuspensionReason.CAPABILITY_PENDING` (same column, no schema change) and an optional `suspension_detail` text so a failure can carry its message (`config_invalid` carries none today).
- Add one optional, generic SDK hook `AgentCapability.readiness(stored) -> Ready | Pending | Failed(message)` (`fred_sdk/contracts/capability/base.py`), served by the pod. Control-plane reads it after a save and in `run_capability_reconciliation_sweep` beside `reconcile_instance_config_health`, setting/clearing `capability_pending` / `capability_config_invalid`. No ppt-specific code in control-plane.
- ppt_builder's `readiness` reads its analysis row: pending/running/stale → Pending, failed → Failed(error), succeeded → Ready. Becoming available therefore waits for the next sweep or for the form's status poll, which asks control-plane to re-check the instance (WP10 picks one; no extra save needed).
- The reconciliation sweep has no production host, so listing a team's agents also re-checks its `capability_pending` instances (caller's token, ≤ 10 concurrently, 2 s bound; no answer changes nothing); with the form's re-check poll, an agent becomes available on the next listing after its analysis completes.
- Failed or interrupted keeps the agent unavailable; the form shows the error and a **"re-run analysis"** action (`POST /analysis/{instance_id}/rerun`). `build_presentation` still refuses unless succeeded (defence in depth).

Control-plane, SDK-hook and frontend-gating parts ship as their own work package (WP10).

### D6. Rendering (kept, fixed)

Duplicate + fill stays the only way an example slide reaches the deck; layouts are instantiated as today. Fixes: `_duplicate_slide` copies only image/media/external-hyperlink relationships (slide-to-slide links dropped, their `a:hlinkClick` removed), copies `p:clrMapOvr` and the notes slide; `_write_lines` reuses the template paragraph's `a:pPr` of the same level for every level. Fill by slot, overflow (`fontScale` floor then word-boundary cut, reported), repeat-group item removal and recentring, image zones, lost-content reporting — unchanged.

**After-render check (`checks.py`):** any original non-shared slide text still present on a duplicated slide is removed and reported; overflow and lost content are reported. The tool fails closed: a slide that ends with no filled slot is an error (D8), never a silent sample slide.

### D7. The code chooses the slide

The plan per slide: `title`, `subtitle`, `bullets`, `columns`, `items`, `image(s)`, `notes`, then `kind` — last, optional. `pattern` and pattern ids leave the schema; the catalogue in the tool description lists the kinds the template offers with their capacities (items, chars), never ids. The plan coercion in `plan.py` stays.

`assign.py` maps the whole deck at once: candidate archetypes per slide are those whose kind matches (`kind` given, else inferred from content shape) and that pass a **fit check** (every non-empty field has a slot, item count ≤ capacity, text within capacity after the shrink floor). Example slides outrank layouts of the same kind. A Viterbi-style pass over the slides minimises misfit cost plus a variety penalty under **deck rules**: cover exactly once, at position 1 (the first slide is assigned the cover archetype; no other slide may use it); closing at most once and only last; never three identical archetypes in a row when an alternative fits (otherwise allowed and reported). `DEGRADATION`, `resolve()`'s last-resort fallback and the id loose-matching are deleted.

### D8. No silent fallback: structured repair

If any slide has no fitting archetype, the tool builds nothing and returns `needs_revision` with, per slide: index, problem (e.g. "7 items; the largest cards slide holds 6"), and options from this template (split, trim to N, kind X). The success message no longer says "do not call again"; it lists what the after-render check removed or truncated. The prompt fragment tells the model to fix and call again with the whole deck.

### D9. Built-in Fred template

`assets/fred_template.pptx` — a real deck designed by the developer, with example slides for every `SlideKind` except `team`/`other` — ships as package data with `fred_template.inventory.json` produced by the same pipeline (vision included) through a `make` target; a test fails when the JSON's `analysis_version` lags. No template configured → this pair is used through the exact customer render path. The `/theme` routes are replaced by `/builtin` (inventory) and `/builtin/patterns.pdf`.

**Interim until the file arrives:** `builtin.py` exposes the built-in `(bytes, inventory)` pair and is backed by the existing `theme.py`, which already runs through `analyze_presentation` (heuristic labels, no vision). The no-template path keeps working with no new code; WP7 swaps the source and deletes `theme.py`.

### D10. Review panel and overrides

Thumbnail + label + kind per pattern; the author may change label or kind and exclude/include. `PatternOverride` keeps `label`, `kind`, `included`; zone-role overrides and the zone-outline detail dialog are deleted. Nothing is mandatory. The form shows the D4 status while pending.

### D11. Evaluation harness

`eval/` in the package, run by an opt-in `make eval` (never in `make test`): N prompts × templates through the real analysis, the real `build_presentation` tool and the configured LLM in a minimal ReAct loop with in-memory ports. Metrics per deck: distinct archetypes / slides, cover exactly once at 1, closing at most once at the end, no three in a row, leftover sample text, overflow, lost content, repairs. Templates: the local "PPT Corporate" agent's `config/ppt_builder_template.pptx` (path given by env var, never committed) and the built-in one. Results go into `verification.md`.

## Risks / Trade-offs

- [Vision model mislabels] → the author relabels in the panel; deterministic geometry still bounds what can be filled; eval measures the effect.
- [Vision cost/latency at upload, ~40 calls] → bounded concurrency, background, once per template hash.
- [Job lost on pod restart] → lease + recovery on next save/turn; the form says so.
- [Strict fit check yields repair loops on weak models] → options in the error are concrete; repairs are an eval metric with a target.
- [New SDK port widens the contract] → optional field, appended; ships alone with a contract entry.

## Migration Plan

Unreleased feature: no `upgrade_config`; local agents re-upload or re-save. New owned table via the package's Alembic tree (`python -m fred_runtime migrate`). The SDK port and the `supports_vision` flag are additive. Migration note: operations impact (the table migration, flagging vision models in the catalogue, the readiness field if WP10 is needed) → minor. The control-plane validate-config timeout is out of scope.

## Open Questions

Resolved by the developer: Q1 status/thumbnails visible to agent editors (D4); Q2 agent unavailable until analysis succeeds (D5); Q3 `pypdfium2`; Q4 agent's default model with optional override (D3); Q5 developer designs the built-in deck, `theme.py` interim (D9); Q6 timeout out of scope.

None remaining for design; implementation details are pinned in the tasks.
