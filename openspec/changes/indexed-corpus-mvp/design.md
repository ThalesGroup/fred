## Context

See proposal.md - Why. FRED's only prior pull-mode attempt (a Sphere connector, still live in a different, older fork — not in this repository) is documented here as evidence, not as something this design extends: full remote rescan every cycle despite an incremental delta API existing but disabled, no stable revision id (diffed by a raw modified-timestamp string), a changed file minted a brand-new document id with the old one explicitly deleted to fake an update, no leader election across replicas (safe only because that deployment ran a single replica), in-memory-only sync status, and heavy business-logic coupling inside what should have been a generic sync engine. Every decision below closes one of these failure modes structurally, not by adding a check on top of the same shape.

FRED already has one relevant precedent to build on rather than reinvent: the agent-template/agent-instance split (`control_plane_backend/agent_instances/`) for "a platform-wide registered thing" vs. "a team's own instantiation of it," and the `capability` OpenFGA object (`fred_core/security/rebac/schema.fga`) for "admin enables this platform-wide thing per team." This design reuses both shapes rather than inventing new ones.

## Goals / Non-Goals

**Goals:**
- One narrow, provider-agnostic contract (`SourceConnector`) that structurally prevents the specific Sphere failure modes above, not just documents against them.
- Split "what can exist on the platform" (`CorpusType`) from "what a team actually has" (`Corpus` instance), reusing the agent-template/agent-instance precedent.
- A usage-enablement gate that is its own ReBAC object type, not a repeat of the `capability:app__<id>` namespacing mistake already being corrected elsewhere for `app`.
- Reuse FRED's existing push ingestion pipeline for pull-sourced documents rather than building a parallel one.

**Non-Goals:**
- Building an external, independently-deployed connector pod (an in-process library inside `knowledge-flow-backend` is the assumed shape for this MVP).
- Any scheduler or trigger mechanism for running a corpus instance's synchronization — this change specifies that synchronizations for one instance must not overlap (see specs/indexed-corpus/spec.md), not how or when a synchronization is invoked.
- A second `CorpusType`, `graphrag`/`llm_wiki` kinds, or an admin/team-facing UI — later increments.
- Reconciling with the older, unrelated GitHub issue `#2240` (an external-pod processor/connector design) — a separate decision once this MVP has produced evidence.

## Decisions

