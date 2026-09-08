# RFC: Knowledge Base Model and Pull Connector Contract

**Status:** draft — POC (§10 steps 1-3) built and tested; §10 step 4 (usage enablement + admin/team UI) in progress
**Author:** Dimitri Tombroff (design derived collaboratively)
**Date:** 2026-09-04, revised 2026-09-06 (KnowledgeBaseType/KnowledgeBase split, §2/§4/§6)
**ID:** KNOWLEDGE-BASE-01 *(informal mnemonic only — see "Task ID convention" in CLAUDE.md, no registry)*
**Scope:** `libs/fred-sdk` (data model + base connector interface), `apps/knowledge-flow-backend` (first concrete pipeline + proof-of-concept pull knowledge base)
**Relationship to prior work:** this RFC intentionally does not build on `#2240` ("RFC: Design pluggable ingestion processors and source connectors coordinated by Temporal"). It was written after deliberately restarting from the problem rather than from #2240's processor/connector framing and processor-first sequencing. The developer directed this restart explicitly. The two RFCs will need reconciling (see §9) — that reconciliation is out of scope here.

---

## 1. Problem

FRED can only grow its knowledge today through manual push (upload). Pull — continuously or periodically drawing documents in from external systems (shared folders, GitHub, Jira, Sphere, ...) — exists only as dead or half-built code (see §3).

The naive framing, "let's write connectors," undersells the actual problem. The hard part is not talking to one more external API — it's this:

> FRED needs to build and maintain several **independent derived representations** of knowledge (vector/SQL today, a GraphRAG-style graph and an LLM-generated wiki foreseeably) from a set of **heterogeneous, continuously-changing external sources**, without the synchronization machinery itself becoming an unmanaged distributed system — the "permanent synchronization hell."

That hell decomposes into distinct failure modes, all independently reproducible in FRED's own history (see the Sphere connector post-mortem in §3): cheap change detection (vs. full rescans forever), correct propagation of a change to the right derived representation, safety under concurrent/overlapping sync runs, one clean contract across structurally different sources, and avoiding wasted reprocessing cost (LLM calls, embeddings) when nothing actually changed.

## 2. Decision

Introduce **two** first-class FRED objects, not one (2026-09-06 revision — see §6 for why a bare connector was rejected as the unit):

```
KnowledgeBaseType = kind × mode [× connector_kind, iff mode == pull]     — platform-wide, registered once
KnowledgeBase     = knowledge_base_type_id × scope [× connector_ref]     — team-scoped instance of an enabled KnowledgeBaseType
```

This mirrors FRED's existing agent-template/agent-instance split, for the same reason: "what can exist on the platform" and "what a given team actually has" are different lifecycles, owned by different actors (developer/platform admin vs. team).

**`KnowledgeBaseType`** — what a developer brings to FRED and a platform admin enables per team (§6):

