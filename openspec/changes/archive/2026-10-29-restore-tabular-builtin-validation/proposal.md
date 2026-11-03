## Why

PRISM-168 reproduces valid `TRIM` and `SUBSTRING` queries being rejected before execution. DuckDB qualifies these built-ins as `main` in its parsed AST, while Fred rejects every qualified function. Agents waste calls recovering from this platform error, independently of model quality.

## What Changes

- Validate analytical functions against their trusted built-in identity, including parser-supplied schema qualification, instead of rejecting every non-empty schema.
- Keep inspection functions, unsafe macros, side effects, external sources and unauthorized datasets rejected.
- Add regressions using the reported expressions and the existing restricted execution boundary.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `tabular-query-safety`: refine pure built-in compatibility. This capability currently lives in the pending `remediate-quality-and-high-security-findings` delta; reuse its name and security requirements. This separate follow-up isolates the reported regression from that change's unrelated scanner and URL work. Do not archive until the shared capability has been reconciled.

## Impact

- Local tracking: [PRISM-168](https://prismaihub.atlassian.net/browse/PRISM-168). No GitHub writes, push or PR, as requested.
- Expected source: `apps/knowledge-flow-backend/knowledge_flow_backend/features/tabular/utils.py`; query validation and restricted-execution tests.
- No API, model catalog, permissions, persistent data, dependency or deployment configuration change.
- The already implemented frontend envelope compatibility restoration is a separate lightweight fix. Model reasoning quality, prompt changes and large-file streaming are outside this SQL correction.
