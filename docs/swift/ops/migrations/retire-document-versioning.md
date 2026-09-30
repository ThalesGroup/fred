---
schema: 1
title: "Hidden alternate document versions are retired and renamed"
impact: minor
configuration: none
configuration_reason: "No configuration key, default or secret changes; the migration runs as part of the knowledge-flow Alembic upgrade and the behaviour it replaces is unconditional."
---

## Applicability

Existing Fred deployments upgrading to this release. Only deployments whose
corpus contains alternate versions are affected by the data migration; the code
removal applies everywhere.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure. The
same-name import question this change relies on shipped in the previous release
("Imports ask before replacing a document of the same name") and must be present
before this one, which removes the mechanism it replaced.

Before upgrading, you can see exactly which documents the migration will rename:

```sql
SELECT document_uid,
       doc->'identity'->>'document_name' AS name,
       tag_ids
FROM metadata
WHERE doc->'identity'->>'version' ~ '^[0-9]+$'
  AND (doc->'identity'->>'version')::int > 0;
```

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The knowledge-flow Alembic upgrade runs migration
`02d556a6f182`, a **data migration** over the `metadata` table.

Each document that carried a hidden alternate version becomes an ordinary
document. Where its folder already holds another document of that name, it is
renamed — `report.pdf` becomes `report (1).pdf`, with the number increasing past
any name a third document already holds, checked in every folder the document
belongs to. A document whose base was already deleted collides with nothing and
keeps the name it has. The `canonical_name` and `version` fields are removed from
every document's identity.

Nothing is deleted, no `document_uid` changes, no folder membership changes, no
document is re-ingested or re-embedded, and a title a user typed is kept. The
migration updates one document per statement and skips documents already done, so
an interrupted upgrade is safe to re-run.

Cost is proportional to the number of alternate versions, not to corpus size: one
indexed lookup per candidate name. A corpus with none does no work.

Two behaviour changes needing no operator action:

- Deleting a document no longer promotes a hidden replacement in its place. There
  are none left to promote.
- `canonical_name` and `version` are gone from the document identity returned by
  the Knowledge Flow API. No Fred UI code read them. A non-UI client that reads
  either field must stop; a client that *writes* them is unaffected, as they were
  already ignored on input.

## Validation

In a team folder that held a base document and its alternate version, both now
appear under distinct names — the second as `<name> (1).<ext>` — and both open.
Deleting the first leaves the second exactly where it is, under its own name.

Re-running the SQL from **Prerequisites** after the upgrade returns no rows.

## Rollback

Use the normal rollback procedure for code and chart. The Alembic downgrade for
this revision is deliberately empty and **the rename is not reversible**: once
two documents carry names of their own, nothing records which of them used to be
the hidden one, so restoring that distinction would mean inventing it.

Rolling the code back is still safe. The renamed documents are ordinary
documents, valid on the previous release, which simply treats them as two
unrelated files — which is what they now are.

If a specific name must be restored, rename the document in the UI.

## Limitations

This release closes the limitation the previous note recorded: a folder can no
longer hold two documents sharing a display name, so a name can always be
replaced on import.

Vector chunks keep their own copy of the document name for citation display, and
the migration does not rewrite it — the same best-effort treatment the in-app
rename already gives it. A renamed document may therefore be cited under its old
name until it is re-vectorized. Re-vectorizing it from the corpus admin page
updates the copy; nothing else is affected.
