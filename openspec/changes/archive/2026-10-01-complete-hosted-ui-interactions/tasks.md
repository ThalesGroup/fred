## 1. Canonical shared APIs

- [x] 1.1 Add optional row callback, keyboard activation and embedded-action isolation; verify canonical table interaction tests.
- [x] 1.2 Add optional drawer close label and neutral-default KPI outcome tone; verify packed declarations and light/dark rendering in the evaluator.

## 2. Packed consumer and verification

- [x] 2.1 Rebuild/validate alpha.3 archive, reinstall it in evaluator without manifest changes and consume all three APIs; verify evaluator interactions, types and build.
- [x] 2.2 Run root quality plus relevant producer/frontend tests, independent review and browser checks; record actual evidence here and include a migration note.
- [x] 2.3 Reconcile and archive this completed SDK change; verify durable spec describes the shipped additive contracts. Publication and evaluator registry close-out remain separate.


## Verification

Developer approved all three SDK extensions in the session before implementation.
`make code-quality` at Fred root passed every module. Canonical DataTable/KpiStatCard tests: 36 passed. Producer `npm test`: 379 passed. `make pack-check-ui`: actual alpha.3 archive validated. `make isolated-consumer`: neutral, React and iframe consumers built/typechecked actual packed archives, including negative row-callback and tone typing. Independent review found no blocking regression. Evaluator consumes the three APIs from the reinstalled tarball: 39 tests passed, TypeScript and production build passed. Publication is not performed; the changed archive requires fresh release evidence.

Browser verification after forced Vite reoptimization: 48 locale/theme/width/route combinations without page overflow or uncaught JS errors; localized close label, clipboard-write feedback, JSON download content and Escape closure verified. Durable requirement synced and strict spec/change validation passed.
