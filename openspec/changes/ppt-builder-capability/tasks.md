Paths are relative to `libs/capabilities/fred-capability-ppt-filler/fred_capability_ppt_filler/builder/` unless rooted; tests under `libs/capabilities/fred-capability-ppt-filler/tests/`. Each work package (WP) names the files it owns; a WP edits only its own files.

**Order:** WP0 → { WP1, WP2, WP6, WP10 } in parallel (WP1.1b needs WP10.0) → { WP3, WP5 } → WP4 → { WP7, WP8 } → WP9 → WP11 → WP12 → { WP13, WP14 } → WP15 → WP16 → WP17 → WP18 → WP19. Q7–Q11 resolved 2026-10-06 (design.md). WP7 is blocked on the developer's `fred_template.pptx`; WP9 runs with the interim built-in source if it has not landed. WP2 lands its model types (task 2.1) first so WP3/WP5 can start against them; WP3 codes against the WP1 port interface and a fake until WP1 merges.

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
- [x] 1.1b Save binding carries the routing fields control-plane sends with validate-config (WP10.0)
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
- [x] 8.1c "Use a vision model" toggle (default on), disabled and forced off with the explanatory message when no vision-capable model is available; model selector (inside the capability's own form widget) shown only while on, listing only vision-capable profiles
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

- [x] 15.1 `SlideKind` gains `table`; data-table detection (≥ 2 columns, no merges, body cells empty/sample, no varying per-cell fill) → table zone with header flag, per-column capacity, line height, `max_lines`; other tables keep the `table` exclusion; bump `ANALYSIS_VERSION`
- [x] 15.2 Vision prompt vocabulary + compatibility (`table` needs a table zone)
- [x] 15.3 Plan `table: {header, rows}` with coercion (ragged rows padded); `infer_kinds` → `table`; catalogue line `table: title …; table N columns (≈C chars per cell line), ≈L lines of rows`
- [x] 15.4 Fit check: per-row wrapped lines vs `max_lines` at full size and at the shrink floor; column count ≤ template (fewer allowed per Q10); misfits name the row/cell and the limits; no table slide in the template → misfit
- [x] 15.5 Render: header + cells with `endParaRPr` attributes, rows cloned (fresh `a16:rowId`) or removed, columns removed with widths rescaled, frame height updated, one table-wide font scale
- [x] 15.6 Checks: no template cell text left, frame on the slide, shrink reported
- [x] 15.7 Tests: Paintress-like synthetic 12 × 5 table (fewer rows, more rows, fewer columns, too long → needs_revision), merged-cell and Gantt-style grids stay excluded, the output opens without repair (unique row ids)
- [x] 15.8 Eval prompts with tabular content; metrics: table used when given, shape kept, no overflow; LibreOffice preview of the table style checked; `verification.md`; package `make code-quality` + `make test`; frontend slice regenerated and `tsc` clean

## WP16. No dropped text, first-deck variety revision, choice guide (D15)

Owns: `plan.py` (coercion: ignored fields, merged aliases), `assign.py` (content problems, repeats), `render.py` (ignored-field warning removal), `tools.py` (variety revision, description guide), `eval/` (prompt, `lost` metric, `ls`), tests `test_build_tool.py`, `test_assign.py`, `port_fakes.py`, `verification.md`.

- [x] 16.1 Coercion keeps unmapped keys of slides, columns and items as ignored fields (`key 'text'`); a field given under its name and an alias is merged; a `{heading, text}` bullet keeps both
- [x] 16.2 Assigner: ignored fields and unbalanced columns/items (heading without body, body without heading beside a complete entry) → `needs_revision` naming slide and field; renderer's ignored-field warning deleted
- [x] 16.3 Repeats (pattern, slides, unused variants of its kind, unused slides of other non-structural kinds) feed both the passive note and the revision
- [x] 16.4 First deck only (no `.pptx` in `outputs/{session_id}`, listed only when needed): a non-structural slide used ≥ 3 times with an alternative → `needs_revision` once per tool instance, accepting the next call; later turns keep the note
- [x] 16.5 Description: choice guide from the offered kinds replaces the variety sentence; length measured before/after
- [x] 16.6 Eval: comparison prompt (two countries, figures, domains, dated initiatives, challenges); `lost` counts raw-argument text absent from the deck; variety revisions counted; `MemoryWorkspace.ls`
- [x] 16.7 Tests: heading2-without-bullets plan → `needs_revision`; variety revision fires once on the first deck and accepts the resend; a later-turn deck gets only the note; coercion keeps every key
- [x] 16.8 Package `make code-quality` + `make test` (+ corporate and Paintress reference); `make eval` sequentially (paintress rules + vision, corporate, builtin) vs WP15; `fred-performance-reviewer` on the tool path; `verification.md`

## WP17. Variety by kind, content-based alternatives (D16)

Owns: `assign.py` (repeats by kind, content shapes), `tools.py` (variety payload, guide), `eval/` (prompt, max kind repeat metric), tests `test_assign.py`, `test_build_tool.py`, `verification.md`.

- [x] 17.1 Repeats grouped by kind for non-structural kinds (by template slide for structural ones); revisable as in D15; the passive note names the kind repeat
- [x] 17.2 Content shapes per slide of a repeat: dated lines → timeline; `Label :` groups with `- ` lines → two_columns / cards; `Label : text` lines → cards; short numeric lines → figures; numbered/step lines → process; kept only when the template offers the kind with a slide holding that many entries
- [x] 17.3 Variety ask and note name the slides and the suggested kinds
- [x] 17.4 Choice guide: "at most 2 bullets slides per deck" when alternatives exist; description length measured
- [x] 17.5 Tests: the evidence plan (5 bullets slides on 5 template slides) → one ask naming slide 7 → timeline and 9/10 → two_columns/cards; resend built; later-turn deck gets the note only; structural kinds exempt
- [x] 17.6 Eval: `thales_spain_italy` prompt (no explicit comparison); "max kind repeat" metric (non-structural)
- [x] 17.7 Package `make code-quality` + `make test` (+ corporate and Paintress reference); `make eval` sequentially (paintress rules + vision, corporate, builtin) vs WP16; paintress rules with `chat.mistral.medium`; `fred-performance-reviewer` on the tool path; `verification.md`
- [x] 17.8 Closing slide "Merci" wrapped by the preview: diagnosed (template vs render vs font), fixed only if the render causes it — LibreOffice font substitution on the template's own layout text; no code change

## WP18. Variety asked on the first call only, with fit hints (D17)

Owns: `assign.py` (repeats beside problems, content shape lengths, fit hints), `tools.py` (first-call ask, merged revision), tests `test_assign.py`, `test_build_tool.py`, `verification.md`.

- [x] 18.1 The variety ask is evaluated on the first call of a turn only; a later call (after a fit repair or a resend) is never asked
- [x] 18.2 The assigner computes repeats over the fitting slides when other slides have problems; a first call with both returns one `needs_revision` holding the problems and the variety block
- [x] 18.3 Each content-based suggestion carries what the favoured variant holds (items max and item fields, or exactly 2 columns, with sizes from the inventory) and a shorten hint when the slide's longest entry exceeds its room
- [x] 18.4 Tests: ask only on the first call; no ask after a fit repair; merged ask + problems in one revision; hints carry the inventory's numbers; resend built; later deck note only
- [x] 18.5 Package `make code-quality` + `make test` (+ corporate and Paintress reference); `make eval` sequentially (14 prompts, paintress rules + vision, corporate, builtin) vs WP16 and WP17; `fred-performance-reviewer` on the tool path; `verification.md`

## WP19. Variety check setting, capped suggestions (D18)

Owns: `assign.py` (structural exclusion, grouping by mode, caps, spread), `tools.py` (mode-gated ask), `capability.py` (`variety_check` config + `FieldSpec`), `eval/` (`--variety`), frontend locales fr/en, Help Center fr/en, tests `test_assign.py`, `test_build_tool.py`, capability tests, `verification.md`.

- [x] 19.1 Structural slides (requested/inferred kind or template slide kind cover/section/agenda/closing) grouped apart, never revisable; the small-model evidence plan (agenda built on a bullets slide + 2 bullets slides) gets no ask
- [x] 19.2 Caps: a kind is suggested or offered only while its distinct variants exceed the deck's slides of that kind (shared across one answer's suggestions); one suggested kind per slide, the least suggested so far
- [x] 19.3 `variety_check` (`template_slide` default, `kind`, `off`) on `PptBuilderConfig` + select `FieldSpec`; tool asks per mode; passive note kept in every mode; not in `labelling_key`; missing value → default
- [x] 19.4 Frontend fr/en title, description, option labels; generic form renders it (checked); Help Center fr/en mentions it; ppt_builder slice regenerated only if the dump changes
- [x] 19.5 Tests: one figures variant → at most one figures suggestion; structural slides never suggested; spread across kinds; small-model plan no ask; each mode's behaviour; default for a missing value; setting not in `labelling_key`
- [x] 19.6 Package `make code-quality` + `make test` (+ corporate and Paintress reference); `make eval` strictly sequential, final code, 14 prompts: `template_slide` vs `kind` on Paintress rules + vision and corporate rules (`mistral-small`), Paintress rules (`mistral-medium`); `off` on Paintress rules (`mistral-small`); `fred-performance-reviewer` on the tool path; `verification.md` with a recommendation for the default

