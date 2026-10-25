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

- [x] 7.1 Author the deck (Q5) with example slides for every kind but `team`/`other` (2026-10-16: the owner's "fred-default-showcase" deck, 45 slides, replaces it; its table body emptied (owner decision A), its kicker lines left out by `ppt-builder-kicker-label` (decision B); the rules analysis finds cover, agenda, section, bullets, two_columns, comparison, cards, quote, image_text, timeline, table, chart (+ full and two-chart slides), figures, process, team, closing; see verification "Built-in deck swap")
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

Owns: `libs/fred-sdk/fred_sdk/contracts/capability/base.py` (`readiness` hook), pod readiness endpoint in `libs/fred-runtime/fred_runtime/app/agent_app.py`, `apps/control-plane-backend/control_plane_backend/agent_instances/suspension.py`, `product/{service,schemas}.py` (post-save and listing checks, `suspension_detail`), its Alembic migration, regenerated `controlPlaneOpenApi.ts`, `AgentFormBody.tsx` / `AgentCard.tsx` reason strings, `CONTROL-PLANE-PRODUCT-CONTRACT.md` entry.

- [x] 10.0 validate-config request carries the team routing fields already built for prepare-execution (profile overrides, chat default, usable model ids, platform binding)
- [x] 10.0b `supports_vision` exposed on `available-models` and `effective-chat-model` responses (regenerated client)
- [x] 10.1 `SuspensionReason.CAPABILITY_PENDING` + nullable `suspension_detail`; pending is not cleared by a save
- [x] 10.2 Optional `readiness(stored)` SDK hook and pod endpoint; control-plane applies it after save and on listings, plus an on-demand re-check the form's poll can trigger
- [x] 10.3 Form/card strings for pending and failed-with-detail; tests in control-plane, fred-sdk, frontend

## WP9. Evaluation and verification (last)

Owns: `libs/capabilities/fred-capability-ppt-filler/eval/` (new), package `Makefile` (`eval` target), `verification.md` (new, this change), package `README.md`, migration note.

- [x] 9.1 Harness: prompts × templates (local "PPT Corporate" template by env var, built-in), real analysis + tool + configured LLM, metrics per D11, JSON + table output
- [x] 9.2 Run it; record results and targets met/missed in `verification.md`
- [x] 9.3 `make code-quality` + `make test` in the package, fred-sdk, fred-runtime, frontend; `fred-performance-reviewer` on the tool path and the per-turn row read
- [x] 9.4 End-to-end on the local stack (upload → status → build → preview/download; no template); README, migration note, issue #2679 status comment — done 2026-10-25: the local stack ran end to end (live revision rounds 2-7 and chart evals r1-r3 build, preview and download through fred-agents, Renoir on the built-in template with no template uploaded; the owner checked upload, analysis status, plan card and build in the browser); README, migration note `docs/swift/ops/migrations/ppt-builder-capability.md` and the #2679 status comment exist (see `verification.md`, Close-out)

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
- [x] 14.4 Checked in the browser on the Paintress agent (switch inside the card, no gap above the kind select); frontend checks as tsc/prettier/eslint/scoped vitest (no `make` while Vite runs) — done 2026-10-25: the owner checked the Paintress form in the browser; frontend checks recorded under WP14 in `verification.md`

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
- [x] 25.4 Listing re-check skips failed preparations, samples over the cap, shares the runtime HTTP client; §8.120/§69 say a hook may start background work and must return quickly. Tests: failed skipped, rotation and one client
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

## WP36. Live-session fixes: "same design as slide N", changes that change nothing

Owns: `changes.py` (`like` edit field, `unchanged`), `plan.py` (`asked_design`, `asked_from`, `DeckPlan.delivered`), `assign.py` (asked design alone, out of variety), `tools.py` (description, no-change answer, stored deck flags), `design.md` D23, delta spec, tests, `verification.md`.

- [x] 36.1 `{op: "edit", slide: N, field: "like", value: M}`: slide N takes slide M's delivered template slide (base plan's `built_on`, whatever the call changes on M; first new slide of a replaced N; kind cleared unless set by the call); offered alone and out of variety asks; `needs_revision` with slide M's design, the misfit or kind, and the remedy; bad references as change errors; description and `changes` schema text name `like`. Tests: the live reproduction (bullets slides 5 and 7 on different template slides, `like` makes them share, stored pin, hidden fields cleared), items on a bullets design and a conflicting kind as revisions, every bad reference's message, resolution against the base and on a replaced slide, five slides asked on one design at max 1 with no repeat
- [x] 36.2 Changes that leave a delivered deck's content and template slides as they are build nothing and return a "nothing changed" error with why and the remedies; a plan stored by `needs_revision` is never treated so. Tests: the live no-op (kind + same bullets), an identical replace, a `like` on the design already held; no render, write or store; a new file name still builds
- [x] 36.3 Package `make code-quality` + `make test`; `verification.md`
- Not covered: a live re-run of the session

## WP37. Name each slide's design in the delivered message

Owns: `tools.py` (delivered text), `design.md` D23, delta spec, tests, `verification.md`.

