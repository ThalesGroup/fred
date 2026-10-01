# Verification — retire document versioning

What is proven, how, and what is not. Written 2026-09-30, against
`feat/retire-document-versioning` stacked on PR #2876.

## Automated

| Suite | Result |
| --- | --- |
| `apps/knowledge-flow-backend` `make test` | 1516 passed, 44 deselected |
| `apps/knowledge-flow-backend` `make code-quality` | clean |
| `libs/fred-core` `make test` | 1031 passed, 40 deselected |
| `libs/fred-core` `make code-quality` | clean |
| `apps/frontend` `npx vitest run` | 3117 passed, 7 skipped |
| `apps/frontend` `npx tsc --noEmit` | exit 0 (checked as an exit code, not through `head`) |
| `apps/frontend` `npx prettier --check src/` | clean |
| `alembic heads` | one head, `02d556a6f182` |
| `alembic check` | no drift |

Migration-specific:

- `tests/alembic/test_alternate_version_migration.py` — 25 tests, the portable
  branch, offline, in `make test`.
- `tests/alembic/test_alternate_version_migration_postgres.py` — 17 tests, the
  PostgreSQL branch against a real PostgreSQL in a throwaway schema, driven
  through `create_async_engine` + `run_sync` so the DBAPI underneath is asyncpg,
  the one a deployment uses, against the disposable PostgreSQL
  `scripts/docker-compose.postgres.yml` provisions — never the dev stack's own
  database. Marked `integration` and `integration_postgres`, so excluded from
  `make test`.
- `libs/fred-core/.../test_identity_ignores_retired_versioning_keys.py` — 3 tests
  for the contract that lets the migration leave the keys in place: a document
  still carrying them reads correctly and neither reaches the API. Fails if
  `Identity` ever gains `extra="forbid"`, which is what would break every
  unmigrated document.

## Every fix was verified by breaking it first

Each was reverted and the test watched to fail, per the branch's standing
practice:

| Change | Failure seen when reverted |
| --- | --- |
| `CASE` guard around the `version` cast | `invalid input syntax for integer: "not-a-number"` |
| Keeping an orphaned alternate's name | 2 tests fail — the orphan and the other-folder case |
| Suffix before the extension | 8 tests fail |
| Skipping a nameless alternate | `doc` column becomes NULL, row undeserialisable |
| `CAST` inside `to_jsonb` | `could not determine polymorphic type because input has type unknown` |

The last one is the class of failure `test_postgres_document_store_sql.py`
records from production, reproduced here. Checked separately: psycopg2 rejects
that statement too, so the driver swap was a coverage gap in what the test
claimed to cover, not proof that psycopg2 would have missed this particular bug.

## Against the developer's real database

59 documents, one alternate (`2-regl_PASSI_v2.2.pdf`, `version = 1`, base already
deleted). `alembic upgrade head` left it under its own name, correctly: nothing
else in its folder held that name.

**What that run did not prove.** Its one alternate was an orphan, so the rename
path never ran on real data — only the keep-the-name path did. And the
`downgrade -1` / `upgrade head` cycle first offered here as "re-runnability
proven" proves nothing: `downgrade()` is empty, so only the `alembic_version` row
moved and the data stayed migrated, after which the second upgrade matched zero
rows. A migration that wrongly re-suffixed `report (1).pdf` into
`report (1) (1).pdf` would have produced the same "no further change" result.
Re-runnability is established by the tests below, not by that cycle.

That database is also no longer a witness for the current behaviour: an earlier
revision of this change cleared `canonical_name` and `version` from every
document, and running it stripped them there for good, so it now shows zero rows
carrying either key where the shipped migration would have left them. The pass
that did it was removed — see the next section.

What does exercise the rename path, including on data the dev corpus does not
have, is `test_alternate_version_migration_postgres.py`: a real PostgreSQL,
driven through asyncpg exactly as a deployment drives it.

## Why the fields are left on ordinary documents