## WP20. Max uses setting, variety row (D19)

Owns: `assign.py` (caps, over-max cost, ask threshold), `tools.py` (`at_most`, guide), `capability.py` (`variety_max_uses`, widget hints), `eval/` (`--max-uses`, `--no-builtin`), frontend `ppt_builder/` (variety row), locales fr/en, Help Center fr/en, tests, `verification.md`.

- [x] 20.1 `variety_max_uses` (1..5, default 2) on `PptBuilderConfig` + `FieldSpec`; both variety fields owned by the `ppt_builder_template` widget; missing value → 2; not in `labelling_key`
- [x] 20.2 Realistic caps per template slide / per kind, structural exempt; beam adds `_OVER_MAX` per content use beyond the cap when the check is on; requested kind never switched
- [x] 20.3 Ask when a group exceeds its cap (D17 timing unchanged); `at_most` in each variety entry; `off` keeps the 3+ note
- [x] 20.4 Choice guide per mode and max, none when off; bullets cap removed
- [x] 20.5 Tests: max 1 spreads a kind's slides over distinct variants; requested kind kept when only one variant; cap raised when the deck forces it; ask fires at max+1 per mode; guide sentences; default for a stored config without the field
- [x] 20.6 Frontend row (switch, two small selects, fr/en), generic select labels removed, Help Center fr/en; vitest (off → "off", on → last mode, max writes `variety_max_uses`, labels); tsc/prettier/eslint; slice regenerated only if the dump changes
- [x] 20.7 Package `make code-quality` + `make test` (+ corporate and Paintress reference); `fred-performance-reviewer` on the tool path; targeted eval, strictly sequential (6 cells: small Paintress rules template_slide ×2/×1, kind ×2/×1; medium Paintress rules kind ×1, template_slide ×1), one contact sheet per cell for `thales_spain_italy`; `verification.md` with a recommendation for the V1 beta defaults

