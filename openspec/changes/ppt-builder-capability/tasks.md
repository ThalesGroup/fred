Paths are relative to `libs/capabilities/fred-capability-ppt-filler/fred_capability_ppt_filler/builder/` unless rooted; tests under `libs/capabilities/fred-capability-ppt-filler/tests/`. Each work package (WP) names the files it owns; a WP edits only its own files.

**Order:** WP0 → { WP1, WP2, WP6, WP10 } in parallel (WP1.1b needs WP10.0) → { WP3, WP5 } → WP4 → { WP7, WP8 } → WP9. WP7 is blocked on the developer's `fred_template.pptx`; WP9 runs with the interim built-in source if it has not landed. WP2 lands its model types (task 2.1) first so WP3/WP5 can start against them; WP3 codes against the WP1 port interface and a fake until WP1 merges.

## Kept from the first iteration (done, still valid)

- [x] K.1 Package scaffold and second entry point `ppt_builder`; `registry.validate()` passes with both capabilities
- [x] K.2 Layout classification from placeholder signatures (top-band BODY-as-heading)
- [x] K.3 Repeat-group detection, reading order, item-count adaptation (`_remove_decoration`, `_recentre_items`)
- [x] K.4 Annotation channels (shape names, notes, `{{key}}`)
- [x] K.5 Slide duplication with shared media; layout instantiation; fill by role through the shared traversal
- [x] K.6 Overflow control with `text_metrics` (fontScale floor, word-boundary cut, report); image zones from team folders
- [x] K.7 Plan coercion of malformed model output; lost-content reporting
- [x] K.8 Delivery: workspace write, PDF preview part / side pane / download chip; middleware prompt fragment, `execution_models=("react",)`
- [x] K.9 Frontend scaffold: plugin, pack options, generated slice target `update-ppt-builder-capability-api`, locales

## WP0. Park composition (first, alone)

Owns: `components.py`, `compose.py`, `composed_render.py`, `layout.py`, `design_system.py`, `theme.py` (import sites only), `analysis.py`, `models.py`, `render.py`, `tools.py`, `capability.py`, tests `test_components.py`, `test_composed_render.py`, `test_layout.py`, `test_design_system.py`, `test_anchors.py`, `test_content_shape.py` (+ compose references in `test_builder_capability.py`, `test_builder_render.py`, `test_fill.py`), `openspec/changes/ppt-builder-composition/`.

- [ ] 0.1 Push the current branch tip to `parked/ppt-builder-composition` (keeps the layer and its change intact)
- [ ] 0.2 Delete the composition modules, their tests and `openspec/changes/ppt-builder-composition/`; move `Box`, `ZoneRole`, `TEXT_ROLES` into `models.py`
- [ ] 0.3 Strip design-system/canvas/icon extraction from `analysis.py`, `PatternSource="composed"` and `ExclusionReason="canvas"` from `models.py`, compose calls from `render.py`, `icon_catalogue` from `tools.py`, `_composable` from `capability.py`
- [ ] 0.4 `make code-quality` + `make test` green in the package; one commit (`refactor:`)

## WP1. Turn-free model port (own PR)

Owns: `libs/fred-sdk/fred_sdk/contracts/runtime.py`, `libs/fred-runtime/fred_runtime/model_routing/{contracts,provider}.py`, `libs/fred-runtime/fred_runtime/app/agent_app.py` (`_build_capability_save_services` only), a new runtime adapter module, `apps/fred-agents/config/models_catalog.yaml`, `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` §8, `docs/swift/capabilities/AUTHORING.md`.

- [ ] 1.1 `CapabilityModelPort` (`ainvoke(messages, *, profile_id, require_vision)`) appended to `RuntimeServices` as optional; resolves the saved agent's default routed model, `profile_id` overrides when usable
- [ ] 1.1b Save binding carries the routing fields control-plane sends with validate-config (WP10.0); stock `model_profile` widget id in `UIHints`
- [ ] 1.2 Optional `ModelProfile.supports_vision`; flag the multimodal profiles in the catalogue
- [ ] 1.3 Runtime adapter over `chat_model_factory.build_for_chat` with a synthetic `capability:<id>` definition and the save binding; fails closed without vision; injected in `_build_capability_save_services`
- [ ] 1.4 Capability-router dependency checking `TeamPermission.CAN_UPDATE_AGENTS` on a team via the pod's `rebac_engine`
- [ ] 1.5 Tests in fred-sdk and fred-runtime (port present on save services, ReBAC denial, vision refusal); contract §8 dated entry; AUTHORING.md line

