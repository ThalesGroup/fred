---
name: test-gaps
description: Review missing regression evidence for changed Fred behavior in the requested branch or files. Read-only; do not generate stubs, run tests or infer coverage from symbol-name matches.
---

# Review regression evidence

Read `AGENTS.md` and establish the requested scope, actual base/head and local
changes. Resolve the base from the request or repository metadata, never a fixed
historical branch. Include Rust, Python or TypeScript according to the change.

For domain changes, start with the business invariant and schema/transaction
responsibilities in `fred-reconstruction-method`. Identify changed behavior,
replaced paths and credible regressions. Search existing shared tests and follow
their setup, execution and assertions before recommending another test.

A function-name reference is not proof of coverage; no direct reference is not
proof of a gap. Integration tests and indirect callers may already exercise the
contract. Do not require one test per callable or generate empty test stubs.
Prefer extending existing behavior checks to adding parallel suites. Do not
require tests for reversible presentation or instruction-only edits without a
concrete behavioral risk.

Report actionable gaps with the invariant, failure example, relevant file and
smallest meaningful regression check. Distinguish missing evidence from proven
missing coverage. Do not claim coverage percentages without measurements or
propose a broad campaign. Writing or running tests requires that work to be in
the requested scope; this review alone does not authorize it.