## WP21. Limits in the schema, build directly, framed pictures, agent prompt eval (D20)

Owns: `plan.py` (field rooms beside `zone_summary`), `tools.py` (schema hints, cache key), `capability.py` (`_BUILD_INSTRUCTIONS`), `models.py` + `analysis.py` (`Zone.framed`, `ANALYSIS_VERSION` 11), `assign.py` (framed picture misfit), built-in inventory, `eval/` (`--agent-prompt`, `agent_prompts/agent_prompt_fr.txt`, metrics on the rendered assignment), tests, `verification.md`.

- [x] 21.1 Schema field descriptions carry the template's room per field (largest variant per kind, common value + differing kinds, cover exact); no `maxLength`; schema cached by kinds + hints; schema/description size and build time per turn measured
- [x] 21.2 `_BUILD_INSTRUCTIONS`: build directly; ask to validate an outline only when the user asked or the subject is unknown
- [x] 21.3 Analysis flags image zones framed by an unremovable layout/master shape (`Zone.framed`); `ANALYSIS_VERSION` 11; built-in inventory regenerated; slice regenerated only if the dump changes
- [x] 21.4 Fit check: an empty framed picture (slide zone or used item) is a misfit; catalogue quotes `(required)`
- [x] 21.5 Tests: field hints (common room, differing kinds, cover); framed misfit and fallback to another kind; Paintress/corporate reference: `slide:266`/`slide:267` framed, the 'Nos quatre priorités' slide not built on them without images, built on one with images
- [x] 21.6 Eval: `--agent-prompt`; the French candidate prompt committed; variety metrics measured on the assignment the tool rendered (same variety and max)
- [x] 21.7 Package `make code-quality` + `make test` (+ corporate and Paintress reference); `fred-performance-reviewer` on the tool path; eval strictly sequential, Paintress rules, 14 prompts, `--no-builtin`, `template_slide` max 1: small/medium × stand-in/optimized prompt; contact sheets for `cyber_2027` and `thales_spain_italy`; `verification.md` with fit problems by field vs WP20 cell 2 and a recommendation on the suggested prompt

## WP22. Short author prompt benchmark (D20)

Owns: `eval/` (`agent_prompts/agent_prompt_short_fr.txt`, the reply after delivery), `verification.md`.

- [x] 22.1 Short French author prompt: the stand-in plus two rules (no invented figures, prefer qualitative content to a placeholder; one- or two-sentence answer after delivery, no slide recap); no slide count, no "à compléter"
- [x] 22.2 Eval records the model's answer after delivery (`reply`, `reply_output_tokens`, `reply_tool_call`), its tokens kept out of the build's; summary columns for reply length and rebuilds after delivery
- [x] 22.3 Eval strictly sequential, WP21 settings (Paintress rules, 14 prompts, `--no-builtin`, `template_slide` max 1): E small + short prompt, F medium + short prompt; replies after delivery replayed on A–F's delivered runs for a like-for-like comparison; `verification.md` with the comparison and the recommendation
- [x] 22.4 Variety default recorded: `template_slide`, `variety_max_uses` 2 (developer decision, no code change)

