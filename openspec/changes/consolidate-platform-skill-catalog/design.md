## Context

See proposal.md for motivation and scope. Investigation used branch head `33a727e07a39087696b5afb250321c3c7aee4584`. No active skill change exists; earlier catalog changes are archived. The current spec requires a single-file Mermaid procedure, the separate model-only data guide, dual-route minutes and verification-command examples. The delta explicitly replaces those requirements rather than layering contradictory instructions over them.

The shared catalog already validates `user-invocable` and `disable-model-invocation`; ReAct, Deep/native children, explicit pins and user catalogs consume those controls. `graph` currently supports user and model invocation. Package discovery tests assert nine names and a one-file graph folder; other tests exercise automatic minutes loading. Those expectations must change with the catalog.

## Goals / Non-Goals

Use packaged English procedures and the existing selection/reference seams. Keep the shared runtime, API schemas and provider/tool bindings unchanged. Scope is the packaged catalog; custom-directory homonyms retain their existing behavior. The invocation matrix is authoritative in the delta spec rather than repeated here.

## Decisions

1. **Keep `graph` as the unified identity.** Present it as Visualization/Visualisation and preserve its current invocation routes. This retains `/graph`, history identity and the existing global policy key. A new `visualize` name would add another retirement and policy transition without improving the method. Keeping both current skills would retain the overlap the user asked to remove.

2. **Separate representation choice from Mermaid syntax.** The graph core covers diagram/chart/table selection, verified facts, chart integrity, accessibility, and the output formats actually supported by available tools. Read `graph/references/mermaid.md` when Mermaid is selected; it retains the existing diagram families, syntax baseline and chat-fence contract. HTML/plotting/table paths do not read it. References stay inside the existing snapshot and read-only native mount; no new renderer, router skill or automatic reference injection is needed.

3. **Apply invocation modes through frontmatter.** Comparison and summary set `user-invocable: false`; minutes sets `disable-model-invocation: true`. Their other flag retains its existing default. This changes fresh selection eligibility while preserving existing-context continuity. Update automatic-minutes tests to exercise explicit selection or an appropriate agent-eligible procedure rather than weakening the loader.

4. **Keep comparison and summary short.** Comparison retains meaningful criteria, comparable evidence, unknown values, trade-offs and approved weighting. Summary retains requested scope and fidelity to consequential facts; `summarize-document/references/complex-summaries.md` is read for conflicting/multiple-source synthesis, complex sources or explicitly strict fidelity/traceability. A simple short summary does not require that reference or a narrated verification checklist.

5. **Remove retired resources and active expectations.** Delete the separate data-visualization and verify-answer skill folders. Catalog-driven menus and administration reflect actual discovery. Update FR/EN presentation and active examples; preserve any historical presentation entries actually needed by history consumers. Do not create fallback aliases or rewrite stored invocation/KPI identities.

## Risks / Trade-offs

- Model adherence is probabilistic: package/transport tests prove availability and instruction delivery, not improved answers. Validate representative requests and describe evidence limits without fabricated quality or token savings.
- Reference reads add one conditional tool read when not already in context; the common visualization path carries fewer examples. Preserve normal reference attribution and complete-read guidance instead of adding a second cache or loader.
- Merging scopes changes the meaning of the `graph` opt-out. Its existing policy governs the unified skill; retired data-visualization opt-outs have no implicit effect. Operators must review this before upgrade. Automatic mapping would either unexpectedly disable diagrams or silently reinterpret an old policy.
- Mixed runtime snapshots can advertise different catalogs behind a shared endpoint. Roll out every replica before treating the new menu/policy as uniform; fresh stale selections fail through existing validation.

## Migration Plan

Extend the existing branch migration guide with changed invocation routes, the seven-entry catalog, conditional references, and the broadened graph policy. Update all runtime replicas and the frontend; no database migration or schema regeneration is expected. Old comparison/summary slash selections and removed names require draft correction. Existing conversations may retain earlier instruction text in their checkpoints.

Before rollout, feature managers review retained graph policy and any retired data-visualization override. For rollback, restore the previous runtime/frontend packages on all replicas and review policy again. Preserve retired policy rows and history so rollback requires no data reconstruction. New references are startup resources, with no process-local cross-request state or new pool/query/concurrency costs; no load campaign is needed for this resource-only change.

## Verification Approach

Extend existing runtime catalog/content, eligibility, ReAct and native Deep tests for actual package modes, explicit-only minutes, removed names and reference reads. Adapt assertions that assume one graph file or automatic minutes. Verify native pins/children and current authorization/policy remain intact. Run focused frontend catalog/menu/history/preview tests where the changed presentation reaches them, including rejection of stale selections.

Inspect representative diagram, numerical chart, no-renderer, short-summary, conflicting-document and missing-evidence paths. Scripted models prove transport only. Finish with required root quality checks, appropriate affected-module checks and an independent read-only review of the final change; reconcile and archive this delta after confirmation, implementation and verification.
