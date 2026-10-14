# 8. Decisions

One entry per decision: what is chosen, why, and what it costs. A superseded entry
stays, marked so.

| Id | Decision | Because | Consequence |
| --- | --- | --- | --- |
| D1 | The space tree lives in SQL; OpenFGA holds direct roles only, no parent relation. | A parent relation in OpenFGA makes each check traverse the tree and each move rewrite tuples. | One check per access; fred-manager enforces the parent rule (I4). |
| D2 | Organization > team > project; a personal space is a one-member team. | One model for every container. | Personal spaces have their own management rule (I6). |
| D3 | Folders carry no rights. | Rights per folder bring back traversal and per-item lists. | Access granularity is the space. |
| D4 | Placement is immutable; a move is a re-import. | Storage keys and indexed content carry placement. | Renames are free; a move costs a re-ingestion. |
| D5 | A space's search scope is its ancestors and itself. | Content of a project stays out of its team's scope. | A project reads its team's and organization's content. |
| D6 | Admin roles grant no content access. | Governing is not reading. | An admin who reads also holds a content role. |
| D7 | Every role or space mutation of an organization runs under one Postgres advisory lock, caller check included. | A check in OpenFGA then a write races without it. | Mutations within one organization are sequential. |
| D8 | Root bootstrap in two steps under one lock: reservation committed, then grant and completion. | No double promotion, no reopening. | A failed grant can only be finished by its claimant. |
| D9 | Configuration, secrets and log output follow Fred's service conventions. | One way to operate every Fred service. | `sourceLocation.function` holds the module path. |
| D10 | Shared infrastructure, own OpenFGA store. | No dedicated infrastructure to run. | Table names are unique in `fred`; the store is `fred-manager`. |
| D11 | Deployed with fred's chart as a separate release. | One chart for every Fred service. | The release references the chart without its `values.schema.json` (chapter 7). |
| D12 | All assignable Fred roles have explicit typed equivalents; space admin and content roles remain orthogonal. | Silent role loss and implicit content grants change authorization meaning. | Analyst is a content role; revocation never adds a fallback role. |
| D13 | Platform mutations and delegated team creation share the bootstrap lock, acquired before the organization lock. | Platform revocation must serialize with dependent writes. | A revoked administrator cannot finish a waiting mutation; the root grant is protected. |
| D14 | Directory operations use a dedicated service client and raw Keycloak subjects in the same realm as callers. | Caller tokens do not carry directory administration privileges. | Grants validate identity existence; revocation tolerates deleted identities. |
| D15 | Import uses authenticated, read-only initialization and a distinct Keycloak service identity. | Service-client credentials must not substitute for Fred operator authority. | Bootstrap and compatible schema/model initialization precede import; Temporal is not involved. |
| D16 | Provisioning is additive and replayable, with identity phases separate from the space transaction. | Keycloak, SQL and OpenFGA do not share a transaction. | Partial effects remain; replay preserves committed IDs and repairs grants. Rolled-back space IDs are not reused. |