## WP2. Analysis: slots by default, `SlideKind`

Owns: `analysis.py`, `lexicon.py`, `models.py`, `overrides.py`, tests `test_builder_analysis.py`, `test_builder_overrides.py`.

- [ ] 2.1 `SlideKind` replaces `Intent`; `Pattern.kind`, `reusable`, `labelled_by`, slot `purpose`; `PatternOverride` = `label`, `kind`, `included` (zone roles deleted); bump `ANALYSIS_VERSION`
- [ ] 2.2 Every text-bearing shape on an example slide is a slot, except text repeated on ≥ 2 slides and footer/date/slide-number fields; the lexicon no longer gates fillability
- [ ] 2.3 Slide-to-slide hyperlinks no longer make a slide uncopyable (`COPYABLE_REL_SUFFIXES`)
- [ ] 2.4 Heuristic `kind` per slide as the vision fallback; tests on the reference template (env var, skipped when absent): no real-text example slide comes out title-only

## WP3. Vision labelling

Owns: `labelling.py` (new), `preview.py`, test `test_labelling.py` (new), package `pyproject.toml` (`pypdfium2`).

- [ ] 3.1 Render example slides to PNG (patterns deck → PDF → pages) with numbered slot overlays
- [ ] 3.2 Prompt + typed response (`kind`, `label`, slot `purpose`, `max_items`, `reusable`); bounded concurrency
- [ ] 3.3 Merge into the inventory; invalid/missing answer → heuristic label, `labelled_by="heuristic"`
- [ ] 3.4 Tests with a fake `CapabilityModelPort`: merge, malformed answer, port absent, vision refused

## WP4. Background analysis

Owns: `analysis_job.py` (new), `ppt_builder_migrations/` (new), `capability.py`, tests `test_analysis_job.py` (new), `test_analyze_route.py`, `test_builder_capability.py`.

- [ ] 4.1 `cap_ppt_builder_analysis` table + Alembic tree + `migrations_location()`; overridable store provider (writable-document pattern)
- [ ] 4.2 Job: deterministic analysis → labelling → patterns PDF, lease heartbeat, single-transaction result; runs via `spawn` under the heavy-job slot
- [ ] 4.3 `validate_config`: readability check, store bytes, `template_sha256`, pending row, spawn, immediate return; config = `template_sha256` + overrides; version-lag and stale-lease re-run
- [ ] 4.4 Routes `GET /analysis/{instance_id}`, `/analysis/{instance_id}/patterns.pdf`, `POST /analysis/{instance_id}/rerun`, authorised for agent editors; `use_vision` + `labelling_model` config fields, row key includes `labelling_key` (toggle/model change re-runs); middleware reads the row with a per-process hash cache; tool refuses unless succeeded
- [ ] 4.6 Implement `readiness()` from the analysis row (pending/running/stale → Pending, failed → Failed(error), succeeded → Ready)
- [ ] 4.5 Tests: save returns before the job ends, two-replica read via the shared store fake, stale lease recovery, re-run, non-editor refused, pending refusal

## WP5. Deck assigner and tool

Owns: `assign.py` (new), `plan.py`, `tools.py`, tests `test_assign.py` (new), `test_build_tool.py` (new).

- [ ] 5.1 Plan schema without `pattern`; `kind` last and optional; catalogue lists kinds with capacities, no ids
- [ ] 5.2 Fit check + kind inference from content shape; Viterbi-style assignment with deck rules (cover once at 1, closing ≤ 1 and last, no three in a row when an alternative fits)
- [ ] 5.3 Delete `resolve()`, `DEGRADATION`, loose id matching, `best_for_intent`
- [ ] 5.4 `needs_revision` structured error per slide with template-specific options; success message reports removals/truncations and no longer forbids another call; prompt fragment updated
- [ ] 5.5 Tests: each deck rule, unfit slide → error (no deck written), item over capacity, variety fallback on a one-archetype template

## WP6. Render fixes and after-render check

Owns: `render.py`, `checks.py` (new), test `test_builder_render.py`.

