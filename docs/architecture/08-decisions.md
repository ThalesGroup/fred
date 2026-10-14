# 8. Decisions

One entry per decision: what was chosen, and what it costs. Superseded entries stay,
marked so.

| Id | Decision | Because | Consequence |
| --- | --- | --- | --- |
| D1 | Rebuild beside the Python backends, in Rust, one topic at a time; migration out of scope. | Incremental repair of the old design kept stalling. | Two systems coexist until the UI moves (chapter 10). |
| D2 | The space tree lives in SQL; OpenFGA holds direct roles only, no parent relation. | Recursive tuple traversal (the old `tag.parent`) made every check deep and every move a tuple rewrite. | One check per access; the parent invariant is enforced by fred-manager (I4). |
| D3 | Organization > team > project; a personal space is a one-member team. | One model for every container, no special personal type. | Personal spaces need their own management rule (I6). |
| D4 | Folders carry no rights. | Rights per folder bring back traversal and lists. | Access granularity is the space. |
| D5 | No moves: placement is immutable, a move is a re-import. | Chunks and storage keys copy placement. | Renames are free; moves cost a re-ingestion. |
| D6 | Search scope = ancestors and self. | A team conversation must not see its projects' content. | A project sees its team's and organization's content. |
| D7 | Admin roles grant no content access. | Least privilege: governing is not reading. | An admin who must read holds a content role too; self-grant is open (chapter 10). |
| D8 | Serialize every role or space mutation of an organization under a Postgres advisory lock, caller check included. | Check-then-write across two systems races. | Mutations of one organization are sequential. |
| D9 | Root bootstrap as the control-plane, but reservation committed before the grant, completion recorded under the lock. | No double promotion, no reopening. | A failed grant can only be finished by its claimant. |
| D10 | Configuration and logging follow the Python backends exactly. | One operating model for every Fred service. | Rust-specific gaps are listed (chapter 6). |
| D11 | Share the `fred` database and the Postgres, OpenFGA, Temporal and Keycloak of the existing stack. | No new infrastructure. | Table names must not collide; fred-manager has its own OpenFGA store. |
| D12 | Deploy with fred's chart as a separate release. | No second chart to maintain. | Temporary schema workaround (chapter 7). |
| D13 | Document in this dossier; generate what code can produce, prove invariants by tests. | Docs drift; fred-website lags. | `make check` gates the dossier. |