## WP23. Review fixes: first deck from the history, outdated analysis refresh, D19 caps

Owns: `tools.py` + `capability.py` (first-deck signal), `analysis_job.py` + `capability.py` (outdated analysis refresh), `design.md` D15/D4/D5/D19/D20, delta spec, tests, `verification.md`.

- [x] 23.1 First deck of the conversation read from the history the model was sent (an earlier `build_presentation` delivery), not from an outputs-folder listing the write-only `WorkspaceFsPort` no longer offers; the listing path, its fakes (`FsEntry`, `ls`) and fallback deleted. Tests: first deck asks; a delivered deck in the history gets the note only and the plan is built as sent; a history of `needs_revision`/errors/another tool's text is still a first deck; both success texts count
- [x] 23.2 Outdated analysis refreshed, never blocking: a succeeded analysis made by older rules stays ready and in use; the first readiness check, turn or save starts one background re-run from the stored template (`refresh_outdated`, atomic `claim_refresh` on the lease, row kept `succeeded`); a failed refresh keeps the old result and spends its attempts; the re-run action and a save force one; `current` true while a refresh holds the lease. A vision-labelled one is auto-refreshed only where the save left its model port, otherwise it stays outdated and the form (`analysis.outdatedVision`, fr/en) says a save re-reads it with the vision model. Tests: outdated → ready, one job for concurrent checks and a turn, old inventory served, new one used and cached after success; failed refresh → old inventory kept, attempts spent, no second job, forced re-run starts one; re-run route on an outdated analysis keeps it succeeded; vision-keyed outdated row without a port → no job, still ready, `current: false`; with a remembered port → one job with that port; panel shows the vision hint (vitest written, not run)
- [x] 23.3 D19 cap aligned to the code: one deck-wide cap per mode (`ceil(content slides / content template slides or kinds)`, floor `variety_max_uses`), not per kind; design D19 and the "never demands the impossible" scenario rewritten, no code change (the code was always deck-wide, benchmarked WP20–WP22; a per-kind cap would silence the ask on a kind with few variants)

## WP24. Review fixes: sections, zip bomb, analysed template, analysis job robustness

Owns: `render.py` (sections), `pptx_archive.py` + every `.pptx` opened from bytes (both capabilities), `capability.py` + `analysis_job.py` (template from the row, outdated cache, effective labelling key, background slots, launched sha, same-file upload), `tools.py` (pictures that load), `labelling.py` (shape-name kinds), comments, `design.md` D2/D4/D6/D20, delta spec, tests, `verification.md`.

- [x] 24.1 Template sections (`p14:sectionLst`) dropped with the template's slides in the rendered and patterns decks (they listed removed slides only: PowerPoint repair prompt). Test: built-in template has sections, rendered and patterns decks have none
- [x] 24.2 Zip-bomb pre-check (`pptx_archive.open_presentation`: total ≤ 512 MB, member ≤ 256 MB, ratio ≤ 100 above 10 MB) before every `Presentation()` on bytes, `ppt_filler`'s parse/fill/folder resolution included. Tests: a deck declaring a ~4 GB member and a 12 MB ratio bomb refused; both saves and the analysis refuse it
- [x] 24.3 The build renders the template bytes from the analysis row filtered on the config's sha (cached per pod by sha, 4 entries), never the asset a newer save rewrote. Tests: a turn on the old config after a newer template's save refuses instead of rendering the newer file; a pod without cache builds from the row with an empty asset store
- [x] 24.4 Outdated inventories cached per pod with a 60 s re-read deadline; a refresh finishing on the pod drops the instance's entries. Tests: no row read on the second turn when the refresh never lands; re-read once due; a landed refresh replaces the cached one
- [x] 24.5 A run without the model port stores `rules` as its labelling key; a `rules` row serves a vision config; a save with a port re-runs it with vision, one without leaves it. Tests: interrupted recovery without port → `rules`, agent ready, save without port no job, save with port → vision; forced refresh without port → `rules`, then a save relabels
- [x] 24.6 Background CPU work holds at most 2 of the 4 heavy-job slots. Test: four background jobs leave two slots free for turns
- [x] 24.7 Rebuilding a lost row returns the launched sha, not the client's. Test: stale client sha → saved config names the analysed file, agent ready
- [x] 24.8 A cancelled background job releases its heavy-job slot when its worker thread ends (done callback on a shielded thread task). Test: slot held after cancel until the thread ends
- [x] 24.9 The tool fetches the plan's pictures before assigning and assigns with those that open as an image; unloadable ids are dropped and reported. Test: unloadable ids on a framed slide → the unframed variant, no problem; all loading → the framed slide
- [x] 24.10 A kind stated by a shape name outranks the vision kind, as a `kind:` note does. Test: a shape renamed "Roadmap" keeps the analysed kind against a vision answer
- [x] 24.11 Uploading the same file (same sha and labelling key) keeps a succeeded, current analysis. Test: same job id after the second upload
- [x] 24.12 Comment blocks over 3 lines shortened (`plan.py`, `render.py` ×2, `tools.py`); `design.md Dn` references in code, tests and eval replaced by a short reason
- [x] 24.13 Package `make code-quality` + `make test`; `fred-performance-reviewer` on the turn path (24.3, 24.4, 24.6, 24.9); `verification.md`
- Deferred (recorded in design D4): analysis rows are never deleted with the instance (no SDK delete hook); the analysis routes answer 404 before the authorisation check

