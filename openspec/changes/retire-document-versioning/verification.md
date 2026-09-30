# Verification — retire document versioning

What is proven, how, and what is not. Written 2026-09-30, against
`feat/retire-document-versioning` stacked on PR #2876.

## Automated

| Suite | Result |
| --- | --- |
| `apps/knowledge-flow-backend` `make test` | 1513 passed, 41 deselected |
| `apps/knowledge-flow-backend` `make code-quality` | clean |
| `libs/fred-core` `make test` | 1028 passed, 40 deselected |
| `libs/fred-core` `make code-quality` | clean |
| `apps/frontend` `npx vitest run` | 3117 passed, 7 skipped |
| `apps/frontend` `npx tsc --noEmit` | exit 0 (checked as an exit code, not through `head`) |
| `apps/frontend` `npx prettier --check src/` | clean |
| `alembic heads` | one head, `02d556a6f182` |
| `alembic check` | no drift |

Migration-specific:

- `tests/alembic/test_alternate_version_migration.py` — 22 tests, the portable
  branch, offline, in `make test`.
- `tests/alembic/test_alternate_version_migration_postgres.py` — 14 tests, the
  PostgreSQL branch against a real PostgreSQL in a throwaway schema, driven
  through `create_async_engine` + `run_sync` so the DBAPI underneath is asyncpg,
  the one a deployment uses. Marked `integration` and `integration_postgres`, so
  excluded from `make test`.

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

59 documents, one alternate (`2-regl_PASSI_v2.2.pdf`, `version = 1`, base
already deleted).

- `alembic upgrade head` → the alternate kept its name, correctly: nothing else
  in its folder held that name.
- After: 59 documents, **0** still carrying `canonical_name` or `version`.
- `alembic downgrade -1` then `upgrade head` again → no further change, which is
  re-runnability proven on real data rather than only in a fixture.

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

## Review

`/code-review high` on the four-commit diff returned three findings. All three
were real and all three are fixed:

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

## Left open deliberately

- **`add_tag_id_to_document` has no name-collision guard**, unlike
  `rename_document`. That is what keeps the ambiguous import state reachable. It
  is a behaviour change of its own and does not belong in a removal change —
  worth its own issue.
- **Vector chunks keep their own copy of the document name** and the migration
  does not rewrite it, the same best-effort treatment the in-app rename gives it.
  A renamed document may be cited under its old name until re-vectorized.
  Recorded in the operator note.
- **The non-PostgreSQL name lookup is still a full scan** (#2860), untouched.
