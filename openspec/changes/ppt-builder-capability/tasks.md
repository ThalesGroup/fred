Paths are relative to `libs/capabilities/fred-capability-ppt-filler/fred_capability_ppt_filler/builder/` unless rooted; tests under `libs/capabilities/fred-capability-ppt-filler/tests/`. Each work package (WP) names the files it owns; a WP edits only its own files.

**Order:** WP0 → { WP1, WP2, WP6, WP10 } in parallel (WP1.1b needs WP10.0) → { WP3, WP5 } → WP4 → { WP7, WP8 } → WP9 → WP11 → WP12 → { WP13, WP14 } → WP15. Q7–Q11 resolved 2026-10-06 (design.md). WP7 is blocked on the developer's `fred_template.pptx`; WP9 runs with the interim built-in source if it has not landed. WP2 lands its model types (task 2.1) first so WP3/WP5 can start against them; WP3 codes against the WP1 port interface and a fake until WP1 merges.

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

- [x] 0.1 Push the current branch tip to `parked/ppt-builder-composition` (keeps the layer and its change intact)
- [x] 0.2 Delete the composition modules, their tests and `openspec/changes/ppt-builder-composition/`; move `Box`, `ZoneRole`, `TEXT_ROLES` into `models.py`
- [x] 0.3 Strip design-system/canvas/icon extraction from `analysis.py`, `PatternSource="composed"` and `ExclusionReason="canvas"` from `models.py`, compose calls from `render.py`, `icon_catalogue` from `tools.py`, `_composable` from `capability.py`
- [x] 0.4 `make code-quality` + `make test` green in the package; one commit (`refactor:`)

## WP1. Turn-free model port (own PR)

Owns: `libs/fred-sdk/fred_sdk/contracts/runtime.py`, `libs/fred-runtime/fred_runtime/model_routing/{contracts,provider}.py`, `libs/fred-runtime/fred_runtime/app/agent_app.py` (`_build_capability_save_services` only), a new runtime adapter module, `apps/fred-agents/config/models_catalog.yaml`, `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` §8, `docs/swift/capabilities/AUTHORING.md`.

- [x] 1.1 `CapabilityModelPort` (`ainvoke(messages, *, profile_id, require_vision)`) appended to `RuntimeServices` as optional; resolves the saved agent's default routed model, `profile_id` overrides when usable
- [x] 1.1b Save binding carries the routing fields control-plane sends with validate-config (WP10.0); stock `model_profile` widget id in `UIHints`
- [x] 1.2 Optional `ModelProfile.supports_vision`; flag the multimodal profiles in the catalogue
- [x] 1.3 Runtime adapter over `chat_model_factory.build_for_chat` with a synthetic `capability:<id>` definition and the save binding; fails closed without vision; injected in `_build_capability_save_services`
- [x] 1.4 Capability-router dependency checking `TeamPermission.CAN_UPDATE_AGENTS` on a team via the pod's `rebac_engine`
- [x] 1.5 Tests in fred-sdk and fred-runtime (port present on save services, ReBAC denial, vision refusal); contract §8 dated entry; AUTHORING.md line

## WP2. Analysis: slots by default, `SlideKind`

Owns: `analysis.py`, `lexicon.py`, `models.py`, `overrides.py`, tests `test_builder_analysis.py`, `test_builder_overrides.py`.

- [x] 2.1 `SlideKind` replaces `Intent`; `Pattern.kind`, `reusable`, `labelled_by`, slot `purpose`; `PatternOverride` = `label`, `kind`, `included` (zone roles deleted); bump `ANALYSIS_VERSION`
- [x] 2.2 Every text-bearing shape on an example slide is a slot, except text repeated on ≥ 2 slides and footer/date/slide-number fields; the lexicon no longer gates fillability
- [x] 2.3 Slide-to-slide hyperlinks no longer make a slide uncopyable (`COPYABLE_REL_SUFFIXES`)
- [x] 2.4 Heuristic `kind` per slide as the vision fallback; tests on the reference template (env var, skipped when absent): no real-text example slide comes out title-only