**D1 — Two objects, not one (`CorpusType` + `Corpus`), not a bare connector.** A bare connector (discover/fetch only) says nothing on its own about what an agent gets from it — it is not a unit worth registering, enabling, or showing an admin. `CorpusType` (platform-wide: `kind` × `mode` × `connector_kind`) is what a developer contributes and an admin enables; `Corpus` (team-scoped: `scope` × `connector_ref`) is what a team creates once its type is enabled. Alternative considered and rejected: a single `Corpus` object carrying both platform-wide and team-scoped fields together (the MVP's first iteration) — rejected because `mode` and `connector_kind` are intrinsic to which type is being instantiated, not a per-instance choice, and conflating the two objects would force every instance-creation path to re-decide platform-wide facts.

**D2 — `SourceConnector` identity is two fields, not one.** `source_item_id` (stable, provider-defined) and `revision` (content-addressed where the provider offers it) are separate fields, never derived from a display path or a mutable timestamp — directly closing the Sphere failure mode of diffing by a raw timestamp string. A rename is representable as "same `source_item_id`, new `display_path`"; "nothing changed" is provable from `revision` alone, without re-fetching content. Alternative considered: deriving identity from a hash of the display path (what the dead, pre-existing `SphereContentLoader` in this codebase did) — rejected for the same reason it failed before: it cannot represent a rename and provides no real change detection.

**D3 — Deletion is a first-class change kind.** The connector reports `DELETE` explicitly rather than the caller inferring it by diffing two listings — removes an entire class of bugs where a partial or failed listing looks like "everything was deleted."

**D4 — Pull-sourced documents reuse the exact push ingestion primitives.** `sync_pull_corpus` calls `extract_metadata`/`save_input`, `push_input_process`, and `output_process` — the same functions a manual upload already calls — rather than a parallel pull-specific pipeline. A changed source item is handled as delete-then-recreate (a new document id), not update-in-place; this is an accepted limitation carried over from the evidence in Context, not a new gap introduced here.

**D5 — Usage enablement is its own OpenFGA type (`corpus_type`), not a namespaced `capability` id.** `capability` is reserved for "something an agent uses"; a corpus type's creation/operation permission is not that, any more than an application's is. This mirrors a parallel, in-progress move a teammate is making for `app` off the same `capability:app__<id>` namespacing pattern this design deliberately does not repeat. The new type omits `capability`'s personal-space overlay (`personal_on`/`personal_disabled`) — not needed yet; a personal team still inherits `default_on` like any other team through the same contextual edge.

**D6 — `CorpusType` is deployment configuration; `Corpus` is a database row.** Mirrors the existing `ApplicationSourceConfig` precedent exactly: a corpus type is contributed by a developer/operator, not created through a product API, so it needs no table — `CorpusTypeConfig` subclasses `fred_sdk.contracts.corpus.CorpusType` directly rather than redeclaring its fields. A `Corpus` instance is genuinely new, team-created runtime state, so it is a Postgres row (`corpus` table, mirroring `agent_instance`'s shape: plain string primary key, indexed `team_id`, JSON-serialized `tag_ids` in a `Text` column matching the codebase's existing convention for structured-but-flexible fields).

**D7 (open, tracked as a task) — Where `Corpus`/`CorpusType` config is read from during synchronization, and where sync state lives.** `Corpus`/`CorpusType` are owned by `control-plane-backend` (D6); the synchronization engine runs in `knowledge-flow-backend` (where the existing ingestion pipeline already lives). The decision already reached in design discussion: read `Corpus`/`CorpusType` from control-plane once per synchronization cycle (not once per file — a low-frequency read, mirroring `fred-runtime`'s existing `initialize_control_plane_client()` pattern), and keep the synchronization's own cursor/state (`{source_item_id: document_id}` plus the connector's opaque cursor) in a small `knowledge-flow-backend`-owned table next to `kf_task_run`/`kf_task_event_log`, never round-tripped through control-plane. Not yet implemented — see tasks.md.

## Risks / Trade-offs

- **[Risk] The `corpus_type` ReBAC schema addition could diverge from Adrian's separate `app`-kind convention if his lands with a different shape.** → Mitigation: `libs/fred-core/fred_core/security/rebac/schema.fga` already carries `corpus_type` as a minimal, easily-adjusted type (six relations); reconciling means adjusting this one block, not a rewrite. Do not extend `corpus_type` further (e.g. a personal-space overlay) until his convention lands.
- **[Risk] Redundant synchronization cost when multiple corpus instances pull the same external source.** → Accepted trade, not mitigated: each instance runs its own independent connector, cursor, and cost, in exchange for zero cross-instance coordination. Documented as a deliberate simplicity choice, not an oversight.
- **[Risk] A changed source item is delete-then-recreate, not update-in-place, so a document id referenced elsewhere (a link, a citation) stops resolving after any content change.** → Accepted limitation carried over from evidence in Context; revisit only if a concrete downstream consumer needs stable document ids across content changes.
- **[Trade-off] No scheduler/trigger is specified in this change (Non-Goals), so nothing currently invokes `sync_pull_corpus` outside a test.** → The no-overlapping-synchronization requirement (specs/indexed-corpus/spec.md) is specified now, ahead of the trigger mechanism, precisely so whatever trigger is chosen next is designed against an already-fixed constraint rather than retrofitted around one.

## Migration Plan

No migration of existing data: this is new capability, not a change to existing behavior. The one schema migration involved (`corpus` table, `apps/control-plane-backend/alembic/versions/57f8e7e05006_add_corpus.py`) is additive-only (`create_table`) with a verified symmetric `downgrade()`. `docs/swift/rfc/INDEXED-CORPUS-RFC.md` is left in place, not deleted, until this change is archived and its content is confirmed to have carried over completely (see tasks.md).

## Open Questions

- Final id/name for the `corpus_type` ReBAC object once Adrian's `app`-kind convention lands (tracked in tasks.md, does not change this change's specs or approach).
- Whether the admin Features-tab entry for a `CorpusType` reuses the existing capability-kind-filtered catalog UI (`CapabilitiesPage.tsx`) as an additional filter value, or gets its own page — a later increment's decision, not this one's.
- How a team's Resources tab represents multiple corpus instances, given it shows undifferentiated documents today with no corpus concept at all — a later increment's decision.