- [ ] 6.1 `_duplicate_slide`: copy only image/media/external-hyperlink rels, drop slide-to-slide `a:hlinkClick`; copy `p:clrMapOvr` and the notes slide (remove the dead notes branch)
- [ ] 6.2 `_write_lines` keeps each level's template `a:pPr`
- [ ] 6.3 `checks.py`: original non-shared text left on a duplicated slide removed and reported; overflow and lost content collected
- [ ] 6.4 Tests: no orphan slide after removing a linked agenda target, dark slide keeps colours, notes copied, two-level body formatting, leftover text removed

## WP7. Built-in Fred template

Blocked on the developer's deck. Owns: `assets/fred_template.pptx`, `assets/fred_template.inventory.json`, `builtin.py` (new), package `Makefile` target, package-data entry in `pyproject.toml`, `theme.py` (deletion), test `test_builtin_template.py` (new). Touches `capability.py` only to swap the import (after WP4).

- [ ] 7.1 Author the deck (Q5) with example slides for every kind but `team`/`other`
- [ ] 7.2 `make builtin-inventory` regenerates the JSON through the full pipeline; test fails when it lags `ANALYSIS_VERSION`
- [ ] 7.0 Interim (not blocked, done in WP4): `builtin.py` backed by `theme.py`
- [ ] 7.3 `/builtin` routes replace `/theme`; delete `theme.py` once the real deck lands

## WP8. Frontend

Owns: `apps/frontend/src/rework/features/capabilities/ppt_builder/**`, `apps/frontend/src/locales/{en,fr}/translation.json` (ppt_builder keys), `docs/swift/ux/COMPONENT-UX.md` (ppt_builder section).

- [ ] 8.1 Regenerate the API slice; analysis status hook polling `/analysis/{instance}` while pending/running; "analysis in progress / interrupted" states
- [ ] 8.1b Failed/interrupted state with error text and "re-run analysis" action
- [ ] 8.1c "Use a vision model" toggle (default on), disabled and forced off with the explanatory message when no vision-capable model is available; `model_profile` selector shown only while on, listing only vision-capable profiles
- [ ] 8.2 Review dialog: thumbnail + label + kind `Select` + include `Switch`; delete zone-role editing and the outline detail; built-in template from `/builtin`
- [ ] 8.3 vitest for status states and override serialisation; `make code-quality` + `make test` in `apps/frontend`

## WP10. Agent readiness (control-plane + SDK hook, own PR)

Owns: `libs/fred-sdk/fred_sdk/contracts/capability/base.py` (`readiness` hook), pod readiness endpoint in `libs/fred-runtime/fred_runtime/app/agent_app.py`, `apps/control-plane-backend/control_plane_backend/agent_instances/suspension.py`, `product/{service,schemas}.py` (sweep + post-save check, `suspension_detail`), its Alembic migration, regenerated `controlPlaneOpenApi.ts`, `AgentFormBody.tsx` / `AgentCard.tsx` reason strings, `CONTROL-PLANE-PRODUCT-CONTRACT.md` entry.

- [ ] 10.0 validate-config request carries the team routing fields already built for prepare-execution (profile overrides, chat default, usable model ids, platform binding)
- [ ] 10.0b `supports_vision` exposed on `available-models` and `effective-chat-model` responses (regenerated client)
- [ ] 10.1 `SuspensionReason.CAPABILITY_PENDING` + nullable `suspension_detail`; pending is not cleared by a save
- [ ] 10.2 Optional `readiness(stored)` SDK hook and pod endpoint; control-plane applies it after save and in the reconciliation sweep, plus an on-demand re-check the form's poll can trigger
- [ ] 10.3 Form/card strings for pending and failed-with-detail; tests in control-plane, fred-sdk, frontend

## WP9. Evaluation and verification (last)

Owns: `libs/capabilities/fred-capability-ppt-filler/eval/` (new), package `Makefile` (`eval` target), `verification.md` (new, this change), package `README.md`, migration note.

- [ ] 9.1 Harness: prompts × templates (local "PPT Corporate" template by env var, built-in), real analysis + tool + configured LLM, metrics per D11, JSON + table output
- [ ] 9.2 Run it; record results and targets met/missed in `verification.md`
- [ ] 9.3 `make code-quality` + `make test` in the package, fred-sdk, fred-runtime, frontend; `fred-performance-reviewer` on the tool path and the per-turn row read
- [ ] 9.4 End-to-end on the local stack (upload → status → build → preview/download; no template); README, migration note, issue #2679 status comment
