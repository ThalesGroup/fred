# Partition machine-written corpus folders from human ones

Tracking: GitHub issue #2687.

## Why

A Knowledge Base library is created through knowledge-flow's ordinary folder
endpoint, deliberately, so that one set of rules governs every folder. The cost
was never paid: nothing marks the result as machine-written, so a synchronized
library is indistinguishable from a folder people made.

Two consequences, both read off the code rather than reported:

- **Its documents are invisible on the page built to list them.** The Knowledge
  Base Documents page browses the library tag alone, and a document carries its
  leaf folder's tag, not the library's. A library mirroring a source tree
  reports zero documents and renders "holds no document yet" while working
  correctly. Nesting is the normal case, not an edge case — the git-repository
  sample mirrors an entire repository tree.
- **It is fully mutable from Resources.** It can be deleted, leaving the
  instance pointing at nothing and every later run failing on each write with
  nothing in the UI explaining why. It can be uploaded into by hand, and those
  documents carry no source key, so synchronization will never remove them:
  removal is addressed, never inferred.

## What Changes

- **A corpus folder can declare that a machine writes it.** A nullable,
  qualified owner reference on the library root, written by a service identity
  and never by a person. Everything nested under it derives its state from that
  root rather than carrying a copy. The pod that fills the library is what
  records it, once per run — it is the only party holding the right to write
  there, and the control-plane has no business writing into the corpus.
- **Human identities may not mutate such a folder's content.** No upload, no
  document added or removed, no subfolder created, no rename or move. Service
  identities keep exactly the ReBAC rights they hold today — the guard is added
  after the existing authorization check, never in place of it.
- **Deleting the folder stays available to people.** Deliberate, and the one
  asymmetry in this change; the reasoning and the alternative are in `design.md`.
- **Documents nested below a library are listed** by the page that lists a
  library's documents.
- **The create form's folder-name field is relabelled** so it asks for the
  folder it creates rather than for the name of the base. Wording only, in both
  locales: no spec-level behaviour changes, so no requirement covers it.

## Capabilities

### New Capabilities

- `synchronized-corpus-folders`: how a corpus folder written by a machine is
  marked, guarded against human mutation, and read back in full — including the
  documents nested below it.

### Modified Capabilities

None. The closest existing capability, `knowledge-base-ingestion`, still lives
in the unarchived `knowledge-base-ingestion-facade` change rather than under
`openspec/specs/`, so there is nothing to write a delta against. That change
should not be archived as it stands — see `design.md`, "A requirement that is
not true yet".

## Impact

- **`apps/knowledge-flow-backend`** — the folder model, the tag service, the
  metadata service, the ingestion upload path, and the library synchronization
  controller. No Alembic revision: a folder is stored as a JSON document beside
  its indexed columns, so the mark adds no table shape (see `design.md`).
- **`libs/fred-sdk`** — the pod's runtime declares its library once per run,
  between fetching the run context and invoking the handler, so no author
  writes it. Nothing in `apps/control-plane-backend` changes.
- **`libs/fred-core`** — the document store gains the descendants read the
  Documents page needs.
- **`apps/frontend`** — the Knowledge Base Documents page, the Resources
  document workspace, and both locales.
- **Generated API client** — regenerated in the same change, per the repository
  rule.

Explicit non-goals:

- **No change to who may delete a synchronized folder.** See above.
- **No new identity per Knowledge Base instance.** Cross-team isolation rests on
  the dispatched library id and therefore on the pod's own code. That is an
  entered decision, recorded in `design.md` so it is not later mistaken for a
  defect; revisiting it needs its own RFC.
- **No fix to KPI or log attribution of machine writes.** Tracked separately.