- **kind** — the pipeline/representation a knowledge base of this type materializes: `rag_sql` (today's default), `graphrag`, `llm_wiki`, `sql_live` (pass-through, no materialization at all), extensible to future kinds.
- **mode** — `push` or `pull`, **mutually exclusive** on a given type. A type is never fed both ways. (Deliberate simplicity choice — see §7.)
- **connector_kind** — required only when `mode == pull`: which connector implementation the type uses internally (`local_fs`, later `minio`/`github`/`sphere`). This is also the id the usage-enablement gate keys on (§6) — *whether a team may use this type at all*.

**`KnowledgeBase`** — a team-scoped instance a team creates once its `KnowledgeBaseType` is enabled:

- **scope** — which documents belong to this instance. Reuses FRED's existing Team/Tag/ReBAC model completely; no new grouping primitive.
- **connector_ref** — the instance's own connector configuration (credentials, root path — opaque, resolved by whatever code knows how to build a `SourceConnector` for `knowledge_base_type_id`). Whether one is required depends on the referenced `KnowledgeBaseType.mode`; that cross-check is a service-layer concern, not encoded in either pure data model (§4).

The connector itself (§5) stays a narrow, pipeline-agnostic contract responsible only for discovering and fetching remote content with a stable identity — never for deciding how a `kind` consumes that content, and never itself the thing registered or enabled. Each `kind` owns its own consumption granularity, and the connector contract must never encode it:

| kind | reprocessing grain | who decides *when* |
|---|---|---|
| `rag_sql` | per document | immediate, per detected change |
| `graphrag` | per batch / affected neighborhood | the knowledge base's own pipeline (threshold, schedule, or on demand — deliberately not specified by this RFC, see §7) |
| `llm_wiki` | per batch (pages can span many source docs) | same as above |
| `sql_live` | none — live query, no materialization | n/a — this kind arguably needs no connector at all |

Knowledge base instances with different sources may overlap: the same external source (e.g. one GitHub repo) may legitimately feed two different knowledge base instances (e.g. one of a `rag_sql` type and one of a future `graphrag` type), each with its own independent connector instance, own cursor, own state. This is a deliberate trade — redundant sync cost across knowledge bases, in exchange for zero cross-knowledge-base coordination (see §7).

## 3. What already exists (evidence, not a base to build on)

Checked before writing this RFC, per the repo's reuse-audit rule — kept here as evidence for the design, even though this RFC does not extend any of it as-is:

| Component | Location | Status |
|---|---|---|
| `BaseContentLoader` / `PullFileEntry` / `BaseCatalogStore` | `apps/knowledge-flow-backend/knowledge_flow_backend/core/stores/content/`, `core/stores/catalog/base_catalog_store.py` | Implemented for `local_path`/`minio` only. A full `SphereContentLoader` exists but is **never wired** — `ApplicationContext.get_content_loader`/`get_pull_provider` raise `NotImplementedError` for `sphere`, `github`, `gitlab` despite their config models (`SpherePullSource`, `GitPullSource`, `GitlabPullSource`) existing in `common/structures.py`. Dead code. |
| `LibraryOutputProcessor` | `core/processors/output/base_library_output_processor.py` | Already scopes a batch step "once for a library/knowledge base... aggregate across documents (e.g. build a shared graph)" by `library_tag`. Never formalized as a typed, configured object — exactly the gap `KnowledgeBaseType.kind` fills. |
| `/corpus` virtual filesystem + `corpus_manager` | `features/filesystem/corpus_virtual_filesystem.py`, `features/corpus_manager/` | Read-only view + `/corpus/revectorize`, `/corpus/purge-vectors`, etc. `corpus_manager_service.py` explicitly says in its own code: *"This is MOCKED here; later it maps to Temporal workflow_id, etc."* — scaffolding waiting for a real object. **Note (2026-09-07 vocabulary convergence):** this is a separate, pre-existing, already-shipped FRED surface, out of scope for this RFC's `KnowledgeBaseType`/`KnowledgeBase` vocabulary. The module and route names above are cited as-is because that is what the code is actually called today — a factual citation, not a naming recommendation for this RFC's own objects. |
| Sphere connector, production reality (`~/Work/fingence`, not this repo) | `contrib/thanos/sphere/sphere_fsspec.py`, `features/external_sources/external_sources_service.py` | Working but instructive as a **negative example**: full remote rescan every cycle (incremental delta API coded but disabled), no stable revision id (diffs by a raw modified-timestamp string), a changed file gets a brand-new `document_uid` with the old one explicitly deleted to fake an update, no leader election across replicas (safe only because `replicaCount: 1`), in-memory-only sync status, heavy Thanos-business-logic coupling inside what should be a generic sync engine. Every one of these is a concrete instance of the failure modes in §1. |

This RFC's connector contract (§5) is written specifically to make the Sphere failure modes structurally impossible, not just "better handled."

## 4. `KnowledgeBaseType` / `KnowledgeBase` data model (`fred-sdk`)

Location: `libs/fred-sdk/fred_sdk/contracts/knowledge_base.py` (`fred_sdk/contracts/` already hosts other transport-neutral wire models; no new top-level package needed).

```python
class KnowledgeBaseMode(str, Enum):
    PUSH = "push"
    PULL = "pull"

class KnowledgeBaseKind(str, Enum):
    RAG_SQL = "rag_sql"
    GRAPHRAG = "graphrag"
    LLM_WIKI = "llm_wiki"
    SQL_LIVE = "sql_live"

class KnowledgeBaseType(BaseModel):
    knowledge_base_type_id: str  # e.g. "local_fs_rag" — the §6 enablement key
    name: str
    kind: KnowledgeBaseKind
    mode: KnowledgeBaseMode
    connector_kind: str | None = None  # required iff mode == PULL; e.g. "local_fs"

class KnowledgeBaseScope(BaseModel):
    team_id: str
    tag_ids: list[str] = Field(default_factory=list)

class KnowledgeBase(BaseModel):
    knowledge_base_id: str
    name: str
    knowledge_base_type_id: str    # which KnowledgeBaseType this instantiates
    scope: KnowledgeBaseScope
    connector_ref: str | None = None   # instance-specific connector config, opaque; not a class_path
```

Two design points:

- `KnowledgeBaseType.connector_kind` and `KnowledgeBase.connector_ref` answer two different questions and live on two different objects, not one field on one object: `connector_kind` is *which connector implementation* — the thing §6's usage-enablement check is keyed on, small and enumerable (`local_fs`, later `minio`/`github`/`sphere`) — while `connector_ref` is *which configured instance* of that kind (credentials, root path), opaque to everything except the code that resolves it. Collapsing them would force parsing `connector_ref` just to answer an authorization question, and would put instance-specific config on the platform-wide, not-team-scoped object.
- `KnowledgeBase` does **not** re-validate against its `KnowledgeBaseType` (e.g. "does this instance have a `connector_ref` because its type is pull-mode?"). A pure data model can't look up an external registry; that check belongs to whatever service creates a `KnowledgeBase` instance, not to either pydantic model.

`fred-sdk` must not import Knowledge Flow application models, Temporal types, or provider-internal types — same boundary discipline as the rest of `fred_sdk/contracts/`.

## 5. Connector contract (`fred-sdk`)

Location: `libs/fred-sdk/fred_sdk/contracts/connector.py`.

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
- The connector has **no knowledge of `KnowledgeBaseKind`, no batching, no scheduling** — it is a pure discover/fetch surface. What a `KnowledgeBase` does with a `SourceChange` stream is entirely the pipeline's decision (§2 table).
- **Not addressed here, deliberately**: what runs `discover_changes` on what cadence, and how at-most-one-active-sync-per-knowledge-base is guaranteed. Kept as an explicit invariant (§7), not a mechanism — see below.

## 6. Usage enablement — which teams may use a `KnowledgeBaseType` (2026-09-05, revised 2026-09-06)

Corrected in conversation after a team decision the same week, not yet written down anywhere else: **`capability` is reserved for "something an agent uses."** A knowledge base type's creation/operation permission is not that — no more than an application is — so it does not belong on `type capability`, namespaced or otherwise.

**Why the gate is on `KnowledgeBaseType`, not on a raw connector kind.** A bare connector (discover/fetch only) says nothing about what an agent gets — it is not the thing worth registering, enabling, or showing an admin. What a developer contributes and a platform admin enables is a whole `KnowledgeBaseType` (§2/§4): "team A may use the Local Filesystem knowledge base," not "team A may use the `local_fs` connector." The connector stays internal plumbing a `KnowledgeBaseType` happens to use (`KnowledgeBaseType.connector_kind`), reused across types if useful — it is never itself registered or gated.

**What is being gated, precisely.** Not a specific `KnowledgeBase` instance, and not cross-team sharing of one instance's content — a knowledge base instance's content stays exactly as scoped by `KnowledgeBaseScope.team_id` (§4) regardless of this gate. The question is coarser and purely operational: *may team A create/operate an instance of `KnowledgeBaseType` T at all* — e.g. "team A may use an fs knowledge base." This gate answers nothing about who can read a given instance's documents.

**Proposed shape (provisional — see coordination note below).** A new OpenFGA object type, `type knowledge_base_type`, copying the exact relation shape already proven by `type capability` (`fred_core/security/rebac/schema.fga`): `organization` anchor, `default_on` (all teams), `enabled`/`disabled` (per-team override, tri-state), `can_manage` (`platform_admin`-only), `can_use` (computed). One object per **registered `KnowledgeBaseType`**, keyed by `knowledge_base_type_id`, not per `KnowledgeBase` instance: `knowledge_base_type:local_fs_rag`, later e.g. `knowledge_base_type:minio_rag`, `knowledge_base_type:sphere_rag`.

**Where the check happens.** At `KnowledgeBase` instance creation — a team without `can_use` on `knowledge_base_type:<knowledge_base_type_id>` cannot create an instance of that type. As a stated requirement, not yet implemented: revoking a team's access should suspend that team's already-running instances of that type, mirroring the existing agent-capability pattern (`reconcile_instance_suspension`, `control_plane_backend/capabilities/enablement.py`) — losing access must not merely block new creation while an already-running sync keeps going. Left unimplemented in this RFC's POC scope (§8).

**Coordination note.** Adrian is actively implementing the equivalent move for applications — off the shared `capability` type (`capability:app__<id>`, `fred_core/security/rebac/capability_authz.py`) and onto their own proper ReBAC type, for the same reason stated above. `knowledge_base_type` should mirror whatever shape that work lands with — same relations, same one-type-per-concept pattern — rather than being designed independently; the developer confirmed we follow his pattern once it exists, not build a parallel one. **`libs/fred-core/fred_core/security/rebac/schema.fga` is deliberately left untouched by this RFC and its POC** until then, both to avoid guessing at a shape that's about to be decided elsewhere and to avoid two people editing the same shared schema file concurrently.

## 7. What this RFC deliberately does not decide

Per developer direction, this RFC stays at the model/contract level and leaves execution mechanics to be resolved with FRED's existing Temporal + Kubernetes primitives when the POC is built, not pre-decided in writing:

- Whether a pull knowledge base's sync is a continuously-running process, a Temporal-scheduled workflow, or an on-demand trigger.
- The exact policy each `KnowledgeBaseKind` uses to decide when to materialize (immediate per change for `rag_sql`; threshold/schedule/on-demand for `graphrag`/`llm_wiki`).
- Deployment shape of a connector: **in-process library inside `knowledge-flow-backend` is the assumed default for the first proof of concept** (reusing/repairing the existing but dead `BaseContentLoader`-shaped plumbing), not an independently deployed pod. An external pod remains a possible future evolution but is explicitly out of scope for v1 — this is a deliberate simplification, not an oversight, made to avoid the cross-repo/cross-language contract surface #2240 was built around before any concrete need for it exists.
- Cross-knowledge-base deduplication of sources: two knowledge bases pulling the same external source each run their own independent connector instance, own cursor, own cost. Accepted trade for zero cross-knowledge-base coordination (§2).

**One invariant is kept as a hard requirement, not deferred**: a given knowledge base must never have two overlapping/racing sync executions against its own state. This is the single most concrete lesson from the Sphere post-mortem (§3) — it broke there specifically because nothing enforced it. How it's enforced (Temporal workflow-id semantics, a lease, a lock) is an implementation choice for the POC; that it must hold is not.

## 8. Non-goals for this RFC

- Building an external, independently-deployed connector pod.
- A UI for creating/configuring knowledge bases — true of the POC completed so far (§10 steps 1-3); the admin Features-tab and team Resources-tab surfaces are the explicit next phase (§10 step 4), not covered by this RFC's model/contract sections.
- Implementing `graphrag` or `llm_wiki` kinds — `rag_sql` (the existing pipeline) is the only kind the POC needs to target, since it already exists and lets the knowledge-base/connector model be validated without also inventing a new pipeline.
- Deciding the fate of RFC `#2240` or the dead `sphere`/`github`/`gitlab` code in the current codebase (see §3) — a separate, explicit decision the developer should make once this model is validated.
- Multi-tenant/multi-Sphere-account credential design — inherit whatever FRED's current secret-reference conventions are when the POC needs real credentials.
- Implementing or enforcing the `knowledge_base_type` ReBAC type (§6) — the `KnowledgeBaseType`/`KnowledgeBase` split exists now so the model doesn't need a breaking change later, but the POC creates/runs its knowledge base instance without any usage-enablement check. Wiring that check follows Adrian's app-kind convention once it lands (§6), not decided independently here.

## 9. Relationship to `#2240`

Left as an open question for the developer, not resolved here: `#2240`'s connector contract (discover/fetch split, stable provenance, durable cursor) converges strongly with §5 above — independently re-derived, not copied. What `#2240` has that this RFC does not is the external-pod execution envelope and processor/connector shared-envelope fields; what this RFC has that `#2240` does not is the `KnowledgeBase` object itself (§2) and the explicit decision to defer the pod question (§7). Reconciling — supersede, merge, or keep as two RFCs at different layers — is a decision for the developer once the POC in §10 has produced real evidence, not before.

## 10. Plan

1. Land `KnowledgeBase` and `SourceConnector` (§4, §5) in `fred-sdk`, with contract fixtures/tests, no behavior yet.
2. Implement exactly one proof-of-concept pull knowledge base in `knowledge-flow-backend`, `kind=rag_sql`, against the simplest possible real connector (candidate: local filesystem or Minio/S3, since both already have working loaders to model the new contract against — Sphere/GitHub are harder cases, better attempted once the model is proven).
3. Validate the §7 invariant (no overlapping sync) end-to-end before calling the POC done.
4. Next phase (in progress, 2026-09-06): a `knowledge_base_type` usage-enablement gate (§6) mirroring Adrian's app-kind convention once it lands, an admin Features-tab entry, and a team Resources-tab surface for created `KnowledgeBase` instances.
5. Only after that: revisit `#2240` (§9), and consider a second `KnowledgeBaseType` (Sphere, GitHub, or a non-`rag_sql` kind) as the following increment.

## 11. Open questions

- Final name for `KnowledgeBase` — resolved 2026-09-07: "Knowledge Base" is this repository's canonical product vocabulary for this feature.
- Exact shape of `connector_ref` (opaque string id vs. a richer registration object) — deferred until the POC needs to actually resolve one.
- Where does per-`KnowledgeBaseKind` consumption policy configuration live — on the `KnowledgeBase` object itself, or entirely inside each pipeline's own code? Leaning toward the latter (keeps `KnowledgeBase` minimal) but not decided.
- Final name and shape of the `knowledge_base_type` ReBAC type (§6) — pinned to whatever Adrian's app-kind convention settles on, not decided independently here.
- Whether the admin Features-tab entry for a `KnowledgeBaseType` reuses the existing `CapabilityKind`-style filtered catalog UI (`CapabilitiesPage.tsx`) as an additional filter value, or gets its own page — leaning toward reusing the existing generic catalog/enablement UI pattern (same table, same per-team matrix drawer) since it already tolerates a new `kind`, but not decided.
- How a team's Resources tab represents multiple knowledge base instances (today it shows undifferentiated documents with no knowledge-base concept at all) — smallest-viable UI addition vs. a full knowledge-base switcher, not decided.