The change originally stripped `canonical_name` and `version` from every stored
document, on the reasoning that a dead field reading like a live one misleads the
next reader. The guard was `WHERE doc -> 'identity' ?| ARRAY[...]` — which filters
nothing, because the old model defaulted `version` to 0 and always backfilled
`canonical_name`, so essentially every row carries both (58 of 59 on the
developer's own corpus).

That made it a full-table JSONB rewrite. Measured on a replica of the real table
with its real indexes: 2.5 s at 100k documents, 20 s and 1.1 GB of WAL at 500k —
against the 30 s `statement_timeout` `fred_core.sql.alembic_env` sets, inside the
single transaction it wraps every migration in, behind a Helm pre-upgrade hook
that retries from zero. Past roughly 300k documents it cancels, rolls back the
renames with it, and fails the release. A corpus with no alternates at all paid
the whole cost.

The pass is gone. The keys stay in storage on documents nothing renamed; the
model no longer declares either field, so they are ignored on read and dropped
the next time anything saves the document.

**Transactions.** Alembic runs the whole migration in one transaction, so it
lands entirely or not at all — an earlier comment here and in the operator note
claimed per-document statements made a partially-applied run safe to resume,
which was wrong. Re-running a completed migration finds nothing to do because the
fields it selects on are gone from the rows it touched.

## The scan each deletion no longer makes

`get_all_metadata` with the exact filters `_promote_alternate_version` passed,
timed on a throwaway PostgreSQL schema, median of 7 runs after a warm-up:

| Corpus | Median | Min | Max |
| ---: | ---: | ---: | ---: |
| 45 | 8.1 ms | 4.2 | 10.5 |
| 545 | 46.4 ms | 33.4 | 149.7 |
| 5045 | 438.3 ms | 402.1 | 526.4 |

Same shape as the figures on #2844 (6 / 36 / 355 ms), which were measured
differently on the same class of machine.

**What this does not prove.** It measures the removed call in isolation, not an
end-to-end deletion. #2844 reports ~20 s per deletion and names other costs this
change does not touch — two blocking calls on the event loop among them. One of
its two scans is gone; #2844 stays open.

## Review — two passes

`/code-review max` on the finished diff returned fifteen findings, two of which
would have failed a deployment. Both are fixed and covered by tests:

1. **The blanket field strip was a full-table rewrite** that could exceed the
   statement timeout — see the section above. Removed.
2. **`(doc->'identity'->>'version')::int` overflows int4.** The old model bounded
   `version` below with `ge=0` and never above, so an archive imported from
   another deployment could carry any magnitude; the cast aborted the whole
   upgrade with `NumericValueOutOfRangeError`. The predicate is now cast-free —
   `jsonb_typeof(...) = 'number' AND (...) > '0'::jsonb` — which also made the
   two branches agree on a numeric-string `version`, where the regex form
   renamed a document the portable branch left alone.

Also fixed from that pass: a scalar `identity` passed the strip's `?|` guard and
failed on `- 'version'` (moot with the strip gone, and now tested); the portable
branch raised `AttributeError` on a non-dict `identity`; `ORDER BY document_uid`
used the database collation while the portable branch used Python codepoint order
(now `COLLATE "C"`); `INGESTION.md` and the operator note both asserted an
invariant — "a folder never holds two documents a user cannot tell apart" — that
this diff's own docstrings contradict; the name-check endpoint still promised a
write-time re-check that the removed flag was the last thing performing; the
operator's pre-flight SQL used the very unguarded-cast pattern the migration
avoids; the user-facing locale strings still said "remove the duplicate" while
only the backend tooltip was reworded, with the test fixture pinned to the
retired sentence; the RFC pointed at an archive directory that does not exist and
was left far thicker than CLAUDE.md allows; and the consumer audit was scoped to
field names rather than to the mechanism (see design.md).

An earlier `/code-review high` pass on the same work returned three findings,
all real and all fixed:

1. **high** — a nameless alternate would make `jsonb_set` return NULL and blank
   the whole `doc` column, after which every listing containing that row fails to
   deserialise, taking the folder page with it. The portable branch guarded this;
   the PostgreSQL branch did not. Now skipped, with a test.
2. **medium** — `AMBIGUOUS_CONFLICT_MESSAGE` told users to "promote the alternate
   version", an action this change deletes. The ambiguous state is still
   reachable, so the message was a dead end rather than dead code: it now says to
   rename or delete one of them. Two docstrings claiming the state was possible
   "only while alternate versions exist" were corrected to name the real cause.
3. **low** — the PostgreSQL test ran on psycopg2 while migrations run on asyncpg.
   Converted, as above.

That an `high` pass found three and a `max` pass then found fifteen — two of them
deployment-breaking, one of them introduced by a fix from the first pass — is the
useful fact to carry forward from this change.

## Left open deliberately

- **`add_tag_id_to_document` has no name-collision guard**, unlike
  `rename_document`. That is what keeps the ambiguous import state reachable. It
  is a behaviour change of its own and does not belong in a removal change —
  filed as #2877.
- **Vector chunks keep their own copy of the document name** and the migration
  does not rewrite it, the same best-effort treatment the in-app rename gives it.
  A renamed document may be cited under its old name until re-vectorized.
  Recorded in the operator note.
- **The non-PostgreSQL name lookup is still a full scan** (#2860), untouched.
- **The scheduler pull path lost its only same-name bound** — #2880, with the
  design question it needs answered first. See design.md.
- **No CI job runs the PostgreSQL migration tests.** `make test` excludes
  `integration`, `test-integration`/`-only` exclude `integration_postgres`, and
  knowledge-flow's CI `integration-target` is empty, so only the manual
  `make test-integration-postgres` runs them. The branch that runs on a
  deployment is therefore ungated, which is how two of the findings above could
  have reached production with every check green. Wiring it needs Postgres added
  to `docker-compose.integration.yml`; out of scope here, worth its own change.
- **Two undisclosed effects of a rename**, both consequences of keeping `title`:
  a migrated alternate keeps it, so `documentNaming.ts` no longer suppresses the
  "Embedded title" hint on that row; and `build_default_query_alias` derives the
  DuckDB relation name from `document_name`, so a renamed CSV's alias changes and
  a client naming the old one is rejected after the upgrade.