## WP3. Vision labelling

Owns: `labelling.py` (new), `preview.py`, test `test_labelling.py` (new), package `pyproject.toml` (`pypdfium2`).

- [x] 3.1 Render example slides to PNG (patterns deck → PDF → pages) with numbered slot overlays
- [x] 3.2 Prompt + typed response (`kind`, `label`, slot `purpose`, `max_items`, `reusable`); bounded concurrency
- [x] 3.3 Merge into the inventory; invalid/missing answer → heuristic label, `labelled_by="heuristic"`
- [x] 3.4 Tests with a fake `CapabilityModelPort`: merge, malformed answer, port absent, vision refused

## WP4. Background analysis

Owns: `analysis_job.py` (new), `ppt_builder_migrations/` (new), `capability.py`, tests `test_analysis_job.py` (new), `test_analyze_route.py`, `test_builder_capability.py`.

- [x] 4.1 `cap_ppt_builder_analysis` table + Alembic tree + `migrations_location()`; overridable store provider (writable-document pattern)
- [x] 4.2 Job: deterministic analysis → labelling → patterns PDF, lease heartbeat, single-transaction result; runs via `spawn` under the heavy-job slot
- [x] 4.3 `validate_config`: readability check, store bytes, `template_sha256`, pending row, spawn, immediate return; config = `template_sha256` + overrides; version-lag and stale-lease re-run
- [x] 4.4 Routes `GET /analysis/{instance_id}`, `/analysis/{instance_id}/patterns.pdf`, `POST /analysis/{instance_id}/rerun`, authorised for agent editors; `use_vision` + `labelling_model` config fields, row key includes `labelling_key` (toggle/model change re-runs); middleware reads the row with a per-process hash cache; tool refuses unless succeeded
- [x] 4.6 Implement `readiness()` from the analysis row (pending/running/stale → Pending, failed → Failed(error), succeeded → Ready)
- [x] 4.5 Tests: save returns before the job ends, two-replica read via the shared store fake, stale lease recovery, re-run, non-editor refused, pending refusal

## WP5. Deck assigner and tool

Owns: `assign.py` (new), `plan.py`, `tools.py`, tests `test_assign.py` (new), `test_build_tool.py` (new).

- [x] 5.1 Plan schema without `pattern`; `kind` last and optional; catalogue lists kinds with capacities, no ids
- [x] 5.2 Fit check + kind inference from content shape; Viterbi-style assignment with deck rules (cover once at 1, closing ≤ 1 and last, no three in a row when an alternative fits)
- [x] 5.3 Delete `resolve()`, `DEGRADATION`, loose id matching, `best_for_intent`
- [x] 5.4 `needs_revision` structured error per slide with template-specific options; success message reports removals/truncations and no longer forbids another call; prompt fragment updated (text lives in `capability.py`: applied by WP4)
- [x] 5.5 Tests: each deck rule, unfit slide → error (no deck written), item over capacity, variety fallback on a one-archetype template

## WP6. Render fixes and after-render check

Owns: `render.py`, `checks.py` (new), test `test_builder_render.py`.

- [x] 6.1 `_duplicate_slide`: copy only image/media/external-hyperlink rels, drop slide-to-slide `a:hlinkClick`; copy `p:clrMapOvr` and the notes slide (remove the dead notes branch)
- [x] 6.2 `_write_lines` keeps each level's template `a:pPr`
- [x] 6.3 `checks.py`: original non-shared text left on a duplicated slide removed and reported; overflow and lost content collected
- [x] 6.4 Tests: no orphan slide after removing a linked agenda target, dark slide keeps colours, notes copied, two-level body formatting, leftover text removed

## WP7. Built-in Fred template

Blocked on the developer's deck. Owns: `assets/fred_template.pptx`, `assets/fred_template.inventory.json`, `builtin.py` (new), package `Makefile` target, package-data entry in `pyproject.toml`, `theme.py` (deletion), test `test_builtin_template.py` (new). Touches `capability.py` only to swap the import (after WP4).