## WP24-frontend. Review fixes: agent form and chat UI

Owns: `apps/frontend/src/rework/` (Dialog, FullPageModal, PatternReviewDialog, usePptBuilderAnalysis, useTeamAgentInstances, part registry, side-panel registry), `COMPONENT-UX.md`, `verification.md`.

- [x] 24f.1 Review fixes committed (`a0cbeb10a` nested Dialog owns Escape over its FullPageModal, `7fbd33d27` rename kept on Enter/Escape, `d46137705` analysis polling survives a failed poll, `6d2579c2b` agent-list polling backs off and stops, `b6b6f61da` NUL byte in the part key, `2a9b38202` focus kept after toggling inclusion, `6ef46ff47` shared side panel offered once, `5edf97cb7` COMPONENT-UX); full vitest 3416 passed

## WP25. Platform review fixes (fred-sdk, fred-runtime, control-plane, docs)

Owns: control-plane `agent_instances/` + `product/service.py` + `product/agent_copy.py` + Alembic `b8e1f4a2c6d9`, fred-runtime `agent_app.py` + `platform_ports.py`, fred-sdk `contracts/runtime.py` + `models.py`, k3d values, contract docs, AUTHORING.md, migration note, `design.md` D3/D5/Migration, delta spec, `verification.md`.

- [x] 25.1 Schema downgrade lifts `capability_pending` suspensions; migration note: rollback = control-plane `alembic downgrade` first. Test: downgrade clears pending rows only, drops the column
- [x] 25.2 Copy asks readiness after create with the caller's token and sends the destination team's routing to `copy-config`, which hands it to the target save. Tests: copy pending while preparing, routing forwarded (control-plane and pod)
- [x] 25.3 Readiness verdicts alone set/clear `capability_pending`: a save/enrol/copy settles in one write (none when ready, else pending; no verdict → pending), 404 reads as ready; a raising hook is `pending`. Tests: save + no verdict, config-invalid → pending in one write, ready clears, raising hook pending, unreadable slice omitted
- [x] 25.4 Listing re-check skips failed preparations, samples over the cap, shares the runtime HTTP client; §8.106/§60 say a hook may start background work and must return quickly. Tests: failed skipped, rotation and one client
- [x] 25.5 Pod capability routes check the named team: validate-config and copy-config (both teams) `CAN_UPDATE_AGENTS`, readiness `CAN_USE_TEAM_AGENTS`; no `team_id` on a secured pod → 422. Tests: 403 for a non-member on each route, member passes with the right permission
- [x] 25.6 Model port re-reads the team's usable models every 30 s. Test: revoked model unused after the TTL, one ReBAC query within it
- [x] 25.7 Readiness writes are compare-and-set on the reason read before the pod call (store-level conditional `UPDATE`, `updated_at` untouched). Tests: stale pending read does not clear a revocation (fake and SQLite store)
- [x] 25.8 Small fixes: (a) `capability_team_authorizer` loaded lazily so fred-sdk has no module-level fastapi import (same public path); (b) k3d values flag Mistral Medium/Small `supports_vision`, note says roll fred-agents first; (c) AUTHORING.md reformatting reverted; (d) `(#1975, …)` dropped from the rewritten `set_suspension` docstring; (e) `model_profile` stock-widget claim removed, clients regenerated, D3 and 1.1b/8.1c corrected; (f) tests: readiness-check permission wiring, copy + readiness, save + no verdict
- [x] 25.9 Verification: `make code-quality` + `make test` in fred-sdk, fred-runtime, control-plane, ppt-filler, fred-agents; frontend tsc + full vitest; single Alembic head; `fred-performance-reviewer` on 25.3, 25.4, 25.6

## WP26. Variety ask counts misfit slides by their closest fit (D17)

Owns: `assign.py` (closest fit, repeat count, options), `tools.py` (ask wording), `design.md` D17/D18/D19, delta spec, tests, `verification.md`.

