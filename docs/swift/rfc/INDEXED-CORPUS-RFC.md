# RFC: Indexed Corpus Model and Pull Connector Contract

**Status:** draft — problem and model confirmed by developer in conversation; interfaces not yet confirmed
**Author:** Dimitri Tombroff (design derived collaboratively; not yet built)
**Date:** 2026-09-04
**ID:** CORPUS-01 *(informal mnemonic only — see "Task ID convention" in CLAUDE.md, no registry)*
**Scope:** `libs/fred-sdk` (data model + base connector interface), `apps/knowledge-flow-backend` (first concrete pipeline + proof-of-concept pull corpus)
**Relationship to prior work:** this RFC intentionally does not build on `#2240` ("RFC: Design pluggable ingestion processors and source connectors coordinated by Temporal"). It was written after deliberately restarting from the problem rather than from #2240's processor/connector framing and processor-first sequencing. The developer directed this restart explicitly. The two RFCs will need reconciling (see §8) — that reconciliation is out of scope here.

---

## 1. Problem

FRED can only grow its corpus of usable knowledge today through manual push (upload). Pull — continuously or periodically drawing documents in from external systems (shared folders, GitHub, Jira, Sphere, ...) — exists only as dead or half-built code (see §3).

The naive framing, "let's write connectors," undersells the actual problem. The hard part is not talking to one more external API — it's this:

> FRED needs to build and maintain several **independent derived representations** of knowledge (vector/SQL today, a GraphRAG-style graph and an LLM-generated wiki foreseeably) from a set of **heterogeneous, continuously-changing external sources**, without the synchronization machinery itself becoming an unmanaged distributed system — the "permanent synchronization hell."

That hell decomposes into distinct failure modes, all independently reproducible in FRED's own history (see the Sphere connector post-mortem in §3): cheap change detection (vs. full rescans forever), correct propagation of a change to the right derived representation, safety under concurrent/overlapping sync runs, one clean contract across structurally different sources, and avoiding wasted reprocessing cost (LLM calls, embeddings) when nothing actually changed.

## 2. Decision

Introduce **`Corpus`** as a first-class FRED object: a named, independently-scoped, independently-typed unit of derived knowledge.

```
Corpus = scope × mode × kind [× connector, iff mode == pull]
```

