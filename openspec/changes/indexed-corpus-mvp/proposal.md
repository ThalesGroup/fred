## Why

FRED can only grow its knowledge today through manual push (upload); pull — continuously or periodically drawing documents in from external systems (shared folders, GitHub, Jira, Sphere, ...) — exists only as dead or half-built code. Every prior attempt at this in FRED's own history (see design.md's Sphere connector post-mortem) failed the same way: full remote rescans forever, no stable change identity, and no protection against overlapping sync runs. This change replaces `docs/swift/rfc/INDEXED-CORPUS-RFC.md` as the durable record for that work going forward, and continues an MVP already partly built and merged on `feat/pull-corpus` — many more increments are expected after this one.

## What Changes

- Introduces **`CorpusType`**: a platform-wide, registered kind of corpus (`kind` × `mode` × `connector_kind`) — what a developer contributes and a platform admin enables per team, mirroring FRED's existing agent-template/agent-instance split.
- Introduces **`Corpus`**: a team-scoped instance of an enabled `CorpusType` (`scope` = team + tags, `connector_ref` = instance config) — what a team creates once its type is enabled.
- Introduces **`SourceConnector`**: a narrow, pipeline-agnostic discover/fetch contract with stable `source_item_id`/`revision` identity, kept deliberately too fine-grained to be the developer-facing unit on its own — internal plumbing a `CorpusType` uses, never itself registered or gated.
- Introduces a dedicated OpenFGA object type `corpus_type` for team usage-enablement — not a namespaced `capability` id, since `capability` is reserved for "something an agent uses." Mirrors a parallel, in-progress move a teammate (Adrian) is making for `app`; this change's schema addition is provisional and must not diverge from whatever shape his lands with.
- **Already built and merged** (this change's `tasks.md` records these as done, not proposed): the `fred-sdk` contracts, a first `SourceConnector` implementation (local filesystem), the sync path wiring a connector into the existing push ingestion pipeline, the `corpus_type` ReBAC relations, `CorpusType` as deployment configuration, the `corpus` instance table, and the fail-closed `create_corpus` creation gate.
- **Not yet built**: the M2M read path so `knowledge-flow-backend` can fetch a `Corpus`/`CorpusType` from `control-plane-backend` once per sync cycle, and `knowledge-flow-backend`'s own small durable sync-state table.
- **Explicitly out of scope for this change**: admin Features-tab UI, team Resources-tab UI, any scheduler/trigger for the sync function, a second `CorpusType` (Sphere, GitHub, Minio), `graphrag`/`llm_wiki` kinds, reconciling with the older, unrelated RFC `#2240` (external-pod processor/connector design), deleting/retiring a `Corpus` instance (only `create_corpus` exists — see design.md D18), and any wiring from a corpus type/instance to an agent capability or MCP server (RAG/SQL exposure stays entirely the existing, separate agent-instance capability configuration, keyed only on the tag a corpus stamps its documents with — see design.md D11).

## Capabilities

### New Capabilities

- `indexed-corpus`: the `CorpusType`/`Corpus` model, the `SourceConnector` contract, and the corpus-type usage-enablement gate — the first capability defined in this repository's `openspec/specs/` (currently empty).

### Modified Capabilities

_None._ No `openspec/specs/` capability exists yet in this repository.

## Impact

- **Code, already merged (`feat/pull-corpus`):** `libs/fred-sdk/fred_sdk/contracts/{corpus,connector}.py`; `libs/fred-core/fred_core/security/{models.py,rebac/{schema.fga,rebac_engine.py,corpus_type_authz.py}}`; `apps/control-plane-backend/control_plane_backend/{corpus_types/,corpus/,models/corpus_models.py}` plus one Alembic migration; `apps/knowledge-flow-backend/knowledge_flow_backend/{core/connectors/local_filesystem_connector.py,features/scheduler/pull_corpus_sync.py}`; a prior cleanup removing dead pull-mode scaffolding that predated this design.
- **Code, not yet built:** a new `DocumentIngestionPort` in `fred-sdk` and its local adapter in `knowledge-flow-backend` (design.md D8-D9), with the *existing* manual-upload path (`ingestion_controller.py`) retrofitted to call it alongside `pull_corpus_sync.py` — proving push and pull share one ingestion hand-off, not two; a documented (not implemented) wire contract for a future remote adapter (D10); a control-plane-backend M2M read endpoint for `Corpus`/`CorpusType`; a knowledge-flow-backend `corpus_sync_state` table; `pull_corpus_sync.py` updated to read config via that endpoint instead of receiving it as a plain argument.
- **Docs:** `docs/swift/rfc/INDEXED-CORPUS-RFC.md` is superseded by this change once archived; it is not deleted immediately (see design.md).
- **Coordination dependency:** the `corpus_type` ReBAC schema addition tracks Adrian's separate, in-progress `app`-kind ReBAC convention — do not implement independently past what is already merged.