- [x] 37.1 Both success texts carry one `Designs:` line: per file slide (a split list's parts included), the template slide's label as the review and summary show it, cut past 28 chars, suffixed `#2`, `#3`… when several included template slides share a label; then one sentence: different names look different, `like` gives slide N slide M's design. Tests: file numbers with a split process list, three bullets slides on three template slides read as three names, a shared label made distinct, a long name cut
- [x] 37.2 Package `make code-quality` + `make test`; `verification.md`
- Not covered: a live re-run of the session


## WP38. Review fixes: stored base, resend rule, hidden fields, design pin, numbering

Owns: `tools.py` (stored base, resend state, hidden fields, designs line, variety ask timing), `changes.py`, `plan.py` (`HIDDEN_FIELDS`), `assign.py` (`_kept`, `Assignment.starts`, `_rejoin`), `render.py` (continuation numbering, `RenderResult.warnings` deleted), `deck_plans.py` (docstring), frontend `DeckSummaryButton.tsx`, `PptPreviewCardRenderer`, `PptPreviewPane`, `COMPONENT-UX.md`, `design.md` D15/D17/D23/D24 and the message rule, delta spec, tests, `verification.md`.

- [x] 38.1 Only a delivered deck is stored as the next turn's base; a refused plan (`needs_revision`, variety ask) stays the turn's in-memory base. Tests: a refused change leaves the store as delivered and the next turn changes the delivered deck; resent changes never applied twice, nothing stored
- [x] 38.2 A delivery clears the corrected-resend state: the same changes sent after a delivered deck are a new change. Test: two inserts of one shape in one turn, both delivered, both in the deck
- [x] 38.3 `built_on`, `asked_design`, `asked_from` are dropped from every sent slide (`slides` and change slides). Test: a model-written pin on a section template slide ignored in `slides` and in a `replace`, stored pin is the chosen one
- [x] 38.4 The design pin holds whenever the template slide is among the best-ranked kind's fits, a substituted kind included. Test: a timeline built on either of two process slides stays on it
- [x] 38.5 The `Designs:` line numbers duplicates on the shown (cut) label. Test: two long labels cut to the same text read `…` and `… #2`
- [x] 38.6 A `changes` call (always on a delivered base) is never asked to vary, even with a trimmed history. Test: a later-turn insert making a template slide repeat is built with the note only
- [x] 38.7 A continuation is numbered at render from `Assignment.starts` (a delivered split included); generated numbers are never stored. Tests: unnumbered steps split 3 + 2 render `1 2 3` / `4 5`, store no number, and render `1 2` / `3 4` after a later change removes a step from part 1; assignment `starts` before and after
- [x] 38.8 The turn's variety ask is used only once a plan is evaluated. Test: an empty first call, then a repeated deck, still asked
- [x] 38.9 `RenderResult.warnings` deleted (it only fed a log line; every finding is in `DeckReport`). Render tests read the report as the agent does
- [x] 38.10 Frontend: the summary info button is `size="small"` like download and close; info, download and close sit in a gapless group (card and pane headers). Test: the button's small size class; `COMPONENT-UX.md` updated
- [x] 38.11 Package `make code-quality` + `make test`; frontend `tsc`, `prettier`, `eslint`, `vitest` on the touched files; `verification.md`; `openspec validate`
- Not covered: a live re-run with a real model; the gapless header has no automated check (CSS only)

## WP39. Live-session fixes: a kind edit's leftovers, actionable drops, identical resends

Owns: `changes.py` (`CLEARABLE`, kind-edit clearing), `assign.py` (`unplaced`), `tools.py` (cleared notes, drop ops, refused-call guard), `design.md` D23 and the message rule, delta spec, tests, `verification.md`.

- [x] 39.1 An `edit` that changes a slide's kind clears the fields no template slide of that kind has a place for beside the rest, unless the same call sets them; the delivery notes or the `needs_revision` lead say what was cleared. Tests: the live session's three edits (kind, title, columns) build a two_columns slide without its bullets and the note; a field the call sets and a same-kind edit clear nothing
- [x] 39.2 In `changes` mode a `drop <field>` option carries its exact `edit` (`[]` for a list, null otherwise); `slides` mode keeps the words. Tests: both modes' option text; the given change clears the field and the deck builds
- [x] 39.3 A call identical to one refused with fit problems this turn, on the same base, is answered without evaluation (same call, the problems, `replace` or drop the change). Tests: no second assignment in either mode, the message, a `replace` then builds; the resent-unchanged flag and the never-applied-twice tests now resend with another `file_name`
- [x] 39.4 Package `make code-quality` + `make test`; `verification.md`; `openspec validate`
- Not in scope: the runtime's handling of the per-turn tool-call cap (reported to the developer, no runtime change)
- Not covered: a live re-run of the session

## WP40. Live-session fixes: parallel fragments, fragment remedy, identical resend

Owns: `capability.py` (`awrap_tool_call`), `tools.py` (`round_refusal`, unchanged resend, `_DUPLICATE` and the argument-keyed guard deleted), `assign.py` (`continuing` remedy), `design.md` D26 and the message rule, delta spec, tests, `verification.md`.

- [x] 40.1 Several `build_presentation` calls in one assistant message: the middleware runs the first in the message's order and refuses the others before the tool, naming the first and pointing to one call or `changes`. Tests: three different fragments gathered, one run and delivered, two exact refusals; an identical copy refused, a single call run, a call absent from the state untouched
- [x] 40.2 A `slides` plan without a cover after a delivered deck (this turn or the history) gets the `changes` remedy as its only option. Test: the same fragment before and after a delivery, both option lists (deleted by WP57: no cover is forced)
- [x] 40.3 A `slides` call equal to the deck delivered this turn is answered "unchanged, deck already delivered as '<file>'" with no render, upload or preview. Tests: render counter unchanged, one write; another file name or content renders; the WP27 parallel-copy test now expects the copy answered as unchanged
- [x] 40.4 Package `make test`, `ruff check`, `ruff check --select I`, `ruff format --check`, basedpyright with baseline; `verification.md`; `openspec validate --strict`
- Not covered: a live re-run of the session

## WP41. Live-session fixes: revisions are not errors, the next call, parallel sections

Owns: `tools.py` (`_answer`, `_NEXT_CALL`, the variety ask and choice guide), `capability.py` (working rules, round refusal), `assign.py` (`_places`, mirrored uses in `_beam` and `_repeats`, `_wants_picture`), `design.md` D27, delta spec, tests, `verification.md`.

- [x] 41.1 Fit and variety `needs_revision`, the identical-resend guard, the round refusal, "nothing changed" and "unchanged, deck already delivered" are non-error results with the same text and payload; bad calls, load/busy/render/upload failures and an analysis not ready stay errors. Tests: each revision path asserts `not is_error` (fit, variety, merged, `changes`, design pin, identical resend still evaluated once, round refusal, unchanged); the empty plan and the bad changes stay errors
- [x] 41.2 Every revision text and the working rules say the very next message must be a new `build_presentation` call with the fixes, never a final answer, unless the user must decide something. Tests: the fit and variety texts, the system prompt
- [x] 41.3 A template slide with a framed picture area is never offered (variety option, suggestion, fit close kind) to slides without an image. Tests: a picture-per-item `cards` variant neither offered nor suggested, a plain one suggested; a framed `image_text` close kind offered only with an image
- [x] 41.4 Parallel sections: uses at the same place of different sections (`section` slides, else agenda entries) count once, in the ask and the beam; repetition inside a section still counts. Tests: three mirrored sections accepted, each keeping the first's design, the same slides without sections a repeat; three uses in one section revised, mirrored or not; an unmirrored place counted on its own; agenda boundaries with and without matching titles (superseded by 42.1)
- [x] 41.5 Package `make test`, `ruff check`, `ruff check --select I`, `ruff format --check`, basedpyright with baseline; `verification.md`; `openspec validate --strict`
- Not in scope: the runtime replacing the model's answer after an error result (separate runtime fix, `libs/fred-runtime` untouched)
- Not covered: a live re-run of the session

## WP42. The variety limit per section, `repeat_layout` (owner decision 2026-10-14)

Owns: `assign.py` (`_sections`, `_caps`, `_beam`, `_runs`, `_repeats`, `SECTION_RULE`), `plan.py` + `changes.py` (`repeat_layout`, aliases, edit path), `tools.py` (description, summary notes), `fill.py` (note codes), frontend summary notes + variety copy + Help Center, `design.md` D27, delta spec, tests, `verification.md`.

- [x] 42.1 The max uses count within each section (section slides, else agenda entries; fewer than two sections = one); the counts reset at each section, in the ask and the beam; the realistic cap is computed on the largest section; alternatives read from the sections concerned. Replaces the "same place in mirrored sections" rule of 41.4. Tests: twice in Italy at 2/4 and twice in Spain at 1/3 accepted (the same slides flat a repeat); three uses in one section revised; agenda boundaries unchanged
- [x] 42.2 Three identical template slides in a row, across a section boundary too, are a repeat (`in_a_row`) when the beam cannot avoid them, unless already listed over their cap; the passive note with the check off is unchanged. Tests: a run across agenda sections revised; a one-template-slide deck noted as a run, its off-mode note kept
- [x] 42.3 `repeat_layout`: the slide keeps the previous slide's template slide when it fits, is outside the cap and never ends a run; notes to the agent and `layout_repeated` / `layout_not_repeated` in the summary; `edit` path, shorthand and loose names/values. Tests: the run with the field accepted and noted; kept outside a cap of 1; content that cannot keep it noted; the edit forms; the summary codes; fr/en wordings
- [x] 42.4 Package `make test`, `ruff check`, `ruff check --select I`, `ruff format --check`, basedpyright with baseline; frontend `tsc`, vitest, prettier, eslint; `verification.md`; `openspec validate --strict`
- Not covered: a live re-run with a real model

## WP43. Library slides excluded from design choice (owner decision 2026-10-14, D28)

Owns: `analysis.py` (`_apply_exclusions`, `ANALYSIS_VERSION`), `lexicon.py` (`is_library_title`), `models.py` (`ExclusionReason`), frontend ppt_builder client + fr/en exclusion labels, delta spec, `design.md` D28, tests, `verification.md`.

- [x] 43.1 A resource-page title or twenty-plus small text-free pictures, groups or freeform glyphs exclude an example slide with the reason `library`; the `icon_bank` rule folded in; `ANALYSIS_VERSION` bumped. Tests: a synthetic icon sheet and fonts sheet excluded as `library`, a content slide with four icons and a dotted row kept as designs, the closing slide kept
- [x] 43.2 The ppt_builder client regenerated and fr/en labels for `library` (`make update-ppt-builder-capability-api`)
- [x] 43.3 Run on the owner's Paintress Cyan template: library slides before/after
- [x] 43.4 Package `make test`, `ruff check`, `ruff check --select I`, `ruff format --check`, basedpyright with baseline; `verification.md`; `openspec validate --strict`
- Not in scope: listing or reusing a library slide's icons (later change)

## WP44. A list over its zone's entry limit says so (live session 2026-10-14)

Owns: `plan.py` (`MIN_FONT_SCALE` moved here, `max_entries`, `list_capacity_text`, `_limit`, `field_hints`), `render.py` (`_line_cost`, `floor_lines`, shared with `_fit`), `assign.py` (`_too_long`), delta spec, tests, `verification.md`.

- [x] 44.1 A list refused for more entries than its zone holds names the count and the limit, with "merge into at most N, or use another kind"; a count that fits but wraps names lines taken vs lines held, with "keep each entry to one line". The fit computation is unchanged. Tests: 3 bullets in a 1-line zone, 3 in a 2-line zone, 4 column entries in a 1-line column, a long entry in a count that fits
- [x] 44.2 The description and schema hints quote `bullets` and `columns.bullets` with their lines and max entries (`≈101 chars × 1 line, max 1 entry`). Test: `zone_summary` for both fields
- [x] 44.3 Package `make test`, `ruff check`, `ruff check --select I`, `ruff format --check`, basedpyright with baseline; `verification.md`; `openspec validate --strict`
- Not covered: a live re-run with a real model

## WP45. A re-run's new analysis reaches the review dialog (owner session 2026-10-14)

Owns: `analysis_job.py` (`AnalysisStatusResponse.refreshing`), the frontend ppt_builder folder (`usePptBuilderAnalysis`, `AnalysisStatus`, `PatternReviewDialog`, `effectiveInventory`), the regenerated client, fr/en `analysis.refreshing`, delta spec, tests, `verification.md`.

- [x] 45.1 The status reports `refreshing` while an outdated analysis is re-read (it stays `succeeded` and `current`, its old inventory served). Tests: the flag during and after a refresh, after a failed one, and on the re-run route
- [x] 45.2 The form polls while `refreshing`, says the template is being read again, and shows the new inventory when the refresh ends. Tests: the hook's polling and inventory swap, the status line
- [x] 45.3 The review's excluded section opens when the analysis set slides aside (`library`, `table`…); an author exclusion of such a slide keeps the analysis reason. Tests: dialog sections, `effectiveInventory`
- [x] 45.4 Package `make test`, `ruff check`, `ruff check --select I`, `ruff format --check`, basedpyright; frontend tsc, prettier, eslint, the folder's vitest; `openspec validate --strict`
- Not covered: an override copied from another agent keeps its label (author data, shown as is)

## WP46. Heuristic kinds for Google Slides exports (owner decision 2026-10-14)

Owns: `analysis.py` (`_pair_group`, `_pairs`, `_lone_figure`, `_item_order`, `_resource_sheet`, `_placeholder_role`, `_group_kind`, `_kind`, `_sequential`, `ANALYSIS_VERSION` 14), `lexicon.py` (`is_figure`, `is_date_sample`, `is_url`), the built-in inventory, delta spec, tests, `verification.md`.

- [x] 46.1 Repeated (heading, text) pairs of two size classes, placeholders typed TITLE/SUBTITLE included, become one repeated group: `cards`, `figures` (figure headings, `label` captions), `timeline` (years, "20XX"); numbered texts on a grid are `cards`. Two plain pairs stay a `two_columns` slide's headings and bodies; a lone big figure is a one-item `figures` slide. Tests: synthetic Google-style cards, two ideas, big figures, big number, numbered grid, staircase timeline
- [x] 46.2 A SUBTITLE placeholder covering a fifth of the slide is a body (no paragraph slide is a cover); a text repeated on other slides stays a slot beside two same-size slots. Tests: paragraph subtitle slide, a timeline entry reused on another slide
- [x] 46.3 A slide with no placeholder and no text but links that draws eight or more shapes, or a linked picture, is excluded as `library`; an empty slide stays `other`. Tests: graphic sheet, promo, empty slide
- [x] 46.4 Before/after classification of Paintress Cyan, Paintress, the built-in template and the corporate reference; a Thales Italy/Spain deck rendered on Cyan before/after; `make builtin-inventory`
- [x] 46.5 Package `make test`, `ruff check`, `ruff check --select I`, `ruff format --check`, basedpyright with baseline; `verification.md`; `openspec validate --strict`
- Not in scope: why vision did not run on these templates (a re-run after a restart has no model port, see verification), the capacity of Cyan's timeline texts (1 line)

## WP47. Re-runs go through the save, the only path with the model port (owner decision 2026-10-15)

Owns: `analysis_job.py` (`recover_interrupted`, `run_analysis`, `restart_from_stored`), `capability.py` (the re-run route deleted), the frontend ppt_builder folder (`usePptBuilderAnalysis`, `AnalysisStatus`), the regenerated client, fr/en `analysis.*` and Help Center wording, `COMPONENT-UX.md`, delta spec, tests, `verification.md`.

- [x] 47.1 Delete `POST /analysis/{instance_id}/rerun` and the form's "Re-run analysis" button: the form says that saving the agent re-runs a failed, interrupted or outdated analysis, which the save already does with its model port. Tests: a save after a restart (no cached port) re-runs a failed and an outdated vision analysis with vision; route and component tests trimmed
- [x] 47.2 A readiness check or turn does not recover an interrupted vision analysis without the port: it stays interrupted until a save. Test: no job, `interrupted`, then a save relabels with vision
- [x] 47.3 A job that runs a vision key without a port logs a WARNING and stores `rules`. Test: forced refresh without the port
- [x] 47.4 Package `make test`, `ruff check`, `ruff check --select I`, `ruff format --check`, basedpyright with baseline; frontend tsc, prettier, eslint, the folder's vitest; `openspec validate --strict`
- Not covered: a live save-based re-run in the browser

## WP48. The preparing banner says what is being prepared (owner decision 2026-10-15)

Owns: the shared `capabilityPreparingKey` helper, `AgentCard`, `AgentFormBody` (pending message), fr/en `rework.agentCard.preparing*`, `rework.teams.formAgent.suspended.pending*`, `capability.ppt_builder.preparing`, Help Center wording, `COMPONENT-UX.md`, `AUTHORING.md`, the SDK `readiness` docstring, delta spec, tests, `verification.md`.

- [x] 48.1 A capability with a readiness hook names its pending work under the frontend locale key `capability.<id>.preparing`; ppt_builder ships "reading the PowerPoint template." No backend change: `suspension_detail` stays the failed-only message (its null is the pending/failed discriminant for the listing re-check and the UI), and which capability is pending is not persisted
- [x] 48.2 The card and the form show "Preparing — {detail} The agent will be available again automatically in a few minutes." when exactly one of the agent's capabilities declares a key, else the generic "Preparing — … Nothing to do on your side."; the form title becomes "This agent is temporarily unavailable." Tests: helper, card with detail and fallback
- [x] 48.3 Frontend tsc, prettier, eslint, vitest on the touched files; `openspec validate --strict`
- Not covered: the banner in the browser

## WP49. Built-in deck for every kind; an unused item's layout decoration goes (owner mandate 2026-10-17)

Owns: `render.py` (`_decoration_fate`, `_mark_of`, `_lift_layout_graphics`, `_layout_draws_for`, `_recentre_items`), `assets/fred_template.pptx` and its inventory, the secrets baseline digest, tests (`test_item_decoration.py`, built-in expectations), Help Center fr/en (template guide), delta spec, `verification.md`.

- [x] 49.1 An unused item takes with it the frame around it and what it holds, a mark just above or beside it and its connectors, whether the slide or its layout draws them: the layout's graphics are copied onto that slide only when one of them serves an unused item, the layout's hidden there; kept items move with theirs. Tests: frame and icon, numbered tiles over columns, connectors between kept and to an unused item, line/background/footer mark kept, Four Cards with 3 items (3 cards, 3 tiles, master marks kept), all four used (layout untouched), timeline with 4 dates and 4 dots
- [x] 49.2 Built-in deck v3 (`fred-default-v3.pptx`, owner's deck edited by lxml, untouched parts byte for byte): agenda as seven grouped (number, heading) entries; section `number`/`subtitle` shape names; timeline dates as years under the 12 % field gap, so each milestone is (number, heading, body); a 5-column table with 8 body rows; statements named title/subtitle with `kind: quote`; Three Columns, Process Three and Three Images fields under 40 % high so each column is one item (Three Images items carry their picture); the chart and matrix takeaway cards drawn as the zone's own fill; KPI samples read as figures; notes `kind:` for the light and picture covers (cover), the dark flow (process), Code and Big Number (other)
- [x] 49.3 Exhaustive showcase decks built in process through the build tool and converted by LibreOffice (every kind, cards 2/3/4/6, timeline 3/4/5, table with total row and highlighted column, figures with trends, eleven chart types, two charts, chart with figures, takeaways shown); expectations updated for the deck only (5 columns, 16-row continuation, "6 columns given, max 5", the layout's step tiles now on the slide)
- [x] 49.4 Package `make code-quality` and `make test`; Help Center fr/en: item height limit, item decoration on the layout, a card behind an optional zone as its fill
- Not in scope (recommended): a big number beside a title as a one-item `figures` slide (analysis), section numbers filled at render, a filled picture placeholder cropped to its shape instead of fitted inside, a bare chart preferring the full-width chart slide

## WP50. Section numbers and cropped pictures (owner decision 2026-10-17, design D29)

Owns: `render.py` (`_place_text`, `section_number`, `_numbered`, `_place_image`, `_crop_to_fill`, `_recentre_items`), `plan.py` / `changes.py` (slide `number`), tests (`test_section_and_picture_fill.py`, `test_deck_changes.py`), delta spec, `verification.md`.

- [x] 50.1 A section slide's number zone shows its ordinal among the deck's sections, padded like the example; a plan `number` is kept. Test: three sections, the second numbered "07" → 01, 07, 03 (fails before: the zone is removed)
- [x] 50.2 A filled picture zone is centre-cropped to its frame, in the frame's shape, alt text kept. Tests: four wide team photos cropped 25 % each side, no geometry of their own (the layout's ellipse), alt text kept; cover and image_text pictures fill their frames (fail before: letterboxed rectangles)
- [x] 50.3 A recentred item moves each shape once. Test: three team members, each photo centred on its name (fails before: off by half a step)
- [x] 50.4 Showcase decks re-rendered on the built-in template and checked as PNG (`~/fred-tmp/default-template/v3-fixes/`): sections numbered, cover, section image, image_text and team pictures filled, team photos round and centred

## WP51. Shared picture slots and empty text boxes (owner decision 2026-10-17, design D30)

Owns: `analysis.py` (`_placeholder_key`, `kicker_keys`, `_records`, step 2 of the slide zones, `ANALYSIS_VERSION`), `render.py` (empty text zones), the built-in inventory, tests, delta spec, `verification.md`.

- [x] 51.1 Two placeholders sharing an idx get distinct keys where records are read, the first in drawing order keeping `ph:<idx>`, so a group's picture slots are each filled. Test: three (picture, text) columns whose first two picture slots share an idx, filled with three pictures, each at its slot's position (fails before: the build raises; then the pictures took their layout idx's position)
- [x] 51.2 A text zone left empty is removed, placeholder or text box. Test: a navy panel box beside the body, given nothing (fails before: emptied but drawn)
- [x] 51.3 Reproduced and re-rendered on the original Thales template (slide 12) and the showcase decks (`~/fred-tmp/bugfix-1017/`), PNG looked at

## WP52. Builder fixes from the revision evals (owner decision 2026-10-17 overnight, design D31)

Owns: `plan.py` (`single_columns`), `changes.py` (`_not_a_list`, one edit per field, `after_the_cover`, `deck_delta`), `assign.py` (`_dropped_text`, `_one_point_over_columns`), `render.py` (`column_split`, closing body, unnumbered closing, `_figure_heading`, `_plain_symbol_bullets`), `tools.py` (cover note, delta line), tests, delta spec, `verification.md`.

- [x] 52.1 `columns` sent as one object is refused with the list form; an edit of a list of objects with one object, and two edits of one field of one slide, are refused. Tests: `test_columns_sent_as_one_object_are_a_problem_not_one_column`, `test_an_edit_of_a_whole_list_with_one_object_is_refused`, `test_two_edits_of_one_field_on_one_slide_are_refused`
- [x] 52.2 Bullets on a two-column slide split at a top-level point; one point with sub-points is a misfit there. Test: `test_bullets_over_two_columns_keep_each_point_with_its_sub_points` (deleted by WP58: a two-column slide takes `columns` only)
- [x] 52.3 An insert at `after` 0 of a deck opening on its cover goes after the cover, with a note. Test: `test_an_insert_at_the_start_goes_after_the_cover` (deleted by WP57: `after` 0 means first)
- [x] 52.4 Wingdings 3 bullets drawn as `►` in the preview copy only. Test: `test_preview_copy_draws_wingdings_3_bullets_the_delivered_deck_keeps`
- [x] 52.5 A closing's lone body holds its bullets; a closing on a section slide is unnumbered. Test: `test_a_closing_holds_its_bullets_and_on_a_section_slide_takes_no_number`
- [x] 52.6 A key figure's label reads under its heading when the card has no label zone. Test: `test_a_figures_label_reads_under_its_heading_without_a_label_zone`
- [x] 52.7 The delivery names the slides changed, added and removed since the previous delivered deck. Tests: `test_the_delta_names_changed_added_and_removed_slides`, `test_a_revision_result_says_which_slides_changed`
- [x] 52.8 Eval calls replayed offline and rendered by LibreOffice (`~/fred-tmp/revision-evals/fixes/`), PNG looked at; package checks; `openspec validate --strict`
- Not changed: parallel build calls (already one build per round and a per-tool lock; the 4-slide deck was the model splitting its deck); a corrected `changes` resend whose shape changed applies to the refused plan (default r14 `after` 0 → 1); the built-in matrix's axis labels read as `columns.bullets×3 1 short word` (analysis; fixed in WP54)

## WP53. Agent guidance from the revision evals (owner decision 2026-10-17 overnight, design D32)

Owns: `builder/capability.py` (`_BUILD_INSTRUCTIONS`, `build_instructions`), `tools.py` (tool and `slides` descriptions, delivery text), `changes.py` (`after` description, `deck_delta` lines), tests, delta spec, `verification.md`. Figures: `ppt-builder-storytelling` 3b.

- [x] 53.1 Working rules name the template in use (built-in or uploaded in the agent's settings) and say the tool cannot switch it. Test: `test_plan_validation.py::test_the_working_rules_name_the_template_and_keep_revisions_truthful`
- [x] 53.2 Working rules for revisions: only what was asked (extras proposed), `changes` for the slides concerned, ask which slide when none is named, claim a build only after a delivery in this answer and describe only what the result lists, say when nothing needed changing. Same test
- [x] 53.3 `after` 0 described as "first, after the cover" (tool description, `SlideChange.after`, the missing-`after` problem); `slides` described as a new deck or a rewrite of most slides. Tests: `test_the_tool_tells_the_agent_one_call_builds_the_whole_deck`, `test_every_bad_change_is_reported_with_its_remedy`
- [x] 53.4 Delivery: "none changed: tell the user the deck is the same"; a `slides` resend touching at most two slides of a larger deck adds "send only `changes` next time". Tests: `test_the_delta_names_changed_added_and_removed_slides`, `test_a_whole_deck_resent_for_a_small_edit_is_pointed_to_changes`, `test_a_small_edit_resent_as_a_whole_deck_is_built_and_pointed_to_changes`
- [x] 53.5 Live re-evaluation of the 30 revision requests on both templates once fred-agents runs this code (not restarted by this change) — done: round 2 (2026-10-18, fred-agents with WP53), 30 requests x 2 templates: default 11/12/7, Thales 15/7/8 pass/partial/fail; round 4 (2026-10-23, mistral-medium) 42/11/6/1 NE of 60

## WP54. Vertical text measured along its height (owner decision 2026-10-17 overnight)

Owns: `analysis.py` (`FrameMetrics.vertical`, `_frame_metrics`, `estimate_capacity`, `ANALYSIS_VERSION` 19 → 20), the built-in inventory, tests, `verification.md`. Template unchanged: a `keep`-named axis would be swept as leftover example text, and fixed axis words would not match another matrix's content.

- [x] 54.1 A text box whose `bodyPr` (own or inherited) sets `vert` other than `horz` swaps width and height in its capacity, so the built-in matrix's vertical axis is ≈54 chars × 1 line, not ≈1 char × 19 lines. Test: `test_builtin_template.py::test_vertical_text_is_measured_along_its_height`
- [x] 54.2 Built-in inventory regenerated (`make builtin-inventory`, matrix zone only); a matrix slide rendered before/after by LibreOffice (`~/fred-tmp/revision-evals/fixes/matrix/`), PNG looked at; package checks; `openspec validate --strict`

## WP55. Revision fixes, round 3 (owner decision 2026-10-18: universal builder rules only, design D33)

Owns: `changes.py` (`apply_changes` origins and `move`, `deck_delta` pairing, render compare, notes-only, moves, fewer points), `tools.py` (turn base, refusal numbering, both-modes refusal, render hashes), `pptx_archive.py` (`slide_fingerprints`), `plan.py` (`rendered`), `render.py` (`RenderResult.fingerprints`), `assign.py` (`_asked` empty picture area), tests, delta spec, `verification.md`.

- [x] 55.1 A refused `changes` call leaves no trace: the next call applies to the deck the refused one applied to, of any shape; refused slides numbered on that deck. Tests: `test_a_refused_changes_call_leaves_no_trace`, `test_numbers_in_a_revision_are_the_deck_the_changes_apply_to`, updated `test_a_corrected_resend_of_refused_changes_replaces_them`, `test_the_same_changes_resent_are_never_applied_twice`, `test_a_call_identical_to_a_refused_one_is_not_evaluated_again`
- [x] 55.2 The delta pairs a run of differing slides by shared words, in order. Test: `test_the_delta_names_the_slide_a_resend_dropped`
- [x] 55.3 The delta compares rendered slides (per-slide hash of the delivered file). Tests: `test_the_delta_compares_what_the_slides_render`, `test_a_slide_moved_by_a_removal_renders_unchanged`
- [x] 55.4 `like` onto a design with a picture area for a slide with no picture is refused. Test: `test_a_picture_design_asked_for_a_slide_without_picture_is_refused`
- [x] 55.5 A change that reached only the speaker notes is listed as such. Test: `test_a_change_only_the_speaker_notes_show_is_said_so`
- [x] 55.6 A changed slide on another design with fewer points is listed with both counts. Test: `test_the_delta_counts_the_points_a_recast_slide_lost`
- [x] 55.7 A layout change through `changes` is no longer pinned to a refused `like` (consequence of 55.1). Test: `test_a_refused_like_never_pins_a_later_edit`
- [x] 55.8 `slides` and `changes` together: one line naming the one to send. Test: `test_no_base_both_modes_and_bad_changes_build_nothing`
- [x] 55.9 `move` op in `changes`; the delta lists moved slides. Tests: `test_move_puts_a_slide_after_another`, `test_a_moved_slide_is_built_and_listed_as_moved`, `test_every_bad_change_is_reported_with_its_remedy`
- [x] 55.10 Eval calls replayed offline; LibreOffice render for the visual items (`~/fred-tmp/revision-evals/fixes/r3/`), PNG looked at; package checks; `openspec validate --strict`
- Not changed (not universal, D33): a process `number` too long for its banner (a growing zone, no capacity); content the agent itself wrote in `notes` on a slide that also changed visibly (default r10)
- [x] 55.11 Live re-evaluation once fred-agents runs this code (not restarted by this change) — done: round 3 (2026-10-18, 60 runs, mistral-medium): 37/16/6 +1 NE (round 1: 24/26/10)

## WP56. Audit fixes: silent losses and prompt/tool contradictions (owner decision 2026-10-18: audit fixes, design D34)

Owns: `changes.py` (`_overlap`, `_on_the_base`), `plan.py` (`read_number`, `_decimal`, `_required`), `lexicon.py` (`_FIGURE`), `assign.py` (`_weigh` picture zones, `_asked`, `_wants_picture`), `capability.py` (`_OUTLINE`, `build_instructions`), `tools.py` (`skip_plan` behind the gate, refusal wording), tests, delta spec, `verification.md`. Audit: `~/fred-tmp/revision-evals/AUDIT-2026-10-18.md`.

- [x] 56.1 (H7) Several edits of one slide in one call: every list index means the base slide's entry (sets and appends upward, deletes downward); a path inside another edit's path (`bullets` and `bullets[1]`, `items[1]` and `items[1].label`) is refused. Test: `test_deck_changes.py::test_list_indexes_in_one_call_are_the_base_slides`
- [x] 56.2 (H8) A typographic minus (U+2212) reads as a minus in chart data and figures; `0,125` / `0.125` read as decimals. `3.141` stays a thousands reading (ambiguous). Test: `test_chart_slides.py::test_a_typographic_minus_and_a_leading_zero_decimal_read_as_written`
- [x] 56.3 (H15) Any picture zone left empty is a misfit (framed or not, slide or item level), with the option to give a picture or use another kind; the `like`-only check and the empty-picture cost are deleted; the catalogue marks every picture zone `(required)`; Help Center template guide (fr+en) updated. Tests: `test_deck_changes.py::test_a_picture_kind_without_picture_never_gets_an_empty_picture_area`, `test_assign.py::test_an_image_pattern_is_not_chosen_for_a_plan_without_images`, `test_empty_item_pictures_are_a_misfit_like_empty_slide_pictures`
- [x] 56.4 (H6, with M12) After needs_revision the working rules defer to the result; a refused `changes` call (ChangeError, identical call) asks for every change again. Spec base sentence and the turn-base comment match the code. Tests: `test_plan_validation.py::test_a_refused_call_is_resent_as_its_result_says`, `test_deck_changes.py::test_no_base_both_modes_and_bad_changes_build_nothing`
- [x] 56.5 (H13) With `validate_plan` on, the working rules say the tool shows the outline (never one written in the chat); `skip_plan` is in the schema only then. Test: `test_plan_validation.py::test_the_plan_gate_is_visible_to_the_model_only_when_it_is_on`
- [x] 56.6 Medium Thales r22 replayed offline and rendered (`~/fred-tmp/revision-evals/fixes/audit/H15/`), PNG looked at; package checks; `openspec validate --strict`
- Not changed: L16 (one number reader for story, plan and lexicon: story already reads U+2212 and both readings, a merge is its own change); M29 (any reply to a proposed outline counts as approval); M22/M23 (refused plan dies with the turn; recoverable mistakes returned as tool errors)
- [x] 56.7 Live re-evaluation once fred-agents runs this code (not restarted by this change) — done: round 3 (2026-10-18), 37/16/6 +1 NE of 60

## WP57. Judgement leaves the builder: the cover (owner decision 2026-10-18: judgement moves to the LLM, design D35)

Owns: `assign.py` (`_allowed`, `_tiers`, `_problem`, `_asked`, `_substitution`, `_CONTINUE_DELIVERED` deleted, `has_cover`/`continuing` parameters deleted), `changes.py` (`after_the_cover`, `AFTER_THE_COVER` deleted, `after` description), `render.py` (cover substitution exemption), `tools.py` (cover rule and `after` 0 wording, `continuing`), tests, delta spec, `verification.md`. Storytelling deletions of the same lot: `ppt-builder-storytelling` task group 5.

- [x] 57.1 (H16) No forced cover: the cover may only be slide 1; a kind-less slide 1 holding only a title and subtitle takes it; any other first slide keeps its kind or content shape. The fragment-after-delivery refusal and the "add a cover slide" option are deleted. Tests: `test_assign.py::test_a_deck_may_open_without_a_cover`, `test_build_tool.py::test_a_deck_without_a_cover_is_built_as_sent`
- [x] 57.2 (H16, M2) `after` 0 means first; `after_the_cover` and its note are deleted. Tests: `test_deck_changes.py::test_an_insert_at_the_start_opens_the_deck`, `test_build_tool.py::test_the_tool_tells_the_agent_one_call_builds_the_whole_deck`
- [x] 57.3 Package checks; `openspec validate --strict`
- Not changed: a cover pattern still serves slide 1 only, and a closing pattern the last slide only (position rules of the kinds themselves)
- [x] 57.4 Live re-evaluation once fred-agents runs this code (not restarted by this change) — done: round 3 (2026-10-18), 37/16/6 +1 NE of 60

## WP58. Layouts and resends (owner decision 2026-10-18: audit fixes, lot 4, design D36)

Owns: `render.py` (`column_split` deleted, `_ZoneMap`, `_place_text`), `plan.py` (`takeaway_aside`, `_slide_fields`), `assign.py` (`_one_point_over_columns` deleted, `_no_place`, `renumber_parts`, `Repeat.unused`/`others` and their computation deleted), `changes.py` (`repinned`), `tools.py` (re-pin on a `slides` resend, part renumbering, variety payload and ask, refused-`changes` text), Help Center fr+en (key-message area), tests, delta specs (also `ppt-builder-intent-fields`), `verification.md`.

- [x] 58.1 (H1) Flat `bullets` do not fit a two-body `two_columns`/`comparison` design; option: give `columns`. Test: `test_assign.py::test_a_flat_list_is_never_split_over_a_two_column_design`
- [x] 58.2 (H2, M4) No `title` in the catalogue of a design that takes `columns` without a title zone; a titled slide is refused with "another kind". Test: `test_assign.py::test_a_title_less_two_panel_design_never_advertises_a_title`
- [x] 58.3 (H3) A takeaway zone beside a body is never a column nor filled from content; alone, it holds the bullets. Test: `test_assign.py::test_a_takeaway_zone_beside_a_body_is_never_a_column`
- [x] 58.4 (H4) A resent slide identical to a delivered one keeps its template slide. Test: `test_deck_changes.py::test_a_whole_deck_resent_keeps_the_design_of_the_slides_it_repeats`
- [x] 58.5 (H5) Split part numbers recounted on delivered slides. Tests: `test_deck_changes.py::test_a_split_list_part_left_alone_drops_its_part_number`, `test_assign.py::test_part_numbers_are_recounted_on_delivered_slides_only`
- [x] 58.6 (H14) Variety asks carry only `suggested` recasts. Tests: `test_build_tool.py::test_the_first_deck_is_asked_to_vary_once_and_a_resend_is_built`, `test_assign.py::test_a_slide_used_three_times_is_reported_without_designs_that_cannot_hold_it`
- [x] 58.7 Package checks; `openspec validate --strict`
- Not changed: splitting itself (needed when a list outgrows the largest slide of its kind); each column quoted at its own room (the tightest body is quoted; no case left after H3); a part title near its room plus ` (k/n)` makes the split fail and the slide is refused as before
- [x] 58.8 Live re-evaluation once fred-agents runs this code (not restarted by this change) — done: round 3 (2026-10-18), 37/16/6 +1 NE of 60

## WP59. Revision fixes, round 3 live evals (owner decision 2026-10-18: universal builder rules only, design D37)

Owns: `charts.py` (`pie_show`), `render.py` (hidden-unit note), `tools.py` (`_redrawn`, `_hoisted`, pie wording), `plan.py` (`takeaway` and `show` descriptions), Help Center fr+en (key messages), tests, delta specs (also `ppt-builder-charts`), `verification.md`.

- [x] 59.1 Pie/doughnut labels default to values when the chart has a `unit`. Test: `test_chart_slides.py::test_a_pie_of_data_with_a_unit_shows_its_values_unless_asked`
- [x] 59.2 Designs line names a chart built as another type. Test: `test_chart_slides.py::test_the_designs_line_says_a_chart_built_as_another_type`
- [x] 59.3 Deck fields inside `changes` hoisted, debris dropped, conflict refused in one line. Test: `test_build_tool.py::test_deck_fields_written_inside_changes_are_taken_to_the_top_level`
- [x] 59.4 ~~An edited takeaway goes on a design of its kind that shows it~~ reverted (owner decision 2026-10-18, D37): a key message is delivered through the slide's content, shown only via `show_takeaways`; the `takeaway` description says so. Test: `test_takeaway.py::test_an_edited_takeaway_never_switches_design_nor_shows`
- [x] 59.5 Package checks; `openspec validate --strict`
- Not changed: mixed units in one series without written units (D37)
- [x] 59.6 Live re-evaluation once fred-agents runs this code (not restarted by this change) — done: round 4 (2026-10-23), 42/11/6/1 NE of 60; pie labels show values, sommaire after the cover

## WP60. Look-alike designs, fallback fix, kinds' use (owner decision 2026-10-18: Paintress deck review, design D38)

Owns: `analysis.py` (`design`, ANALYSIS_VERSION 21), `models.py`, `assign.py` (design keys, `SHAPE_HINTS`, substitution remedy), `render.py` (two notes), `tools.py` (designs line, catalogue, guide), built-in inventory, tests, delta spec, `verification.md`.

- [x] 60.1 Look-alike template slides are one design. Tests: `test_builder_analysis.py::test_look_alike_template_slides_are_one_design`, `test_assign.py::test_look_alike_template_slides_count_as_one_design`, `test_build_tool.py::test_the_designs_line_names_look_alike_template_slides_once`
- [x] 60.2 Fallback notes state the fix without an exit. Test: `test_assign.py::test_a_kind_fallback_note_states_the_fix_without_an_exit`
- [x] 60.3 One "use for" clause per content kind on its catalogue line. Test: `test_build_tool.py::test_schema_and_description_offer_kinds_never_pattern_ids` (updated)
- [x] 60.4 Package checks; `openspec validate --strict`; `make builtin-inventory`
- [x] 60.6 Deck fields lifted out of `slides` entries too (one helper with `changes`); a deck field reaching a slide is never told to go in its text. Tests: `test_build_tool.py::test_a_deck_field_written_inside_a_slide_is_read_as_the_decks` (replays the a611e51e first call, `tests/replays/a611e51e_first_call.json`), `test_assign.py::test_a_field_the_model_invented_is_a_problem_naming_its_text` (extended)
- [x] 60.5 Live re-evaluation once fred-agents runs this code (not restarted; stored inventories re-analyse on the version bump) — done: round 4 (2026-10-23, Thales instance re-analysed on v4), 42/11/6/1 NE of 60

## WP61. Sections, numbering and suggestions (owner decision 2026-10-18: deck review 50bf2432, design D39)

Owns: `assign.py` (`_sections`, `SECTION_RULE`, `Repeat.suggested`, `_suggested`, notes), `tools.py` (proposal notes, catalogue), tests.

- [x] 61.1 Only `section` slides start a section; agenda matching deleted. Tests: `test_assign.py::test_an_agenda_never_splits_the_deck_into_sections`, `test_assign.py::test_three_identical_slides_in_a_row_are_revised_under_the_cap`
- [x] 61.6 Package checks; `openspec validate --strict`
- [x] 61.5 A content kind with one design says `1 look` on its catalogue line. Tests: `test_builder_render.py::test_catalogue_says_a_content_kind_with_one_design_has_one_look`, `test_build_tool.py::test_the_tool_tells_the_agent_one_call_builds_the_whole_deck` (updated)
- [x] 61.2 Every note numbers slides as the outline of its result does (delivery: the file; proposal and revision: the plan), suggestions included. Test: `test_assign.py::test_every_note_numbers_slides_as_its_outline_does`
- [x] 61.3 A suggestion never names a template slide already at its cap. Test: `test_assign.py::test_a_suggestion_never_names_a_template_slide_already_at_its_cap`
- [x] 61.4 Variety notes state their fix without "nothing to do". Test: `test_assign.py::test_every_note_numbers_slides_as_its_outline_does` (asserts the phrase is gone)
- [x] 61.7 Live re-evaluation once fred-agents runs this code (not restarted by this change) — done: round 4 (2026-10-23), 42/11/6/1 NE of 60

## WP62. Pro-session fixes: deck fields and key figures (owner decision 2026-10-18: audit fixes, design D40)

Owns: `tools.py` (`_deck_fields_lifted`, `deck_conflict`), `render.py` (`_figure_scale`), `plan.py` (`quoted_chars`), `assign.py` (`_too_long`), tests, delta spec.

- [x] 62.1 Deck fields lifted by the args schema, before the runtime parses the slides. Tests: `test_build_tool.py::test_a_deck_field_inside_a_parsed_slide_is_never_a_slide_problem` (replays the 0f2506ea first build, `tests/replays/0f2506ea_first_build.json`), `test_build_tool.py::test_a_deck_field_written_inside_a_slide_is_read_as_the_decks` (now through `ainvoke`)
- [x] 62.2 A one-line key figure shrinks to the floor before it is refused; its room is quoted at the floor. Test: `test_builder_render.py::test_a_key_figure_shrinks_to_fit_its_line_down_to_the_floor`
- [x] 62.3 Package checks; `openspec validate --strict`
- [x] 62.4 Live re-evaluation once fred-agents runs this code (not restarted by this change) — done: round 4 (2026-10-23), 42/11/6/1 NE of 60

## WP63. Robustness review fixes (owner decision 2026-10-23, design D41)

Owns: `traversal.py` (`walk_shapes` path steps), `analysis.py` (ANALYSIS_VERSION 22), built-in inventory, tests, delta spec.

- [x] 63.1 Shapes sharing an id get a key each, frozen per slide part. Test: `test_builder_render.py::test_text_boxes_sharing_a_shape_id_each_get_a_zone_and_a_fill` (all items, and two of four with the dropped boxes drawn first)

## WP64. Closing slide: contact vs thanks (owner decision 2026-10-23, design D42)

Owns: `lexicon.py` (`contact_kind`), `analysis.py` (`_contact_roles`, ANALYSIS_VERSION 23), `models.py` (contact roles), `plan.py` (`email`, `phone`), `assign.py` (`_NO_CONTACT`, contact preference), `render.py` (contact lines, `_drop_contact_icons`), `changes.py`, built-in inventory, generated ppt_builder client, tests, delta spec.

- [x] 64.1 Closing lines whose sample reads as an email or phone get `contact_email` / `contact_phone`. Tests: `test_closing_contact.py::test_contact_samples_are_recognised`, `::test_the_contact_lines_of_a_closing_slide_get_contact_roles`
- [x] 64.2 Closing slide `email` / `phone` fields; without them the contact design is never chosen, with them it is preferred. Tests: `test_closing_contact.py::test_a_closing_without_contact_never_takes_the_contact_design`, `::test_a_closing_with_a_contact_takes_the_contact_design`, `::test_with_only_a_contact_design_a_closing_without_contact_uses_another_design`, `::test_reference_template_picks_thanks_or_contact` (Thales v4)
- [x] 64.3 An empty contact line goes with its icon; a closing without contact lines lists the contact. Tests: `test_closing_contact.py::test_the_contact_fills_its_lines_and_an_empty_one_loses_its_icon`, `::test_a_closing_without_a_contact_line_lists_the_contact`
- [x] 64.4 Package checks; `openspec validate --strict`; `make builtin-inventory`; ppt_builder client regenerated
- [x] 64.8 Owner decision B (2026-10-25): the closing is outside the slide count asked, appended at build (`tools._closed`), never in the proposed outline; kept on revisions; opt-out only through `no_closing`, which the user asked for explicitly, stored with the deck (`DeckPlan.no_closing`). Tests: `test_closing_contact.py::test_a_deck_without_a_contact_gets_the_thanks_slide_after_its_slides`, `::test_four_slides_asked_get_the_closing_as_a_fifth`, `::test_the_guidance_puts_the_closing_outside_the_slide_count`, `test_plan_validation.py::test_the_closing_is_added_at_build_never_in_the_outline`, `::test_a_revision_keeps_the_closing_unless_the_user_opts_out`, `test_closing_contact.py::test_an_opt_out_sent_with_changes_drops_the_added_closing`, `::test_an_opt_out_keeps_a_closing_the_model_wrote_or_edited`
- [x] 64.5 Live re-evaluation once fred-agents runs this code — done: chart evals r1-r3 (2026-10-25): contact closing pass in r1-r3 (p11), r3 builds N slides + the thank-you closing (p07-p09 pass); owner browser check of Merci/Contact closings
