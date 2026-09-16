## Context

See proposal.md for the motivation and specs/team-admin-charter/spec.md for the required behaviour.

Observed state on `swift` that shapes the approach:

- `team_admin` is a direct OpenFGA relation (`schema.fga`, `type team`). `team_member` is the union of every team role, and five permissions (`can_update_info`, `can_administer_*`) plus the two evaluation permissions derive from `team_admin`.
- `team_admin` is written in five places: `add_team_member`, `grant_team_member_role` and `rescue_team_admin` through `_add_team_member_relation`, `create_team` for the initial admins, and the import bundle through `_grant_team_role_via_import`.
- The last-admin guard and the rescue "orphaned team" check count `team_admin` subjects. `my_relations` and the member list fold direct relations into `UserTeamRelation`.
- The control-plane already repairs the `organization -> team` edge at startup under an advisory lock (`_reconcile_team_organization_relations`), fail-closed.
- Legal markdown is static frontend content shadowed by the theme archive; `GcuPage` and `GdprPage` each carried their own copy of the loading cascade.

## Goals / Non-Goals

**Goals:**

- A nominated admin who has not accepted has no admin authority anywhere: every service, every permission derived from `team_admin`, present or future.
- The authorization state stays explicit in OpenFGA and readable in `my_relations`.
- The home page and the personal space never block on the charter.

**Non-Goals:**

- Enforcing the charter's content (backup administrator, monthly review, member vetting).
- Blocking the whole application, as the terms of use do.
- Fixing the GCU version enum, a separate defect.

## Decisions

### A pending relation instead of a permission gate

Nomination writes `pending_team_admin`, a relation that only feeds `team_member`. Accepting swaps it for `team_admin`.

Alternatives considered:
- **Python gate in the control-plane** (the first version of this change): denying the admin-only permissions and stripping them from the projection. Rejected: it cannot tell a permission granted by `team_admin` from the same permission granted by another role (`team_admin or team_editor`), and other services asking OpenFGA directly never see it.
- **`active_team_admin` intersection** (`team_admin and team_admin_charter_signatory from organization`): correct for every permission, but needs a charter object on the organization, one intersection on every check and seven rewritten definitions. The pending relation gets the same guarantee with one relation and no per-check cost; its price is the reconciliation below.

### Resolve the relation at every write of `team_admin`

`resolve_granted_team_relation(user_id, relation, deps)` returns `pending_team_admin` for `team_admin` while a version is set and the user has not accepted it. The five write sites call it. The request schemas refuse `pending_team_admin` (422), so only the server writes it. Revoking it maps to `can_administer_admins`, and `_remove_all_team_member_relations` deletes it with the other roles.

### Acceptance promotes, writing before deleting

`POST /team-admin-charter` inserts the acceptance if absent, then lists the caller's `pending_team_admin` teams (`lookup_resources` now accepts a relation) and, per team, writes `team_admin` before deleting `pending_team_admin`. A failure in between leaves both relations, which is an active admin; a repeat call finishes the move and also promotes a nomination that raced the first call.

### Reconcile at startup, only when the version changes

`team_admin_charter_state` stores the last applied version. At startup, under the metadata store's advisory lock, `reconcile_team_admin_charter_roles` compares it with the configuration and, when they differ, walks every registry team once: demote `team_admin` without an acceptance of the version, promote `pending_team_admin` with one, or promote everyone when the charter is off. The applied version is stored last. Like the organization edge repair it is fail-closed.

### Keep the admin invariants on active admins

The last-admin guard and the rescue check keep counting `team_admin` only. Counting pending admins would let a team whose only nominee never accepts escape the platform rescue.

### Frontend: a gate around the team pages

`TeamAdminCharterGate` wraps the `MainLayout` outlet. When `useSelectedTeam` returns a team whose `my_relations` holds `pending_team_admin`, it renders `TeamAdminCharterPage` (charter and Accept) instead of the page, but only while the team's `admins` (`team_admin` only) is empty: nobody has vouched for the user's other roles yet. When the team has an accepted admin, the gate renders the page under a notice leading to the Responsibilities section, so a pending admin who is also an editor keeps working and is never locked out for declining. The backend is unchanged either way: `pending_team_admin` never carries an admin permission. The home page and the personal space have no such relation. Accept invalidates `ControlPlaneTeam`, so `my_relations` refreshes and the gate opens. Team settings show the Responsibilities section to `team_admin`s and pending admins, with Accept for the latter; the admin role chip of a pending admin turns light orange with a clock icon ("Admin (pending)" on hover), and toggling it cancels the nomination.

### Markdown hook extracted from the GCU and GDPR pages

`useLegalMarkdown(name)` keeps the current candidate order and SPA-fallback rejection, and replaces both inline copies.

## Risks / Trade-offs

- [A version change on a large deployment reads every team at startup] → Only once per change, under a lock, and the applied version skips it afterwards.
- [Existing admins lose their rights at the startup that applies a new version] → Intended; they accept from their team page. The rollout order in the contract publishes the text first.
- [A nomination racing an acceptance leaves the user pending] → The team page shows the charter again and a repeat acceptance promotes it.
- [A user holding only `pending_team_admin` cannot drop it by revoking, it is their last role] → An admin removes the member instead, as for any last role.
- [During a rolling update that changes the version, a pod still on the previous configuration can grant `team_admin` to someone who has not accepted the new version, and reconciliation, which only runs when the version differs from the applied one, never corrects it] → Accepted: the window is the rollout itself. When it matters, change the version with a rollout that stops old pods first; reconciling at every startup was rejected for its cost of one ReBAC read per team per replica.
- [The two control-plane migrations must stay linear with `swift`] → Re-parent on the current head before merge, per CLAUDE.md.

## Migration Plan

1. Deploy with `app.team_admin_charter_version` unset: the tables are created, nothing else changes.
2. Publish a theme archive containing `team-admin-charter.md` and `team-admin-charter.fr.md`.
3. Set the version: the next startup makes admins who have not accepted pending, and they see the charter when they open their team.

Rollback: unset the version. The next startup promotes every pending admin; acceptances stay on record.
