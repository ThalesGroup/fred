## Why

Fred-manager needs a recoverable space-deletion lifecycle before document and conversation cleanup is added. An authenticated API must retire a space immediately, while a separate Rust Temporal worker removes its existing SQL/OpenFGA state after a governed delay, without losing the information needed after partial failure.

## What Changes

- Add asynchronous deletion and deletion-status APIs for organizations, ordinary teams and projects, including their descendants and, for organizations, personal spaces.
- Restrict requests to platform owners through an explicit OpenFGA capability. This preserves Python's technical team-deletion authority; extending it to projects and organizations is a proposed contract, not an existing Python behavior.
- Persist the request and retire its complete scope atomically; enforce retirement on every manager consumer and mutation, including provisioning and permission probes.
- Add validated Rust policy types using the existing `default/rules/match/action`, ISO-8601 retention and scheduler conventions. Do not accept settings for unimplemented conversation behavior.
- Add a separately runnable Rust Temporal lifecycle worker, an idempotent periodic sweep, bounded cleanup activities, observable partial failures and durable completion receipts.
- Remove only manager-owned empty folders, spaces and their OpenFGA relations. Refuse scopes containing document rows; preserve accounts, consent, platform roles and unrelated organizations.
- Keep the UI and role-revocation semantics unchanged. The developer explicitly selected space deletion only; full member removal and conversation cleanup are separate work.

## Capabilities

### New Capabilities

None. Extend the existing manager capability rather than introduce a parallel ownership specification.

### Modified Capabilities

- `fred-manager-provisioning`: add the space-deletion lifecycle and permit immutable hierarchy links to be removed only by its authorized cleanup.

## Impact

- `apps/fred-manager`: lifecycle module, API, configuration, CLI/worker entry point, new SQL migration, OpenFGA capability and bounded tuple cleanup, existing space/provisioning consumers, tests and deployment overlay.
- `apps/frontend`: regenerate the manager client; no page, control or interaction changes.
- `docs/architecture`: journeys, action/role matrix, ownership, operations, runtime/configuration references and measured request budgets in the implementation commit.
- Temporal Rust worker crates aligned with the existing pinned 1.0.0 client/common family; no Python service replacement or data migration in this lot.
- Follow-on to Rust reconstruction issue #3092. OpenFGA cleanup pitfalls in #2664 inform the design. Establish a dedicated implementation issue when this scope is approved; do not repurpose the separate Python migration work in #2921.
