## Context

See proposal. Base: `37af622d05b8f7ec340008725dd87cd0f362a666`.
All canonical direct roles are OpenFGA tuples. SQL records committed space identity;
parent and personal-organization links are immutable OpenFGA tuples. Existing
organization locks cannot prevent two different organizations attaching one subject.

## Goals / Non-Goals

Enforce one organization per person without a parallel SQL membership store, a new
permission matrix or visual redesign. Preserve member/editor/admin/analyst/owner
semantics, platform governance, consent and additive import. No new registration,
organization transfer command, personal entitlement, resource or conversation UI.

## Decisions

### Context and authority

Derive the distinct organization IDs of all committed direct-grant spaces using
full placement (including governance-only roles and legacy orphan child roles).
Ignore ghost tuples for absent SQL rows as existing creation recovery requires.
Zero means unattached, one means that organization, more than one returns conflict.
No claims mapping, email-domain guessing, new SQL grants or automatic enrollment.

`/me/spaces` resolves and validates this context before returning memberships.
Home defaults to its organization entry; that entry links to `/home` and team/project
links retain space selection. An invalid explicit space selection never falls back.
`/me` remains platform-role metadata, so platform administration is independently
usable. Missing membership yields an empty Home, not an invented organization.

Content reads, scope, writes and ingestion dispatch require the same context and
existing OpenFGA permission. Authorization probes return false for a foreign/missing
context and conflict for ambiguous data. Ordinary role management checks caller
context. Platform owner grant/revoke of organization owner, platform grants and
team registry keep their existing explicit platform authority boundary.

### Writes and concurrency

Reuse platform SQL lock and guard instead of adding subject guards with new
initialization/migration failure modes. Role grants/revocations acquire platform
then organization locks, capture both guards before checking authority or attachment,
and retain locks through commit. Operator organization creation also holds platform
lock/guard. A late abandoned write cannot survive a newer platform guard mutation.
Team/personal creation still uses its organization lock/guard: required parent/root
membership already binds its target, checked before publication. Context checks use
the held SQL connection to avoid pool starvation.

Grant checks reject foreign or ambiguous target attachment. Revoke does not require
target uniqueness, allowing authorized repair of legacy conflicts. No automatic
transfer: existing dependent-role revocation rules still apply.

Import rejects conflicting declarations across all subtrees, including not-yet-created
identities. Validate known subjects in read-only preflight, again before subtree
publication, and after capturing each subtree's platform/organization guards.
Use its transaction for rows so earlier new subtrees remain visible before commit.
Existing partial failure and additive replay semantics remain unchanged.

### Request budget and trade-offs

Let `Q(u) = P_u + sum L(s)` Reads for all distinct committed directly granted spaces
of subject u: `P_u` exhausts `Read(user=user:u, object=space:)`; `L` is 0 for an
organization, 1 for team/personal, 2 for a project. Placement Reads filter exact
`object=space:id`, relation `parent` or `organization`; all reads use higher
consistency and existing unset page_size. No ListObjects, ListUsers or Expand.

- Read/authorize content: prior Check + target placement L + Q(caller).
- Scope: existing L + Check + Q(caller).
- Memberships: existing paginated role/child/link Reads; at most one additional
  team-parent Read per orphan direct project whose parent was not already placed.
- Grants: prior budget + Q(target) + Q(caller) except owner grants have no caller
  context check; non-owner grants add platform guard Read and two Write operations.
- Revokes: prior budget + Q(caller) except owner; non-owner adds platform guard Read
  and two Write operations. Target enumeration is unchanged.
- Organization creation: previous guard initialization W(2), now two guard Reads,
  Q(first person), then W(7) (three initial roles and two guard replacements).
- Team/project creation: prior budget + Q(caller) + Q(admin). Personal creation and
  SQL content writes: prior budget + Q(caller).
- Import: existing budgets plus Q per known declared subject in preflight, Q per
  declared subject at reconciliation, and Q per subject in its guarded subtree.
  No added tuple mutations; baseline roles and guard batches remain unchanged.

Context costs depend on direct grants and pagination, not documents or all users.
All role grants/revocations now serialize at platform level, including unrelated
organizations. Lock duration includes guard, context, permission, directory and
mutation calls through SQL commit. Content writes retain organization-only locks.
Measure client RPCs with actual fixture sizes; no scalability claim is made from
correctness races at concurrency 2. Server-side FGA evaluation work is separate.

## Migration Plan

No SQL or FGA schema change. This is a behavioral compatibility change: diagnose
multiple attachments, deny business access, and have authorized administrators remove
unwanted roles bottom-up using existing revoke paths; never choose or delete data
automatically. Deploy all role writers together; mixed old writers do not enforce
the new invariant. Document recovery and regenerate the HTTP error contract.
