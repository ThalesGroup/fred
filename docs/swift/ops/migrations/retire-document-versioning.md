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
WHERE jsonb_typeof(doc->'identity'->'version') = 'number'
  AND (doc->'identity'->'version') > '0'::jsonb;
```

That is the migration's own test for an alternate, deliberately: comparing the
JSON number rather than casting it to `int` cannot fail on a value too large for
`int`, or on a hand-edited one that is not a number at all.

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
keeps the name it has.

Nothing is deleted, no `document_uid` changes, no folder membership changes, no
document is re-ingested or re-embedded, and a title a user typed is kept.

**Only those documents are written.** Every other document keeps the
`canonical_name` and `version` keys it already had in its stored JSON. They are
inert — the application's document model no longer declares either field and
ignores both on read — and each document drops them the next time anything saves
it. Clearing them for the whole corpus up front was measured at 20 seconds and
1.1 GB of WAL at 500,000 documents, against a 30-second statement timeout, and
would have failed the upgrade on a large platform to tidy data nothing reads.

Cost is therefore proportional to the number of alternate versions, not to corpus
size: one indexed lookup per candidate name. A corpus with none does no work.

The whole migration runs in one transaction, as every Alembic migration on this
platform does. An interrupted upgrade leaves the database exactly as it was and
is safe to retry from the start; a completed one finds nothing left to do if run
again.

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
Documents still carrying `version: 0` in their stored JSON are expected and
harmless — see **Upgrade**.

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

The previous note's limitation is narrowed, not closed. Alternate versions are
gone, so they are no longer how a folder ends up holding two documents of one
name — but two other paths still are: two concurrent imports of the same name
(the pre-upload name check is not repeated at write time), and adding an existing
document to a folder that already holds its name, which is unguarded unlike a
rename (#2877). In that state the import still refuses the name and now tells the
user to rename or delete one of the two, an instruction they can actually act on;
previously it told them to promote an alternate version, which was never an
action the product offered.

Two consequences of a rename, for the few documents the migration renames:

- **A renamed spreadsheet's SQL alias changes.** `build_default_query_alias`
  derives the DuckDB relation name from the document name, so `sales.csv` renamed
  to `sales (1).csv` moves from `d_<uid>_sales` to `d_<uid>_sales_1`. A saved
  query or client naming the old alias is rejected after the upgrade and has to
  be pointed at the new one.
- **A renamed document keeps the title a user typed for it**, deliberately: a
  migration carries none of the intent that makes a hand-driven rename supersede
  it. Where such a title exists, the Resources table shows it with the
  "Embedded title" hint, as it does for any document whose title and file name
  differ.

Vector chunks keep their own copy of the document name for citation display, and
the migration does not rewrite it — the same best-effort treatment the in-app
rename already gives it. A renamed document may therefore be cited under its old
name until it is re-vectorized. Re-vectorizing it from the corpus admin page
updates the copy; nothing else is affected.