- [x] 26.1 Variety ask counts misfit slides by their closest fit: on a call with fit problems, a slide that fits nothing is placed for the repeat count on its closest fit or a variant of that kind with no other problem (same caps, structural and revisable rules), so the ask joins its fit problems in the same round; still first call only, never a round of its own. Options and suggestions skip template slides sharing its fit problem (group options: shared by every slide of the group). Tests: repeated slides that each have a fit problem → `slides` and `variety` together, fixed plan with kinds unchanged built with the note; a timeline lacking the same label zone not offered; the existing merged-ask tests now count the slide to fix
- [x] 26.2 Package `make code-quality` + `make test`; `verification.md` (with the PowerPoint check of 24.1)

## WP27. Parallel copies of a build call

Owns: `tools.py` (build entry)

- [x] 27.1 One build at a time per answer; a copy of a call still running (same arguments) is answered "Ignored: …" without a second build, and a different plan sent in parallel waits its turn. Seen live: mistral-small sent the same two-slide call twice in parallel and both built the same file. Test: two identical parallel calls → one write, one "Ignored"; two different parallel plans → both built. Package `make code-quality` + `make test` (426 passed, 5 skipped)

## WP28. Close-kind fallback and actionable messages (D21)

Owns: `assign.py` (close kinds, problems, notes), `tools.py` and `render.py` (message texts), `design.md` D7/D21, delta spec, tests, `verification.md`.

- [x] 28.1 A requested kind falls back only to its close kinds (`CLOSE_KINDS`); with none fitting, `needs_revision` on the requested kind's closest slide (its own largest item count, trim/split, close-kind options), never an unrelated kind; the substitution note says why and how to get the requested kind. Seen live: a 9-item agenda (agenda slide max 8) built on a team slide. Tests: the live case → `needs_revision` "the largest 'agenda' slide holds 8", no team option; 9 items with a process slide of 10 → process with the actionable note; the agenda written as bullets → bullets slide, note "give the bullets as items (at most 8)"; fallback tests updated (cover → section, closing → section, timeline → bullets, process max counted on process slides)
- [x] 28.2 Every message of `build_presentation` and `list_images_in_folder` states what happened, why and one remedy or "nothing to do" (errors, render errors, review notes, repeat notes, skipped entries, unusable images, empty folder, busy, duplicate, repeated problem); success and "Ignored:" prefixes unchanged. Tests asserting exact texts updated
- [x] 28.3 Package `make code-quality` + `make test`; `verification.md`
- [x] 28.4 Renderer findings the after-check report does not carry reach the model in the "To review" notes, each with its remedy (`DeckReport.notes`): agenda gap, one-line overflow, items slide given no items, content on a fixed slide, a table the render cannot fit; findings already in the report stay in the logs (`RenderResult.warnings`, now logged). Tests: exact note texts in `test_builder_render.py` and `test_table_slides.py`, the agenda note in a delivered message (`test_build_tool.py`)

## WP29. Limits phrased in words (D22)

Owns: `plan.py` (`capacity_text`), `assign.py` (shortening options), `tools.py` (catalogue header), `design.md` D22, delta spec, tests, `verification.md`.

- [x] 29.1 One generic rule turns a zone's measured room into a word budget (`floor((chars per line + 1) / 7)` per line × lines, floor 1, "1 short word" under 6 chars per line), quoted before the chars everywhere the model reads a room: catalogue, schema hints, `needs_revision` reasons and options, kind advice. Same rooms, same fit check, no template-specific logic, no sample-text example (D22)
- [x] 29.2 Tests: the wording for 1-word, multi-word, multi-line and under-6-char rooms; a shortening option names words and chars; schema hints and catalogue on the Paintress and built-in references read coherently
- [x] 29.3 Package `make code-quality` + `make test`; eval strictly sequential, WP21 settings (Paintress rules, 14 prompts, `--no-builtin`, `template_slide` max 1): small + stand-in (vs A), medium + stand-in (vs C); `verification.md` with success, first call, calls, figure-label and cover-subtitle too-long problems, decks ×3+, tokens, and a keep/revert recommendation

## WP30. Template preparation guide

Owns: Help Center `guides/prepare-powerpoint-template.md` (fr + en), `PptBuilderTemplatePanel` (guide link), `verification.md`.

- [x] 30.1 Help Center page "Préparer son template PowerPoint" / "Prepare your PowerPoint template" in `guides`, written from the analysis rules (example slides before layouts, one slide per design, the `SlideKind` list, `kind:`/`label:` notes, kind names and shape-name roles, repeat groups, measured room, picture zones and framed pictures, data tables, exclusion reasons, review, re-analysis), with a do/avoid table; linked from the capabilities page and the guides index
- [x] 30.2 A discreet "How to prepare your template?" link at the end of the template card opens the page in the Help Center language matching the app, in a new tab. Tests: the link's text, target and language; the page exists in both languages

## WP31. Review fixes from live use