- [ ] 7.1 Author the deck (Q5) with example slides for every kind but `team`/`other` (deck shipped; since WP12 the rules analysis finds `cover`, `quote`, `image_text`, `cards`; the deck still has no `timeline` slide: developer fix pending, then `make builtin-inventory`)
- [x] 7.2 `make builtin-inventory` regenerates the JSON through the full pipeline; test fails when it lags `ANALYSIS_VERSION`
- [x] 7.0 Interim (not blocked, done in WP4): `builtin.py` backed by `theme.py` (superseded: `builtin.py` reads the shipped asset)
- [x] 7.3 `/builtin` routes replace `/theme`; delete `theme.py` once the real deck lands

## WP8. Frontend

Owns: `apps/frontend/src/rework/features/capabilities/ppt_builder/**`, `apps/frontend/src/locales/{en,fr}/translation.json` (ppt_builder keys), `docs/swift/ux/COMPONENT-UX.md` (ppt_builder section).

- [x] 8.1 Regenerate the API slice; analysis status hook polling `/analysis/{instance}` while pending/running; "analysis in progress / interrupted" states
- [x] 8.1b Failed/interrupted state with error text and "re-run analysis" action
- [x] 8.1c "Use a vision model" toggle (default on), disabled and forced off with the explanatory message when no vision-capable model is available; `model_profile` selector shown only while on, listing only vision-capable profiles
- [x] 8.2 Review dialog: thumbnail + label + kind `Select` + include `Switch`; delete zone-role editing and the outline detail; built-in template from `/builtin` (served by `/theme` until WP7 renames it)
- [x] 8.3 vitest for status states and override serialisation; `make code-quality` + `make test` in `apps/frontend` (run as tsc/prettier/eslint/scoped vitest while a dev server used the worktree; the full make targets run in 9.3)

## WP10. Agent readiness (control-plane + SDK hook, own PR)

Owns: `libs/fred-sdk/fred_sdk/contracts/capability/base.py` (`readiness` hook), pod readiness endpoint in `libs/fred-runtime/fred_runtime/app/agent_app.py`, `apps/control-plane-backend/control_plane_backend/agent_instances/suspension.py`, `product/{service,schemas}.py` (sweep + post-save check, `suspension_detail`), its Alembic migration, regenerated `controlPlaneOpenApi.ts`, `AgentFormBody.tsx` / `AgentCard.tsx` reason strings, `CONTROL-PLANE-PRODUCT-CONTRACT.md` entry.

- [x] 10.0 validate-config request carries the team routing fields already built for prepare-execution (profile overrides, chat default, usable model ids, platform binding)
- [x] 10.0b `supports_vision` exposed on `available-models` and `effective-chat-model` responses (regenerated client)
- [x] 10.1 `SuspensionReason.CAPABILITY_PENDING` + nullable `suspension_detail`; pending is not cleared by a save
- [x] 10.2 Optional `readiness(stored)` SDK hook and pod endpoint; control-plane applies it after save and in the reconciliation sweep, plus an on-demand re-check the form's poll can trigger
- [x] 10.3 Form/card strings for pending and failed-with-detail; tests in control-plane, fred-sdk, frontend

## WP9. Evaluation and verification (last)

Owns: `libs/capabilities/fred-capability-ppt-filler/eval/` (new), package `Makefile` (`eval` target), `verification.md` (new, this change), package `README.md`, migration note.

- [x] 9.1 Harness: prompts × templates (local "PPT Corporate" template by env var, built-in), real analysis + tool + configured LLM, metrics per D11, JSON + table output
- [x] 9.2 Run it; record results and targets met/missed in `verification.md`
- [x] 9.3 `make code-quality` + `make test` in the package, fred-sdk, fred-runtime, frontend; `fred-performance-reviewer` on the tool path and the per-turn row read
- [ ] 9.4 End-to-end on the local stack (upload → status → build → preview/download; no template); README, migration note, issue #2679 status comment