- **scope** — which documents belong to this corpus. Reuses FRED's existing Team/Tag/ReBAC model completely; no new grouping primitive.
- **mode** — `push` or `pull`, **mutually exclusive** on a given corpus. A corpus is never fed by both at once. (Deliberate simplicity choice — see §6.)
- **kind** — the pipeline/representation this corpus materializes: `rag_sql` (today's default), `graphrag`, `llm_wiki`, `sql_live` (pass-through, no materialization at all), extensible to future kinds.
- **connector** — required only when `mode == pull`. A narrow, pipeline-agnostic contract (§5) responsible only for discovering and fetching remote content with a stable identity — never for deciding how a `kind` consumes that content.

Each `kind` owns its own consumption granularity, and the connector contract must never encode it:

| kind | reprocessing grain | who decides *when* |
|---|---|---|
| `rag_sql` | per document | immediate, per detected change |
| `graphrag` | per batch / affected neighborhood | the corpus's own pipeline (threshold, schedule, or on demand — deliberately not specified by this RFC, see §6) |
| `llm_wiki` | per batch (pages can span many source docs) | same as above |
| `sql_live` | none — live query, no materialization | n/a — this kind arguably needs no connector at all |

Corpora with different sources may overlap: the same external source (e.g. one GitHub repo) may legitimately feed two different corpora (e.g. a `rag_sql` corpus and a future `graphrag` corpus), each with its own independent connector instance, own cursor, own state. This is a deliberate trade — redundant sync cost across corpora, in exchange for zero cross-corpus coordination (see §6).

## 3. What already exists (evidence, not a base to build on)

Checked before writing this RFC, per the repo's reuse-audit rule — kept here as evidence for the design, even though this RFC does not extend any of it as-is:

| Component | Location | Status |
|---|---|---|
| `BaseContentLoader` / `PullFileEntry` / `BaseCatalogStore` | `apps/knowledge-flow-backend/knowledge_flow_backend/core/stores/content/`, `core/stores/catalog/base_catalog_store.py` | Implemented for `local_path`/`minio` only. A full `SphereContentLoader` exists but is **never wired** — `ApplicationContext.get_content_loader`/`get_pull_provider` raise `NotImplementedError` for `sphere`, `github`, `gitlab` despite their config models (`SpherePullSource`, `GitPullSource`, `GitlabPullSource`) existing in `common/structures.py`. Dead code. |
| `LibraryOutputProcessor` | `core/processors/output/base_library_output_processor.py` | Already scopes a batch step "once for a library/corpus... aggregate across documents (e.g. build a shared graph)" by `library_tag`. Never formalized as a typed, configured object — exactly the gap `Corpus.kind` fills. |
| `/corpus` virtual filesystem + `corpus_manager` | `features/filesystem/corpus_virtual_filesystem.py`, `features/corpus_manager/` | Read-only view + `/corpus/revectorize`, `/corpus/purge-vectors`, etc. `corpus_manager_service.py` explicitly says in its own code: *"This is MOCKED here; later it maps to Temporal workflow_id, etc."* — scaffolding waiting for a real object. |
| Sphere connector, production reality (`~/Work/fingence`, not this repo) | `contrib/thanos/sphere/sphere_fsspec.py`, `features/external_sources/external_sources_service.py` | Working but instructive as a **negative example**: full remote rescan every cycle (incremental delta API coded but disabled), no stable revision id (diffs by a raw modified-timestamp string), a changed file gets a brand-new `document_uid` with the old one explicitly deleted to fake an update, no leader election across replicas (safe only because `replicaCount: 1`), in-memory-only sync status, heavy Thanos-business-logic coupling inside what should be a generic sync engine. Every one of these is a concrete instance of the failure modes in §1. |

This RFC's connector contract (§5) is written specifically to make the Sphere failure modes structurally impossible, not just "better handled."

## 4. `Corpus` data model (`fred-sdk`)

Proposed location: `libs/fred-sdk/fred_sdk/contracts/corpus.py` (new module — `fred_sdk/contracts/` already exists and already hosts other transport-neutral wire models; no new top-level package needed).

```python
class CorpusMode(str, Enum):
    PUSH = "push"
    PULL = "pull"

class CorpusKind(str, Enum):
    RAG_SQL = "rag_sql"
    GRAPHRAG = "graphrag"
    LLM_WIKI = "llm_wiki"
    SQL_LIVE = "sql_live"

class CorpusScope(BaseModel):
    team_id: str
    tag_ids: list[str] = Field(default_factory=list)

class Corpus(BaseModel):
    corpus_id: str
    name: str
    scope: CorpusScope
    mode: CorpusMode
    kind: CorpusKind
    connector_ref: str | None = None   # required iff mode == PULL; opaque reference, not a class_path
```

`fred-sdk` must not import Knowledge Flow application models, Temporal types, or provider-internal types — same boundary discipline as the rest of `fred_sdk/contracts/`.

## 5. Connector contract (`fred-sdk`)

Proposed location: `libs/fred-sdk/fred_sdk/contracts/connector.py`.

```python
class SourceItem(BaseModel):
    source_item_id: str        # stable, provider-defined identity. Never re-derived from name/path.
    revision: str               # stable revision/etag. Content-addressed when the provider offers it.
    display_path: str
    size_bytes: int | None = None
    modified_at: datetime | None = None

class ChangeKind(str, Enum):
    UPSERT = "upsert"
    DELETE = "delete"

class SourceChange(BaseModel):
    item: SourceItem
    kind: ChangeKind

class SourceConnector(Protocol):
    def discover_changes(self, cursor: str | None) -> tuple[list[SourceChange], str]:
        """Bounded batch of changes since `cursor`; returns the next cursor.
        Must never advance past changes the caller has not durably accepted."""
        ...

    def fetch(self, item: SourceItem, destination_dir: Path) -> Path:
        """Download the artifact identified by `item.source_item_id` (at `item.revision`)."""
        ...
```

Design points this directly encodes, each traceable to a §3 failure mode:

- `source_item_id` and `revision` are **two distinct fields**, both provider-defined and stable — not derived from a display path or a mutable timestamp. This makes a rename representable as "same `source_item_id`, new `display_path`" instead of delete+add, and makes "nothing actually changed" cheaply provable without re-fetching content.
- `discover_changes` is cursor-based, not full-rescan. A connector that cannot offer real deltas may implement this as "cursor = last full scan, always return everything" — but the contract does not privilege that as the default.
- `DELETE` is a first-class `ChangeKind`, not inferred by the caller diffing two listings.
- The connector has **no knowledge of `CorpusKind`, no batching, no scheduling** — it is a pure discover/fetch surface. What a `Corpus` does with a `SourceChange` stream is entirely the pipeline's decision (§2 table).
- **Not addressed here, deliberately**: what runs `discover_changes` on what cadence, and how at-most-one-active-sync-per-corpus is guaranteed. Kept as an explicit invariant (§6), not a mechanism — see below.

## 6. What this RFC deliberately does not decide

Per developer direction, this RFC stays at the model/contract level and leaves execution mechanics to be resolved with FRED's existing Temporal + Kubernetes primitives when the POC is built, not pre-decided in writing:

- Whether a pull corpus's sync is a continuously-running process, a Temporal-scheduled workflow, or an on-demand trigger.
- The exact policy each `CorpusKind` uses to decide when to materialize (immediate per change for `rag_sql`; threshold/schedule/on-demand for `graphrag`/`llm_wiki`).
- Deployment shape of a connector: **in-process library inside `knowledge-flow-backend` is the assumed default for the first proof of concept** (reusing/repairing the existing but dead `BaseContentLoader`-shaped plumbing), not an independently deployed pod. An external pod remains a possible future evolution but is explicitly out of scope for v1 — this is a deliberate simplification, not an oversight, made to avoid the cross-repo/cross-language contract surface #2240 was built around before any concrete need for it exists.
- Cross-corpus deduplication of sources: two corpora pulling the same external source each run their own independent connector instance, own cursor, own cost. Accepted trade for zero cross-corpus coordination (§2).

**One invariant is kept as a hard requirement, not deferred**: a given corpus must never have two overlapping/racing sync executions against its own state. This is the single most concrete lesson from the Sphere post-mortem (§3) — it broke there specifically because nothing enforced it. How it's enforced (Temporal workflow-id semantics, a lease, a lock) is an implementation choice for the POC; that it must hold is not.

## 7. Non-goals for this RFC

- Building an external, independently-deployed connector pod.
- A UI for creating/configuring corpora.
- Implementing `graphrag` or `llm_wiki` kinds — `rag_sql` (the existing pipeline) is the only kind the POC needs to target, since it already exists and lets the corpus/connector model be validated without also inventing a new pipeline.
- Deciding the fate of RFC `#2240` or the dead `sphere`/`github`/`gitlab` code in the current codebase (see §3) — a separate, explicit decision the developer should make once this model is validated.
- Multi-tenant/multi-Sphere-account credential design — inherit whatever FRED's current secret-reference conventions are when the POC needs real credentials.

## 8. Relationship to `#2240`

Left as an open question for the developer, not resolved here: `#2240`'s connector contract (discover/fetch split, stable provenance, durable cursor) converges strongly with §5 above — independently re-derived, not copied. What `#2240` has that this RFC does not is the external-pod execution envelope and processor/connector shared-envelope fields; what this RFC has that `#2240` does not is the `Corpus` object itself (§2) and the explicit decision to defer the pod question (§6). Reconciling — supersede, merge, or keep as two RFCs at different layers — is a decision for the developer once the POC in §9 has produced real evidence, not before.

## 9. Plan

1. Land `Corpus` and `SourceConnector` (§4, §5) in `fred-sdk`, with contract fixtures/tests, no behavior yet.
2. Implement exactly one proof-of-concept pull corpus in `knowledge-flow-backend`, `kind=rag_sql`, against the simplest possible real connector (candidate: local filesystem or Minio/S3, since both already have working loaders to model the new contract against — Sphere/GitHub are harder cases, better attempted once the model is proven).
3. Validate the §6 invariant (no overlapping sync) end-to-end before calling the POC done.
4. Only after the POC works: revisit `#2240` (§8), and consider a second corpus `kind` or a second connector (Sphere, GitHub) as the next increment.

## 10. Open questions

- Final name for `Corpus` vs. alternatives (kept simple deliberately; flag if it collides with product-facing terminology already in use elsewhere).
- Exact shape of `connector_ref` (opaque string id vs. a richer registration object) — deferred until the POC needs to actually resolve one.
- Where does per-`CorpusKind` consumption policy configuration live — on the `Corpus` object itself, or entirely inside each pipeline's own code? Leaning toward the latter (keeps `Corpus` minimal) but not decided.