Owns: `overrides.py`, `assign.py` (problem text), `design.md` D10/D21, delta spec, Help Center guide (one passage), tests, `verification.md`.

- [x] 31.1 A kind override to a real kind makes an `other` slide usable: `apply_overrides` sets `reusable` from the new kind when it differs from the analysed one (the author's choice wins over the one-off verdict, as a `kind:` note does; `other` stays unused; exclusion still applies). The guide's "Check the result" passage says so (fr + en). Test: an `other` slide re-kinded `bullets` is assigned; back to `other`, or the analysed kind repeated on a one-off, it stays unused
- [x] 31.2 `needs_revision` text joins each part once: a forced cover no longer takes the close-kind lead (seen in eval: "cover; ; closest close kind, closest fit, a 'cover' slide"); the lead is `closest fit` or `<why>; closest close kind`. Tests: exact text for a cover-forced misfit and a close-kind misfit
- [x] 31.3 Package `make code-quality` + `make test`; `verification.md`

## WP32. Changes against the previous plan (D23)

Owns: `builder/changes.py` (new: operations and their errors), `builder/deck_plans.py` (new: base-plan store and table), `ppt_builder_migrations` (one revision), `tools.py` (schema, description, messages), `capability.py` (fragment, table), `eval/run_eval.py` + `eval/prompts.py` (second-turn edit), migration note, `design.md` D8/D23, delta spec, tests, `verification.md`.

- [x] 32.1 `changes` operations (`replace`, `insert` after N with 0 = start, `remove`, `edit` of one field path) applied all at once on the base plan's numbering; untouched slides kept as the base's objects; every bad operation reported in one actionable error, nothing built. Tests: each op, mixed ops numbered on the base, inserts after the same slide in order, edit paths (field, element, append, null removes, table cell), every error text, `slides` + `changes` refused
- [x] 32.2 Base plan stored per `(session_id, agent_instance_id)` in `cap_ppt_builder_deck_plan` (one Alembic revision on the capability's own tree, single head) on every evaluated call (needs_revision or delivery), never on an error; read only for a `changes` call, the turn's own last plan from memory first; a failed write logged, not fatal; no base → "send the whole deck in `slides`". Tests: base across two tool instances (turns) on the SQL store, refused plan is the base, error keeps the old base, no base error, write failure still delivers
- [x] 32.3 The resulting plan goes through the normal path; untouched slides byte-identical in the rendered plan; numbering of messages on the new plan; variety ask on the first call and `deck_delivered` unchanged; a `changes` call with the shape of the turn's previous one is applied to that call's base (corrected or identical resend, never applied twice); duplicate parallel guard unchanged. Tests: partial fix after needs_revision delivered, later-turn edit keeps other slides identical, variety ask then same-changes resend built once with one insert, kept success prefixes
- [x] 32.3b Eval fixes: corrected resend of a refused insert applied to its own base (seen: one more copy per call); change slides plain objects in the schema (the inlined slide schema doubled the tool schema); `slides: null` and a single change object read. Tests: corrected insert resend, fix numbered on the refused plan, null slides, schema size guard
- [x] 32.4 Tool description, `needs_revision`, variety ask, delivery and review-note texts, and the working rules name both modes in a few lines (`changes` for a fix or a user's edit, `slides` for a new deck)
- [x] 32.5 Eval: `--edit-turn` adds a second user turn with an edit request per prompt (new tool instance, same conversation and base store); metrics: revision calls using `changes`, edit success, edit calls with `changes`, previous slides kept identical, edit tokens. Run small then medium (stand-in prompt, WP29 settings, strictly one at a time; stop on quota); compare with WP29 "words"
- [x] 32.6 Package `make code-quality` + `make test`; migration note (second table); `verification.md` with the benchmark and a keep/revert recommendation
- Deferred: `cap_ppt_builder_deck_plan` rows are never deleted with their conversation (per-instance data cleanup: issue #2990)

## WP33. A list too long for its kind continues on a slide of the same kind (D24)

Owns: `assign.py` (split, beam, variety counts, notes, cap problem), `render.py` (model numbering, agenda gap, consecutive numbers), `tools.py` (render the parts), `design.md` D21/D24, delta spec, tests, `verification.md`.

- [x] 33.1 Items or table rows over the kind's largest slide continue on parts of the same kind (balanced, at most 2 parts, `(k/n)` title marker, numbering continued), tried before the close kinds; beyond the cap, close kinds then `needs_revision` with the cap options. Tests: 9 agenda items over 8 → 5 + 4 with titles and numbers, explicit numbers kept, a table split with its header, 17 items over 8 → close kind or `needs_revision` with the cap text, bullets never split, a text too long never split
- [x] 33.2 Variety: continuation parts out of the use counts, caps, groups, asks and the three-in-a-row note; the continuation prefers its first part's template slide. Tests: a split list alone never asked, another slide on the same template slide still counted
- [x] 33.3 Messages and stored plan on the model's numbering: render receives the expanded plan with model numbers; the stored base plan is the model's; the agenda gap counts a split agenda once. Tests: split note text, a later slide's note keeps its plan number, `changes` on the stored plan after a split delivery, agenda gap not raised by a split agenda
- [x] 33.4 Package `make code-quality` + `make test`; quick benchmark (mistral-small, WP32 settings, `--edit-turn`), compared with WP32 small run 3; `verification.md`

## WP34. "What was built" next to the deck's download (D25)

Owns: `fill.py` (`PptPreviewPart.summary`, the note models), `builder/checks.py` + `builder/render.py` (per rendered slide record), `builder/tools.py` (summary on the delivered part), frontend `ppt_filler` card + pane header (info button, dialog, `types.ts`), locales fr/en, Help Center presentation page (fr + en), `COMPONENT-UX.md`, `design.md` D25, delta spec, tests, `verification.md`.

- [x] 34.1 The delivered `ppt_preview` part carries an optional `summary`: per rendered slide its plan number, part `k`/`n` of a split list, title as rendered, kind, template slide label, and note codes with small params (no prose). Built from what the render and the tool did, never from the model's reply; absent on `ppt_filler` parts. Tests: a split list (both parts, `list_continued`), a substitution (`other_kind` with the asked kind), a cut text (`text_shortened`), an unusable image (`image_unusable`, pre-assignment and at render), items over the slide (`items_left_out` with the count), a `ppt_filler` part without it
- [x] 34.2 Frontend: an info icon button next to the `.pptx` download (card and pane header), shown only when `summary` exists, opens the central `Dialog` "What was built" / "Ce qui a été construit": slide count, then per slide its number, title (or template slide label), kind label (`capability.ppt_builder.kinds.*`) and plain notes translated from the codes. Tests: no button without a summary; dialog lists slides and notes; fr/en strings; accessible names
- [x] 34.3 Help Center presentation section: one sentence on the info button (fr + en); `COMPONENT-UX.md` entry
- [x] 34.4 Package `make code-quality` + `make test`; frontend `tsc`, `prettier`, `vitest` on the touched files; `verification.md`

## WP35. Live-session fixes: variety re-ask, one numbering, design kept, flattened changes

Owns: `tools.py` (`deck_delivered`, stored deck, delivery text, description), `assign.py` (stored parts rejoined, notes on the file's numbers, template slide kept), `render.py` (messages on the file's numbers), `changes.py` (flattened slide, field messages, `built_on` inherited), `plan.py` (`built_on`), `fill.py` + frontend `types.ts` (summary `number` docs), `design.md` D15/D23/D24/D25, delta spec, tests, `verification.md`.

- [x] 35.1 Variety ask never re-fires after a delivery in an earlier turn: the platform's checkpoint hygiene clears message names before capability middleware, so `deck_delivered` matches a result by the `tool_call_id` of the `build_presentation` call, its text read from a string or text blocks. Tests: a delivered deck seen with names stripped and block content, through the middleware on a later turn (built, no ask); another tool's delivery-like text still no deck
- [x] 35.2 One numbering: after a build the stored plan is the deck as delivered (each continuation part a slide with its rendered title, entries, continued numbers and kind; no non-slide entry); delivery notes and renderer findings name the file's slide numbers; the delivery says later `changes` use them; the summary's `number` is the slide's place in the deck. Stored parts (`X (k/n)`, `X (k+1/n)`) are one list again on a rebuild: never split or suffixed twice, one slide for variety, one template slide. Tests: stored deck equals the rendered one and a later edit numbers on the file without re-splitting; a delivered split rebuilt at max one (no problem, repeat or part, same template slide); notes after a split on the file's numbers (substitution and agenda gap); summary numbers 1..5
- [x] 35.3 Design kept: each stored slide records its template slide (`built_on`); a slide that still fits there with the same kind keeps it; a `replace` gives its first new slide the replaced slide's; the description says to use `edit` for text inside a slide. Tests: a section replaced with new text stays on the template slide it was pinned to, another kind is reassigned; assignment keeps the pinned variant, ignores it for another asked kind or content that no longer fits; `built_on` inherited by the first replacement only; description text
- [x] 35.4 Flattened `changes`: a `replace`/`insert` with slide fields and no `slides` reads them as its one slide; slide fields beside `slides`, or on an `edit`/`remove`, and unknown keys get what/why/remedy messages. Tests: the live shape (`kind`, `title`, `items`) and an aliased insert read; each mixed case's exact message; a flattened replace delivered and stored through the tool
- [x] 35.5 Package `make code-quality` + `make test`; `verification.md`
- Not in scope: undo/revert of earlier plans; the streamed "Vo\nici" glitch
