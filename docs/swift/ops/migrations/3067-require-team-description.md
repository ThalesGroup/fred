---
schema: 1
title: "Team descriptions become required"
impact: minor
configuration: none
configuration_reason: "Only the teammetadata.description column, the team API and the UI change; no configuration keys, environment variables or Helm values change."
---

## Applicability

Every Fred deployment. Teams without a description, or with one shorter than 20
characters, are affected by the data migration.

## Prerequisites

Before upgrading, count the teams that will receive the default description
(read-only, on the control-plane database):

```sql
SELECT count(*) FROM teammetadata
WHERE description IS NULL OR length(trim(description)) < 20;
```

No preparation is required: the count only tells you how many team
administrators will have a description to write.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The control-plane database migration (revision
`c9acb7dd3ad0`) runs with the usual `alembic upgrade head` step:

1. Every team whose description is missing, blank or shorter than 20 characters
   receives the default text « Description à compléter par l'administrateur de
   l'équipe. ». Valid descriptions are kept, without surrounding spaces.
2. `teammetadata.description` becomes `VARCHAR(500) NOT NULL`, with the check
   constraint `ck_teammetadata_description_min_length` (at least 20 characters
   once trimmed).

After the upgrade:

- Creating a team requires a description of 20 to 500 characters.
- A team description can be edited but no longer cleared.
- Team administrators of a team carrying the default text see a reminder on
  the team's home page and in its settings. Ask them to write it: the
  description is shown on every marketplace team card.
- A platform import never fails on a description: imported teams without a
  valid one receive the default text, and the import report states how many.

## Validation

List the teams that still carry the default description:

```sql
SELECT id, name FROM teammetadata
WHERE description = 'Description à compléter par l''administrateur de l''équipe.';
```

In the UI, open the administration teams page: the create form refuses to
submit without a description of at least 20 characters. Open the marketplace
teams page: every card shows a description.

## Rollback

Downgrade the control-plane database to revision `93427a5fe874` **with this
release**, then redeploy the previous one: the previous release does not know
the revision and cannot downgrade it. A previous control-plane running against
the upgraded database cannot create a team (it sends no description, the
database refuses the row and the API answers a misleading 409), so do not leave
both in place. The same holds during a rolling update: team creation can fail
on the old pods until they are replaced.

The downgrade restores an optional `VARCHAR(180)` column and is lossy:

- descriptions equal to the default text are cleared (`NULL`);
- descriptions longer than 180 characters are **cut to their first 180
  characters**. Export them first if they must be kept:

```sql
SELECT id, name, description FROM teammetadata WHERE length(description) > 180;
```

## Limitations

- `POST /teams` now requires `description`, and `PATCH /teams/{team_id}`
  refuses `description: null` or a value outside 20 to 500 characters (422). Only
  the Fred frontend and the platform importer call these routes; adapt any
  custom client.
- The default text is stored in French whatever the platform language; the UI
  shows it translated.
- The Knowledge Flow storage backfill script from an older release cannot
  create missing team records on an upgraded database; use the script shipped
  with this release.
- Direct SQL writes to `teammetadata` must provide a description of at least
  20 characters.
