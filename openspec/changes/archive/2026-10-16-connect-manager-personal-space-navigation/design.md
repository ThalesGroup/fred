## Context and scope

Base: `1ccb47962`, tracking #3092. Unique server-resolved organization context is
implemented. The existing personal command creates a private team with member and
editor, under its organization lock, and rejects repeated creation. Python personal
identifiers and content hooks must not return to manager navigation. This lot uses
the existing personal row presentation and selected-space detail; Resources,
documents, agents and conversations remain outside the lot.

## Decisions

### Explicit creation eligibility

Add direct organization role `personal_space_creator` and OpenFGA permission
`can_create_personal_space`. Neither inherits nor grants content. Existing
organization administrators grant/revoke it through the existing role routes.
Granting it requires a direct content role on that organization. Import enforces
the same dependency using declared or existing roles before side effects and again
under reconciliation locks. Removing the last content role is blocked until this
same-scope entitlement is removed, as well as existing child dependencies.
The demo gives Priya this role explicitly. No default enrollment or configuration
switch grants it. Revocation prevents creation, never removes existing space access.

### Explicit open command

Retain `POST /me/personal-space` and its organization_id body, validated against
server context. After loading the organization, hold its SQL advisory transaction
lock, capture its FGA revision guard BEFORE authority reads, resolve caller context,
Check organization read, enumerate all organization links and load committed rows.
If the caller's personal row exists, Check its current read and return 200 with no
writes. Otherwise Check creation eligibility, insert the SQL row and guarded FGA
organization/member/editor tuples, commit, and return 201. Do not repair removed
roles, replace an inaccessible existing row, or treat dependency errors as success.
The lock spans dependent FGA/SQL calls. No directory lookup occurs. Concurrent
commands serialize and return the same committed UUID. Reuse captures a guard Read
for a single safe ordering but does not replace it or mutate SQL/FGA.

Expose `organization_id` on `/me/spaces` from already resolved placement, with no
additional FGA call. Personal path remains itself, without parent inheritance.

### Existing navigation and generated client

Restore the personal presentation of TeamSelectionListItem with an accessible
command mode, same styling/avatar/label. Show it when the organization lists the
creation role or the caller has an existing personal membership. Use generated RTK
mutation, disable automatic 401 replay, refresh memberships after success and select
the returned UUID. Every deliberate activation uses the command. Guard duplicate
clicks, pending and delayed completion after account changes; display normal errors
and permit a fresh action. A button-mode row handles keyboard activation without
pretending that modified/middle clicks can open a not-yet-created URL. Login,
render, hover, GET and import never create personal spaces. Filter the personal row
from the collective list. Preserve organization/team/project selection and layout.

### Additive model publication

Keep SQL authorization_store as the sole pinned model pointer. With the existing
`sync_schema_on_init` enabled, initialization holds the platform SQL lock, reads
the published model by ID and accepts either the exact current model or an exact
historical predecessor fixture. Only the predecessor permits publishing the new
additive model in the SAME store and transactionally updating model_id. Existing
tuples and spaces are preserved. No SQL migration or reset is needed. Concurrent
initializers serialize; failure before SQL commit leaves the prior pointer usable
for retry (an unused published model is harmless). Import/load remain read-only and
reject a predecessor until initialization upgrades it. Unknown models fail closed.
Deploy writers together; old binaries reject the new pinned model on rollback.

## Request budgets and cardinalities

Use chapter 9 notation: `Q(u)` is all pages of direct roles for caller u plus
placement reads needed to resolve their unique organization; `R_g` exact guard
Read; `P_o(org)` all organization-link Read pages with user=space:org,
relation=organization, object=space:. No page_size override; exhaust continuations.
`C` means higher-consistency Check, `W(n)` one Write of n tuple operations.

| Path | FGA client RPC budget | Mutations |
| --- | --- | --- |
| New personal space | Q(u) + R_g + P_o(org) + 2C + W(5) | link, member, editor, guard delete/insert |
| Existing personal space | Q(u) + R_g + P_o(org) + 2C | none |
| Membership organization_id | unchanged membership budget | none |
| Creator grant | existing organization grant + one direct_roles_on Read (paginated) | existing guarded role write |
| Creator revoke / last content revoke | existing revoke budget | existing guarded write or refusal |
| Import dependency | no extra Read when content is declared; otherwise direct_roles_on pages per creator declaration/check phase | one additional role tuple for Priya |

Context work grows with caller direct roles and their placements. Personal lookup
grows with personal spaces in the organization, not documents. These RPC counts do
not bound OpenFGA server evaluation or throughput. Tests measure multi-page fixtures,
zero-write reuse/refusal, and a two-open race; report sizes and concurrency.
Model upgrade adds one pinned-model GET, one model POST and one SQL pointer update
under platform lock; current-model startup performs only the GET after binding read.

## Verification and migration

Exercise eligibility grant/import/revoke dependencies, private isolation, current
read rechecks, repeated and concurrent commands, failure paths, API status/schema,
generated consumers, UI keyboard/pending/account changes, real OIDC browser with
Priya and no Python/runtime requests. Preserve and cite I4/I6/I20/I23 tests.
Verify exact predecessor compatibility, read-only refusal, initialization race and
failed pointer update. Run required manager, frontend, browser, root and arc42
checks, independent review, documentation pass and archive before local commit.
Migration note explains opt-in model publication, coordinated writers, old-binary
rollback refusal, explicit eligibility and the 409-to-200 reuse contract change.