## WP11. First-call success: capacities, coherent labels, soft fallback

Owns: `analysis.py`, `models.py`, `labelling.py`, `assign.py`, `plan.py`, `tools.py`, `render.py` (`_fit` reads the stored capacity, line sources), `fred_capability_ppt_filler/text_metrics.py`, their tests, regenerated ppt_builder frontend slice, `verification.md`.

- [x] 11.1 Per-slot capacity `chars_per_line × max_lines` stored at analysis, calibrated on the slot's sample text (binary search, bounded); fit check, renderer and description read it; bump `ANALYSIS_VERSION`
- [x] 11.2 Vision kind accepted only when compatible with the slide's slots (D2.3 table); rejections logged, counted, shown as pattern warnings
- [x] 11.3 Soft fallback (D7): unavailable, unfitting or misplaced requested kind → best fitting other kind; substitutions named in the success message
- [x] 11.4 Actionable `needs_revision` (D8): field + element + measured limit + concrete options; resent-unchanged / changed-but-same flagged; description shows per-zone capacity
- [x] 11.4b Found by the eval (D6): a subtitle without its zone leads the body; sequential step numbers need no number zone
- [x] 11.5 Tests for each; eval re-run on the WP9 matrix with first-call success; `verification.md` before/after
- [x] 11.6 Package `make code-quality` + `make test`; frontend slice regenerated and `tsc` clean

## WP12. Example slides that copy a layout; rows of same-size shapes

Owns: `analysis.py`, `render.py` (item removal), their tests, `assets/fred_template.inventory.json`, package `.baseline/detect-secret-baseline.json` (the deck hash), `verification.md`.

- [x] 12.1 A slide copying its layout replaces the layout pattern (later copies dropped, excluded copy keeps the layout); slide 1 → `cover` hint; `OBJECT` placeholder named as an image is an image slot; title-less quote → title + subtitle; placeholder padding/wrap/font inherited by idx
- [x] 12.2 Rows of same-size non-grouped text shapes → repeat group (≥ 3, or ≥ 2 with an aligned second row; grid; column-body limits 35 % wide / 40 % tall)
- [x] 12.3 Renderer removes and recentres non-grouped items shape by shape
- [x] 12.4 Tests: synthetic decks (figures row, process pairs, two/three-column bodies untouched, layout copy replaced, cover hint), built-in asset, reference template; bump `ANALYSIS_VERSION`, `make builtin-inventory`
- [x] 12.5 Eval re-run (builtin rules, corporate and prism rules + vision); `verification.md` updated; package `make code-quality` + `make test`

## WP13. Deck-wide variety (D12, D13 analysis part)

Owns: `analysis.py` (`_copies_layout`, duplicate placeholder idx), `models.py` (delete `preferred`), `labelling.py` (`preferred` removal only), `assign.py`, `plan.py` (`zone_summary`), `render.py` (item heading lead, decoration of removed items), `tools.py` (catalogue, description, variety note), their tests, `assets/fred_template.inventory.json`, regenerated ppt_builder frontend slice, `verification.md`.

- [x] 13.1 Reuse cost `_REUSE × k` per prior use of the same pattern anywhere in the deck; beam search with use counts + last two choices replaces `_viterbi`; deck rules unchanged
- [x] 13.2 Empty item image zones cost `_IMAGE_HOLE` in `misfit`
- [x] 13.3 Item `heading` with no heading zone leads the single text zone in bold (fit check and renderer agree); lost only when it does not fit (Q8)
- [x] 13.4 Catalogue lists every distinct variant per kind with its label (drop `_MAX_VARIANTS`); description asks for varied content shapes
- [x] 13.5 Success message: a pattern used ≥ 3 times names its slides and the unused variants with their sizes
- [x] 13.6 `_copies_layout`: picture placeholders are slots; a slide holding all its layout's slots stands for it even with drawn decoration (Q7); duplicate `idx` on a slide → distinct keys + warning; bump `ANALYSIS_VERSION`, `make builtin-inventory`
- [x] 13.7 Decoration overlapping a removed item is removed with it (top-level icon on `slide:272`) — already the case; covered by the reference-template test
- [x] 13.8 Delete `Pattern.preferred` (models, analysis, labelling, API slice) — frontend slice regeneration left to the frontend owner
- [x] 13.9 Tests: A B A B avoided when a third fitting pattern exists, icon cards chosen for short items, image cards cost their empty pictures, heading+text items fit a one-text-zone card, covered layouts leave the inventory, catalogue shows 6 cards variants on the Paintress fixture
- [x] 13.10 Eval: add "max uses of one pattern" and "template patterns used across the run" metrics; re-run builtin + corporate; `verification.md`; package `make code-quality` + `make test`

