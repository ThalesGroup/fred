Implementation starts only after developer review of this scope and acceptance
criteria. All validation below uses an isolated fresh dataset; migration and the
Monday Swift validation remain separate.

## 1. Establish the target model

- [ ] 1.1 Replace corpus `tag_ids` membership with the mandatory indexed folder reference and same-folder filename constraint; verify fresh schema creation, invalid membership rejection and concurrent name conflicts.
- [ ] 1.2 Remove document FGA relations and consolidate folder authorization in the existing facade, including bounded heterogeneous batches and higher-consistency checks; verify permission mapping, revocation, service identities and FGA failure behavior.
- [ ] 1.3 Update ingestion, overwrite, source synchronization and target-format import/export writers; verify same-folder UID preservation, round-trip grants, attachment isolation and rejection of multi-folder, legacy and reparenting input.

## 2. Converge corpus access paths

- [ ] 2.1 Replace metadata/tag global document enumeration with bounded folder discovery, authorized SQL pages/counts and summary-only folder reads; verify sparse authorization continuation and absence of eager item scans.
- [ ] 2.2 Apply canonical folder gates to content, vector and tabular retrieval and agent filesystem navigation; verify denied/mixed scopes, stale indexes, request limits and no widening or silent incompleteness.
- [ ] 2.3 Regenerate affected OpenAPI clients and update Resources and ReAct/Deep consumers for single membership, pagination and retrieval continuation; verify UI browsing/import and representative scoped/unscoped agent answers.
- [ ] 2.4 Align deletion, cleanup retries and quota accounting with single membership; verify deletion racing ingestion, residual index entries and overwrite size deltas without orphan access.

## 3. Validate and consolidate

- [ ] 3.1 Validate fresh-install scenarios with real OpenFGA and increasing corpora (including 200 teams/2,000 members and sparse grants): record configured limits, checked tuples, transport calls, metadata rows read and latency for fixed requests; demonstrate the design's bounds and run the agreed manual cases plus relevant automated checks.
- [ ] 3.2 Apply the design's documentation dispositions without dropping unresolved RFC decisions; verify links, remove superseded paths, run root quality/migration checks and obtain independent branch review. Record evidence in the PR, then sync/archive the completed specs; do not claim existing-deployment upgrade readiness.
