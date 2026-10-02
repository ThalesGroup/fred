## Context

- `schema.fga`: `organization` carries everything platform-wide: roles,
  `suspended`, every `can_*` permission, and the subject of `default_on`,
  `personal_on` and `personal_disabled`. The reverse edges `organization#team`
  and `organization#personal_team` are injected as contextual tuples, the
  second only when the team id starts with `personal-`.
- `ORGANIZATION_ID = "fred"` (`rebac_engine.py`) is referenced in about 400
  places.
- A personal space has ReBAC tuples (owner self-grant) but **no** registry
  row: `teams/system.py` synthesizes it on each request. Its kind is inferred
  from the id by `is_personal_team_id` / `is_personal_team_ref`
  (`fred_core.common.team_id`) and by `teamId.ts` in the frontend, about 80
  backend call sites, runtime pods included.
- Runtime pods have no access to the team registry.

## Goals / Non-Goals

**Goals:** platform authority and team kind become explicit data; every
answer stays identical.

**Non-Goals:** making `organization` a tenant, organization roles, deleting
`team_manager` (step 2); projects; any UI change.

## Decisions

1. **One `platform` object, `platform:fred`.** The type says what it is; the id
   is one constant in `fred_core`, with no meaning beyond that. Alternative: an
   id taken from configuration. Rejected: there is exactly one platform per
   OpenFGA store, so configuring its id adds a setting and changes nothing.
2. **Everything platform-wide moves, `organization` keeps only `team`.** That
   covers roles, `suspended`, permissions, the catalog anchors, and the class
   markers (`default_on`, `personal_on`, `personal_disabled`), whose contextual
   reverse edges become `platform#team` and `platform#personal_team`. Leaving
   the markers on `organization` would have to be undone in step 2, because a
   catalog default is platform-wide, not per tenant.
3. **The personal space becomes a registry row** with `kind = personal` and an
   `owner_user_id`. It keeps its id and is created where the owner self-grant
   happens today, so creation stays in one place. Its `name` is its id, which
   satisfies the uniqueness constraint without colliding with a shared team;
   the UI already shows its own label for it.
4. **A single authority for kind.** In the backends, the registry answers it,
   through one `fred_core` function. The `personal` route alias resolves to the
   caller's registry row. Runtime pods receive `team_kind` next to `team_id` in
   their execution context. `is_personal_team_id` is deleted, and so is the
   frontend `startsWith("personal-")`; the frontend reads `team.kind`.
5. **Delete stale distinctions rather than port them.** Several runtime sites
   skip personal spaces on the grounds that they are "not real ReBAC teams",
   which has been false since personal spaces received their own tuples. Each
   site is checked: it is deleted if the distinction no longer holds, and
   ported to `team_kind` otherwise.
6. **Tuple migration is copy-only in this step.** A startup reconciliation,
   under the existing advisory lock, copies each platform-level tuple from
   `organization:fred` to `platform:fred`, idempotently. The old tuples stay,
   inert, so a rollback to the previous version still works. A cleanup change,
   once release 1 has run in production, deletes them.

## Risks / Trade-offs

- [A missed `organization` reference silently denies] → Model tests assert
  every permission on `platform`, and `organization` must keep no relation
  except `team`; plus a check that no `ORGANIZATION_ID` reference survives
  outside the team edge.
- [An extra registry read on hot paths] → The team row is already loaded where
  the kind matters, or the kind travels in the runtime context; no per-check
  query.
- [Personal rows for users who never used their space] → Register only the
  spaces that have an owner tuple, not every known user.

## Migration Plan

1. Alembic: add `kind` (default `shared`) and `owner_user_id` to
   `teammetadata`.
2. Startup reconciliation, under the advisory lock: the tuple copy
   (Decision 6), and registration of every personal space found among existing
   owner self-grant tuples. It is the only code allowed to read the legacy
   `personal-` prefix.
3. Rollback: the Alembic downgrade deletes the personal rows (the previous
   version would list them as shared teams) and the columns. The previous
   version ignores the `platform` tuples.
