# RFC — Corpus re-vectorization (products rebuild, post-migration embeddings)

**ID:** MIGR-07 · **Status:** backend done — issue [#2111](https://github.com/ThalesGroup/fred/issues/2111).
Closed out 2026-07-25; one open item remains (below).
**Owner:** Dimitri · **Surface:** knowledge-flow-backend (+ migration UI trigger)
**Sibling of:** [`PLATFORM-IMPORT-RFC.md`](PLATFORM-IMPORT-RFC.md) (the **products**
topic that runs after **metadata** import).
**Operational model:** [`ops/KEA_SWIFT_CUTOVER.md`](../ops/KEA_SWIFT_CUTOVER.md).

---

## Closed out — see the canonical contract

Built as designed: `RevectorizeCorpusWorkflow`/`RevectorizeDocument` Temporal
workflows over the existing `output_process` activity, a new
`list_documents_in_scope` activity, `/corpus/revectorize` wired to a real
`task_run` + workflow, and the `source_tag` scope-authorization gap fixed
alongside.

**No knowledge-flow-backend equivalent of `CONTROL-PLANE-PRODUCT-CONTRACT.md`
exists yet** — flagged to Dimitri rather than created unilaterally. Until that
doc exists, the full contract (endpoint shape, workflow/activity boundary,
scope semantics, authorization rule) lives in
**[`CONTROL-PLANE-PRODUCT-CONTRACT.md` §28](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md#28-contract-notes--migr-07-corpus-re-vectorization-finalized-2026-07-25)**
as an interim canonical record. This file stays only as a closed-out design
record; the original problem statement, alternatives, and risks-now-resolved
discussion are in `git log -p -- docs/swift/rfc/CORPUS-REVECTORIZE-RFC.md`.

**Remaining open item:** MIGR-07.04 — the migration UI's "Rebuild embeddings"
final-step trigger button (reuse the same task atoms already used by import).
A real future item, not yet built.
