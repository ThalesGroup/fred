## 1. Configuration and eligibility

- [x] 1.1 Implement default packaged configuration and explicit null/custom behavior; verify loader and Helm round-trip tests (#3299).
- [x] 1.2 Parse invocation metadata and enforce per-request catalog/read eligibility; verify default, agent-only, explicit-only and invalid metadata through public loaders/execution (#3300).
- [x] 1.3 Negotiate additive catalog fields and preserve packaged provenance; verify old and new response consumers.

## 2. Native Deep selection

- [x] 2.1 Pass native pinned_skills and observe actual loads with trusted events/KPIs; verify compiled streaming/invoke and resume tests (#3302).
- [x] 2.2 Verify children, native file searches, failed/unknown loads and existing workspace/readonly behavior.

## 3. Integration

- [x] 3.1 Regenerate schemas/contracts, update migration guidance, run root quality/offline checks and independent review; reconcile and archive.

Evidence: configuration loader 23 tests and Helm 19 tests passed. Runtime policy,
compiled ReAct/Deep and native filesystem regression suites pass 88 tests,
including failed inference escaping, resumed disabled loads and reusable binding.
Versioned metadata/direct-policy helper passes 15 tests, delegated admission and
foreground routing pass 78 tests; SDK offline suite passes 653 tests (3 skipped).
No new DeepAgents dependency was needed: installed/locked 0.7.30 provides native
pinned_skills. Both public API clients were regenerated.

Final verification: runtime complete offline suite passes 2293 tests (23
integration tests deselected); later resume-eligibility/concurrent-pin and
actual-target user-control corrections pass 113 affected tests. SDK full suite
passes 653 tests (3 skipped). Migration-note validation passes against branch
base d76d96ba0f6642871b2191cedb1ecb32df0b0d2a.

Independent author review: standards/performance and spec reviewers inspected
that base through 42fad4ab8 plus the complete working tree, then corrective
deltas through 17741c118 and subsequent runtime changes. Coverage included
configuration/deployment, SDK/runtime callers, native children/checkpoints,
policy storage/auth/relay, frontend interaction/provenance and packaging/docs.
Standards axis: four findings resolved - retained-pin escaping after model
failure, reusable runtime source narrowing, actual-target user invocation
bypass and active-switch focus. Its corrective review reports no remaining
actionable finding in scope.

Spec axis: seven findings resolved - cross-message command copy, active-switch
focus, CLI prose, selected-read origin, same-exchange reference eligibility,
the stale middleware prohibition and the ambiguous snapshot-filtering
requirement. Full modified blocks preserve existing scenario names at sync.

Performance review found bounded pooled async
I/O and existing KPI routing, without a production-load or PostgreSQL claim.
Unrelated models_catalog.local.yaml was excluded. All work remains local.

Root make code-quality passes across every configured module, including full
frontend TypeScript/Prettier/ESLint, Python lint/import/format/security/baseline
typing, and migration-tool tests. Installed editable Python environments were
used with dependency-bootstrap sync skipped to avoid network rebuilds; all
quality targets executed. Node tools were restored from the lockfile offline
after sandbox subprocess restrictions. No dependency or lockfile changed.
Strict validation passes for all four deltas and their merged main spec.
All 158 original scenario names remain, with 11 additions. Final source review
covered cbbbd1fe0 plus the documented corrective working tree.
