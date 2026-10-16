## Context

Decisions taken with the developer on 2026-10-15: the tree lives only in OpenFGA;
admin, editor and analyst descend, member does not; a personal space has no parent
and inherits neither rights nor agents; a person must be a member of a team before
holding a project role; an agent's envelope is its execution space and ancestors,
narrowed by organization/team/project switches. Only fred-manager changes now.

## Decisions

- **Model.** `space` gains `parent: [space]` and `organization: [space]`.
  `effective_editor|admin|analyst = <role> or effective_<role> from parent`.
  Permissions keep their names and use the effective relations; `can_read` keeps
  direct `member`. `organization` appears in no permission. The DSL compiler
  accepts `[space]` and `<relation> from parent`, nothing more.
- **Direct parent content role.** Granting a space role, nominating a space admin
  and importing a child role require the target's direct `member`, `editor` or
  `analyst` tuple on the parent. With `can_read` instead, revoking an ancestor's
  editor would leave a descendant role whose parent is unreadable, unnoticed by the
  local children-first check. The direct rule keeps revocation local and exact.
- **SQL.** Migration 0006 drops `parent_id` and `path`, the root/parent check and the
  sibling uniqueness, rewrites the space immutability trigger for `kind` and
  `personal_owner`, and adds a unique organization-name index. Sibling names,
  kind placement and one personal space per person and organization are checked
  in code under the organization advisory lock, after reading children from OpenFGA.
- **Placement stays immutable.** Manager writes `parent`/`organization` once, in the
  same atomic Write as the creator's grants, and never deletes them. Child lookups
  ignore ids without a committed SQL row, as rolled-back creations leave tuples.
- **Organization lock.** The lock key needs the space's organization: 0 Reads for an
  organization, 1 for a team or personal space, 2 for a project, read before locking.
  Links are immutable, so reading them outside the lock is safe.
- **`/me/spaces`.** Read direct roles, then walk down from spaces where the caller
  holds a descending role (children Reads per organization and team), and read each
  directly granted space's parent. No `ListObjects`: its server limit truncates
  silently. Effective roles are computed from the tree in Rust only for display;
  every decision remains a Check.
- **Scope.** One `Check(can_read)`, then up to two parent Reads, then one SQL kind
  lookup. `levels` removes kinds; omitted means all. Personal: itself.
- **Team registry** keeps its response; each team's organization costs one Read,
  issued concurrently, at most 100 per page.
- **Deleted cutover.** `migrate-authorization` copied legacy tuples into a guarded
  store. Legacy stores have no `parent` tuples and SQL no longer holds them, so the
  copy cannot be correct. Startup binds an existing publication or initializes an
  empty installation; anything else requires the local reset.

## Costs

Counts per successful call, in OpenFGA requests. `L` = link Reads placing a space
(0 organization, 1 team or personal, 2 project). `R_d` = one Read of a user's direct
roles on one space, `R_c` = one children Read. Full inventory: arc42 chapter 9.

| Operation | Before | After |
| --- | --- | --- |
| Content check, authorize document/space | `1 C` | `1 C` (server traverses ≤ 2 parents) |
| Authorize scope | `1 C` | `1 C + L` |
| Grant child role | `1 R_g + 2 C + W(3)` | `L + 1 R_g + 1 C + 1 R_d + W(3)` |
| Revoke space role | `1 R_g + 1 C + P_u + W(2+d)` | `L + 1 R_g + 1 C + P_u + 1 R_c (+1 for an organization) + W(2+d)` |
| Create team (local) | `2 R_g + 2 C + W(5)` | `L_p + 2 R_g + 1 C + 1 R_d + 1 R_c + W(6)` |
| Create personal space | `1 R_g + 1 C + W(4)` | `1 R_g + 1 C + 1 Read + W(5)` |
| `GET /me/spaces` | `P_u` | `P_u + D + O_d + T_d` Reads |
| Team registry page | `1 C` | `1 C + ≤ 100 Read`, concurrent |
| ZIP import | `... + 3H` Checks | `3H + 2E` Reads instead; `+C` link tuple operations |

`D` = directly granted teams, projects and personal spaces; `O_d`, `T_d` =
organizations and teams reached by a descending role; `E` = existing parents whose
children resolve names; `C` = new teams and projects. Wire counts are asserted by
integration tests on fixed fixtures; they are not latency or throughput measurements.

## Risks / Trade-offs

- More OpenFGA Reads on navigation and structure operations, fewer SQL joins.
  Placement is immutable, so an in-process link cache is possible later; it is not
  added without measurement.
- A project cannot be hidden from its team's editors, admins or analysts.
- Data loss on upgrade of an existing manager installation: accepted, POC only.

## Open questions

- Whether both agent configuration and conversation switch the scope levels
  (manager accepts `levels`; the callers are out of scope): to confirm with Maxime.
