# RFC — Per-User Personal Space Isolation

**Status:** Draft  
**Author:** Dimitri Tombroff  
**Date:** 2026-06-01  
**ID:** CTRLP-10  
**Area:** `fred-core`, `control-plane-backend`, `frontend`

---

## 1. Problem

`PERSONAL_TEAM_ID = TeamId("personal")` is a hardcoded constant shared by every
authenticated user. Every personal-space resource — agent instances, sessions,
knowledge resources, prompts — is stored under `team_id="personal"`. Any
authenticated user who knows (or guesses) this constant can read, modify, or
delete another user's personal data.

Observed breach (confirmed in testing):
- User Liam logs in and sees user Alice's personal agents.
- User Liam sees user Alice's conversation history.
- The same applies to resources and prompts.

`build_personal_team(_user)` accepts a `KeycloakUser` argument but silently
ignores it, returning the same constant for every caller. ReBAC registers every
user as `MEMBER` of the same shared `"personal"` team, making the problem
unfixable at the ReBAC layer without changing the team identity first.

---

## 2. Root cause

```python
# fred-core — fred_core/common/team_id.py
PERSONAL_TEAM_ID = TeamId("personal")   # ← shared by all users

# control-plane-backend — teams/system.py
def build_personal_team(_user: KeycloakUser) -> TeamWithPermissions:
    return TeamWithPermissions(
        id=PERSONAL_TEAM_ID,            # ← user argument ignored
        ...
    )

# fred-core — security/rebac/rebac_engine.py
Relation(
    subject=RebacReference(Resource.USER, user.uid),
    relation=RelationType.MEMBER,
    resource=RebacReference(Resource.TEAM, PERSONAL_TEAM_ID),  # ← same team for all
)
```

---

## 3. Decision

Replace the shared constant with a **per-user personal team ID** derived from
the user's Keycloak `uid`:

```
personal_team_id(user) → TeamId(f"personal-{user.uid}")
```

**Why this is the right approach:**
- Every user gets a truly isolated namespace with no shared state.
- No per-resource `user_id` filter needs to be added to every store — team
  isolation already covers it.
- ReBAC already works correctly for non-personal teams; personal teams become
  first-class team objects, identical in treatment.
- The frontend already receives the team ID from bootstrap and uses it
  dynamically — no frontend route changes are required.
- The `"personal"` string in URL routes becomes an opaque alias resolved at
  bootstrap time, not a load-bearing identifier.

**Why not per-resource user_id filtering (Option B):**
- Requires every store method (agents, sessions, knowledge, prompts, and any
  future resource type) to carry and enforce a `user_id` parameter.
- Fragile: new resource types silently miss the filter until a breach is
  discovered.
- Already demonstrated as insufficient — the session `list_by_team` fix done
  on this branch is the exact type of whack-a-mole this approach requires.

---

## 4. Proposed solution

### 4.1 fred-core

Replace the constant with a function. Keep the constant as a deprecated alias
pointing to `"personal"` for the migration period only.

```python
# fred_core/common/team_id.py

def personal_team_id(user_uid: str) -> TeamId:
    """Return the personal team ID for one user."""
    return TeamId(f"personal-{user_uid}")
```

Export `personal_team_id` from `fred_core.common`. Remove `PERSONAL_TEAM_ID`
from the public API once all callers are migrated.

Update `rebac_engine.py` to use `personal_team_id(user.uid)`.

### 4.2 control-plane-backend

Six call sites to update:

| File | Change |
|---|---|
| `teams/system.py` | `build_personal_team(user)` uses `personal_team_id(user.uid)` |
| `teams/system.py` | `get_team_by_id_from_service` branch: compare against `personal_team_id(user.uid)` |
| `product/service.py` (bootstrap) | Pass `personal_team_id(user.uid)` to `get_team_by_id_from_service` |
| `product/service.py` (session create) | Replace `PERSONAL_TEAM_ID` with `personal_team_id(user.uid)` |
| `product/service.py` (prompt context) | Same |
| `users/api.py` | Pass `personal_team_id(user.uid)` when fetching personal team |

`prompts/store.py` uses `literal("personal")` as a scope label in a query —
this label is cosmetic metadata, not a foreign key, and can remain `"personal"`
as a display string. No data integrity risk.

### 4.3 Frontend

No route or component changes required. The frontend receives the team ID from
`useFrontendBootstrap` → `activeTeam.id` and uses it dynamically throughout.
After the fix, `activeTeam.id` will be `personal-<uid>` and all navigation,
API calls, and URL construction will use that value automatically.

The fallback `?? "personal"` strings in components are pre-bootstrap guards.
They should be updated to `?? ""` (empty = no navigation) to avoid silently
routing to a stale team ID, but this is a cleanup item, not a blocker.

### 4.4 Database migration

**Dev / test environments:** Purge all rows with `team_id="personal"` across
`session_metadata`, `agent_instances`, `managed_mcp_servers`, `prompts`, and
any other team-scoped tables. Data created in a shared personal space has no
reliable owner and cannot be safely reassigned.

**Production (future):** If a production deployment accumulates data under
`team_id="personal"` before this RFC is applied, a migration script must
identify ownership from correlated tables (e.g., `session_metadata.user_id`,
`agent_instances.created_by`) and rewrite `team_id` to the correct
`personal-<uid>` value. This script must be written and reviewed before the
production cutover.

---

## 5. Alternatives considered

**Option B — per-resource `user_id` filtering:** Rejected. See §3.

**Keep `"personal"` as a URL alias resolved server-side:** The frontend could
continue navigating to `/team/personal/…` and the API would resolve `"personal"`
to `personal_team_id(current_user.uid)`. This avoids any URL-visible change
but adds a translation layer in every route handler. Deferred — can be added
later as a UX convenience without affecting the isolation model.

---

## 6. Impact on existing contracts

### CONTROL-PLANE-PRODUCT-CONTRACT — addition required

Add to the sessions and agent-instances sections:

> **Personal team isolation rule:** The personal team ID is `personal-{user.uid}`.
> No two users share a personal team. All team-scoped endpoints enforce isolation
> by team membership. No additional per-resource `user_id` filter is required or
> maintained for personal space resources.

### REBAC — no model change

The ReBAC model remains unchanged. Personal teams become real isolated team
objects. Each user is `MEMBER` of exactly one personal team (their own). The
existing `MEMBER` relation and team-scoped permission checks apply without
modification.

---

## 7. Decisions

1. **Personal team ID format: `personal-{uid}`** — confirmed. Readable in logs
   and DB queries, unambiguous prefix distinguishes personal teams from
   collaborative teams.

2. **Bootstrap alias `"personal"`:** Deferred to a follow-up. Not required
   for the isolation fix. The frontend uses the real ID from bootstrap.

3. **Session `user_id` filter (merged on branch `swift`):** Kept as
   defence-in-depth. Once CTRLP-10 ships, team isolation makes it redundant
   but harmless. It will not be removed — layered filtering is acceptable.
   The PATCH/DELETE ownership gap documented in BACKLOG §6.4.F should be
   fixed in the CTRLP-10 change.