## WP14. Review dialog sections and card layout (D13 frontend part)

Owns: `apps/frontend/src/rework/features/capabilities/ppt_builder/PatternReviewDialog.{tsx,module.css,test.tsx}`, `apps/frontend/src/locales/{en,fr}/translation.json` (ppt_builder keys), `docs/swift/ux/COMPONENT-UX.md` (ppt_builder section).

- [x] 14.1 Three sections: slides of the deck, layouts (collapsed, one-line hint), excluded; thumbnails keep their page by pattern id
- [x] 14.2 `.cardHeader` `grid-template-columns: minmax(0, 1fr) auto`; label `TextInput` `compact`; `Switch size="small"`; thumbnail page width from the thumbnail box
- [x] 14.3 vitest: sections split by `source` and `included`; locales en/fr; COMPONENT-UX line
- [ ] 14.4 Checked in the browser on the Paintress agent (switch inside the card, no gap above the kind select); frontend checks as tsc/prettier/eslint/scoped vitest (no `make` while Vite runs)

## WP15. Table slides (D14)

Owns: `analysis.py` (table zone, exclusion rule), `models.py` (`table` kind, table zone fields), `labelling.py` (vocabulary, compatibility), `plan.py` (`table` field, coercion, summary), `assign.py` (fit, inference, misfits), `render.py` (table fill), `checks.py`, `tools.py` (schema, description), `eval/` (prompts, metrics), their tests, `assets/fred_template.inventory.json`, regenerated ppt_builder frontend slice + `types.ts` `SLIDE_KINDS` + kind locales, `verification.md`.

- [ ] 15.1 `SlideKind` gains `table`; data-table detection (≥ 2 columns, no merges, body cells empty/sample, no varying per-cell fill) → table zone with header flag, per-column capacity, line height, `max_lines`; other tables keep the `table` exclusion; bump `ANALYSIS_VERSION`
- [ ] 15.2 Vision prompt vocabulary + compatibility (`table` needs a table zone)
- [ ] 15.3 Plan `table: {header, rows}` with coercion (ragged rows padded); `infer_kinds` → `table`; catalogue line `table: title …; table N columns (≈C chars per cell line), ≈L lines of rows`
- [ ] 15.4 Fit check: per-row wrapped lines vs `max_lines` at full size and at the shrink floor; column count ≤ template (fewer allowed per Q10); misfits name the row/cell and the limits; no table slide in the template → misfit
- [ ] 15.5 Render: header + cells with `endParaRPr` attributes, rows cloned (fresh `a16:rowId`) or removed, columns removed with widths rescaled, frame height updated, one table-wide font scale
- [ ] 15.6 Checks: no template cell text left, frame on the slide, shrink reported
- [ ] 15.7 Tests: Paintress-like synthetic 12 × 5 table (fewer rows, more rows, fewer columns, too long → needs_revision), merged-cell and Gantt-style grids stay excluded, the output opens without repair (unique row ids)
- [ ] 15.8 Eval prompts with tabular content; metrics: table used when given, shape kept, no overflow; LibreOffice preview of the table style checked; `verification.md`; package `make code-quality` + `make test`; frontend slice regenerated and `tsc` clean
