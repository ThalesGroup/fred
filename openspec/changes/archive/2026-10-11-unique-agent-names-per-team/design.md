## Context

See proposal.md for the why. Agent instances live in the control plane table `agent_instance` (`display_name String(255) NOT NULL`, `team_id` indexed, hard delete). The personal space is a team (`personal-<uid>`), so a per-team rule covers it.

Names are written by:
- `enroll_agent_instance` and `update_agent_instance` (`product/service.py`), which raise `EnrollmentError(http_status)`;
- `copy_agent_instance_to_team` (`product/agent_copy.py`), where the copy name comes from `_copy_name` (exact, case-sensitive check) and a duplicate takes the user's name unchecked;
- the platform importer (`import_export/importer.py`), which inserts rows as they are.

Prompts already enforce `UniqueConstraint("team_id", "name")`, translate the `IntegrityError` into a store error, and map it to a 409 with a `code` that the form reads.

## Goals / Non-Goals

**Goals:**
- One rule, enforced by the database, with the service turning a violation into a readable 409.
- The frontend marks the name field, as the prompt form does for its command.

**Non-Goals:**
- Uniqueness across teams, or of other agent fields (role, description).
- Changing the `_imported-<n>` copy naming or the copy dialog.

## Decisions

1. **A unique functional index on `(team_id, lower(display_name))`.** The database is the only place that closes the race between two concurrent creations or copies, which the copy design accepted until now. Every write path stores the name trimmed, so `trim` is not indexed: PostgreSQL reflects `trim(x)` as `TRIM(BOTH FROM x)`, which the autogenerate check reads as a different index (the existing `ix_users_lower_username` follows the same `lower(...)` pattern).
   - **Alternative:** a stored `normalized_name` column. Rejected: one more column to keep in sync for something an expression index does on its own.
2. **Trim on write, compare normalised.** The request schemas strip `display_name` (a validator, so the OpenAPI shape does not change), and every comparison in Python uses the same `normalize_agent_name = lower(strip)`. Case is kept as typed.
3. **Store error, service 409.** The store catches the `IntegrityError` of that index and raises `AgentNameAlreadyExistsError`. Enroll, update and duplicate map it to `EnrollmentError(409, code="agent_name_conflict")`; `EnrollmentError` gains the optional `code` that `PromptRequestError` already has, and the API puts it on the body. The service also checks before writing, so the common case fails fast without a rolled-back transaction; the index stays the guarantee.
4. **Copy and import rename.** `_copy_name` compares normalised names. On an index violation (a concurrent copy took the name), the copy recomputes the name once and retries; a second failure is reported for that destination like any other. The importer applies the same `_imported-<n>` rule against the target team's names before inserting.
5. **Migration renames, then indexes.** One Alembic revision, re-parented on the current head:
   - trim every `display_name`;
   - for each team, group agents by normalised name and order each group by `created_at`, then id;
   - keep the first one, rename the others `<name> (n)` with the first n ≥ 2 still free in the team, cutting the base so the result fits 255 characters;
   - create the unique index.

   The downgrade drops the index and does not restore the old names.
   - **Alternative:** fail the migration and list the duplicates. The owner chose automatic renaming.
6. **Frontend: checked on blur, server as backstop (owner decision).** `TeamAgentsPage` already holds the team's full agent list (the endpoint is not paginated). It passes the normalised names of the other agents (the edited one excluded) to `AgentFormModal` and `DuplicateAgentDialog`.
   - When the name field loses focus, a taken name shows an error under the field, and the submit button stays disabled until the name changes. The person learns it before clicking Create.
   - The duplicate dialog opens on the first free `<name> (n)` instead of the source's own name, which is always taken in its team.
   - The 409 `agent_name_conflict` remains, for a name taken in the meantime. A Duplicate goes through the copy endpoint, whose per-destination results gain `error_code` for the same purpose. It is read from the error body and shown on the same field instead of the toast; other errors keep the toast.
   - **Alternative:** a server "is this name free" endpoint on blur. Rejected: the list is already loaded, and a new endpoint would add a round trip for the same answer.

## Risks / Trade-offs

- [The migration renames agents users know by name] → It keeps the oldest one, only touches real collisions, and the migration note asks operators to list them beforehand with the query it provides.
- [SQLite in tests vs PostgreSQL in production: `lower` on non-ASCII] → SQLite's `lower` only folds ASCII. Tests use ASCII names; PostgreSQL folds Unicode. Documented in the test.
- [A concurrent copy loses the race twice] → It is reported as a failed destination; the user retries.

## Migration Plan

Deploy normally; the control-plane database migration of the deployment applies the revision. The migration note gives a read-only SQL query to list colliding names before the upgrade. Rollback: downgrade drops the index; renamed agents keep their new names.
