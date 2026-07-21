# RFC — Per-User Personal Space Isolation

**Status:** Implemented — retired 2026-07-21. Kept as the historical decision
record only (naming choice, rejected alternatives). **Current design state:**
[`docs/swift/platform/REBAC.md` § Personal
teams](../platform/REBAC.md#personal-teams--self-provisioned-never-admin-writable-authz-08)
(ReBAC mechanism) and `id-legend.yaml` entries `CTRLP-10` (isolation shipped)
and `AUTHZ-08` (ReBAC tuple hardening + enumeration follow-up). Do not amend
this file further — amend the docs above instead.  
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
```

---

## 3. Decision — personal team ID format

Replace the shared constant with a **per-user personal team ID** derived from
the user's Keycloak `uid`: `personal_team_id(user) → TeamId(f"personal-{user.uid}")`.

**Why this is the right approach:**
- Every user gets a truly isolated namespace with no shared state.
- No per-resource `user_id` filter needs to be added to every store — team
  isolation already covers it.
- Personal teams become first-class team objects, identical in treatment to
  collaborative teams (see `REBAC.md` for how that treatment was later made
  real rather than synthetic — `AUTHZ-08`).
- The `"personal"` string in URL routes becomes an opaque alias, resolved
  server-side (`get_system_team` accepts both), not a load-bearing identifier.

**Why not per-resource `user_id` filtering:** requires every store method
(agents, sessions, knowledge, prompts, and any future resource type) to carry
and enforce a `user_id` parameter — fragile, since a new resource type
silently misses the filter until a breach is discovered. Team isolation
(the ID format above) covers every resource type by construction instead.

---

## 4. What shipped

Format `personal-{uid}` is exported as `fred_core.common.personal_team_id`.
Every control-plane and runtime call site that used to read the
`PERSONAL_TEAM_ID` constant now derives it per-caller; the bare `"personal"`
alias is resolved server-side at the API boundary, never stored. Full
implementation and shipped-branch detail: `id-legend.yaml` entry `CTRLP-10`.

Dev/test environments had all `team_id="personal"` rows purged at cutover (no
reliable per-row owner to reassign). No production deployment predated this
fix.

---

## 5. Confirmed decisions

1. **Personal team ID format: `personal-{uid}`.** Readable in logs and DB
   queries; unambiguous prefix distinguishes personal teams from
   collaborative teams.
2. **Bootstrap alias `"personal"` resolved server-side.** `get_system_team`
   recognises both `"personal"` (URL alias) and `"personal-{uid}"` (canonical
   ID); all data-access calls use the resolved `team.id`, never the raw path
   parameter.
3. **Session `user_id` filter kept as defence-in-depth**, redundant with team
   isolation but harmless.
4. **Agent `created_by` uses `user.username`, not `user.uid`.**

---

## 6. ReBAC treatment — see `REBAC.md`

This RFC originally specified "no ReBAC model change: each user is `MEMBER` of
exactly one personal team." That was never actually implemented — no code
path wrote a ReBAC tuple for a personal team until `AUTHZ-08` (2026-07-20).
The current, real design (self-provisioned `team_editor` tuple, write-guarded
at the one `add_relation` chokepoint, self-healed on both permission checks
and enumeration) lives in
[`REBAC.md` § Personal teams](../platform/REBAC.md#personal-teams--self-provisioned-never-admin-writable-authz-08) —
do not re-derive or re-amend it here.
