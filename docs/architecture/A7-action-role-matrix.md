# Reference: action and role matrix

Companion to the [Security chapter](03-security.md).

This reference describes the implemented **control-plane Rust** contract on the
organization/team/project model. It covers every registered HTTP operation,
operator entry points and every permission accepted by the authorization API.
It does not assert that the corresponding Python surfaces use the same rules.
The [Python comparison](#differences-from-the-python-contract) names the verified
differences; those differences are not a claim of team approval.

## How to read the matrices

Each role column describes what that role grants **by itself**. Roles are cumulative.
`Yes` still requires the additional conditions in the row and below the table.
`No` means that the role does not grant this action; another held role can grant it.
The role is evaluated on the target space, except where the row explicitly names
the parent or organization. Platform roles apply to `platform:root` only.

All non-public business HTTP operations require an authenticated caller and current
personal CGU acceptance when configured. Space business actions also require the
caller's unique organization to match the target. Roles do not bypass admission.
`GET /me/spaces` can list governance-only spaces: seeing an entry is not permission
to read its Resources. Organization context is derived from committed spaces and
OpenFGA direct grants, never selected by a request URL or a token group.

The HTTP prefix below is `/control-plane/v1`. Route registration is generated in
[manager contracts](A2-manager-contracts.md#control-plane-http-surface).

## Role scope and inheritance

| Role | Legal grant location | Applies to | Content authority by itself |
| --- | --- | --- | --- |
| `member` | Organization, team, project; personal at creation | That space only | Read |
| `editor` | Organization, team, project; personal at creation | That space and all non-personal descendants | Read and write |
| `admin` | Organization, team, project | That space and all non-personal descendants | None |
| `analyst` | Organization, team, project | That space and all non-personal descendants | Read |
| `organization_owner` | Organization only | That organization only | None |
| `personal_space_creator` | Organization only | Eligibility for that person's personal space in that organization | None |
| `platform_owner` | Platform | Platform governance | None directly |
| `platform_observer` | Platform | Platform observation permission | None |
| `feature_manager` | Platform | Team registry and capability-management permission | None |
| `prompt_editor` | Platform | Platform-prompt permission | None |

An editor/admin/analyst on an organization applies to every team and project below
it. The same role on a team applies to its projects, not to its parent or siblings.
A member never descends. A personal space has **no parent link**: its organization
link identifies governance and supplies no inherited permission. Its SQL
`personal_owner` is an identity, not the FGA `organization_owner` role. Initial personal grants
are `member` and `editor`, not `admin` or `organization_owner`.

## Content actions

No platform role, `organization_owner` or `personal_space_creator` grants any row
in this table. Rights apply uniformly to the owning space: folders and documents
have no separate ACL, sharing grant or role inheritance tree.

| Action and HTTP entry | member | editor | admin | analyst | Extra condition / effect |
| --- | --- | --- | --- | --- | --- |
| Browse mixed directory - `GET /spaces/{id}/entries` | Yes, local | Yes | No | Yes | Same-space parent; bounded page, total, ancestors and current write decision |
| Read storage summary - `GET /spaces/{id}/storage` | Yes, local | Yes | No | Yes | Space statistics and shared quota usage; no other space's filenames |
| Preflight original names/quota - `POST /folders/{id}/documents/preflight` | No | Yes | No | No | Advisory result, no reservation |
| Create original - `POST /folders/{id}/documents` | No | Yes | No | No | One file, request key, quota and unique name; current admission/write rechecked before publication |
| Read/acknowledge upload receipts - `GET /spaces/{id}/document-uploads`, `GET /document-uploads/{id}`, `PUT /document-uploads/{id}/acknowledgment` | Yes, local | Yes | No | Yes | Initiating actor only; acknowledgment requires terminal state |
| Download original - `GET /documents/{id}/content` | Yes, local | Yes | No | Yes | Current owning-space authority; private attachment |
| Create a folder - `POST /folders` | No | Yes | No | No | Same-space parent, valid name, depth <= 15, unique sibling name |
| Rename a folder - `PATCH /folders/{id}` | No | Yes | No | No | Name changes; space, parent and path stay immutable |
| Delete a folder - `DELETE /folders/{id}` | No | Yes | No | No | Atomic subtree removal; any published document or pending upload refuses the whole subtree |
| Resolve search scope - `POST /authorize/scope` | Yes, local | Yes | No | Yes | Read on requested space; returns it and ancestors, never descendants; personal returns itself; optional levels only narrow |

The original Resources UI binds listing, navigation, creation, rename and subtree
deletion to manager. Its directory response supplies the current write decision;
each mutation rechecks it. Names are display metadata; paths use immutable UUIDs.
Original upload and individual download use manager; processing controls preserve
their presentation with processing unavailable in this view.

## Space governance and personal-space actions

| Action | member | editor | admin | analyst | owner (organization) | personal_space_creator | Platform role granting this action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Create team - `POST /spaces` | No | No | Yes, on parent organization | No | No | No | None |
| Create project - `POST /spaces` | No | No | Yes, on parent non-personal team | No | No | No | None |
| Grant/revoke `member`, `editor`, `analyst` - `PUT/DELETE /spaces/{id}/roles/{role}/{user}` | No | No | Yes, on target | No | No | No | None |
| Grant/revoke team/project `admin` - same role routes | No | No | Yes, on target | No | No | No | None |
| Grant/revoke organization `admin` - same role routes | No | No | Yes, on organization | No | Yes | No | None |
| Read organization/team supervision - `GET /organizations/{organization_id}/supervision` and `/teams/{team_id}` suffix | No | No | No | No | Yes, on target organization | No | None |
| Grant/revoke organization `personal_space_creator` - same role routes | No | No | Yes, on organization | No | No | No | None |
| Grant/revoke `organization_owner` - same role routes | No | No | No | No | No | No | `platform_owner` |
| First creation of own personal space - `POST /me/personal-space` | No alone | No alone | No | No alone | No | Yes, plus organization read | None |
| Reuse existing own personal space - `POST /me/personal-space` | Conditional | Conditional | No alone | Conditional | No | No alone | None |
| Add roles in a personal space - `PUT /spaces/{id}/roles/{role}/{user}` | No | No | No | No | No | No | None |
| Remove a personal-space role - `DELETE /spaces/{id}/roles/{role}/{user}` | No | No | Yes, on its organization | No | No | No | None |

Conditions are part of these rights:

- Supervision requires `can_own_organization` after admission, unique matching
  organization context and lifecycle checks. It grants technical aggregates only,
  not content, downloads or named-user listings. Team detail accepts only a
  collective team in that organization. All OpenFGA pages must succeed; dependency
  failure returns 503 `dependency_unavailable`, never a partial result. Exact
  scopes, refusals and counters are in [the supervision contract](A8-organizations.md#organization-supervision).

- For team/project creation, the nominated initial admin holds a direct content
  role (`member`, `editor` or `analyst`) on the parent. The creator gains no implicit
  content role. A project cannot be created under a personal space.
- Every direct role on a team/project requires a direct content role on its parent;
  inherited permission alone is insufficient. The recipient cannot be attached to
  another organization. Owner-only/admin-only attachment is still an attachment.
- Personal-space eligibility is organization-only and also requires a direct
  organization content role. First creation additionally checks effective
  organization read. Existing-space reuse requires both organization read and
  personal read; eligibility need not still be held. Reuse restores no removed role.
- A non-personal space keeps at least one admin; an organization keeps at least one
  owner. Removing a person's last direct content role is refused while dependent
  child roles or personal-space eligibility remain. No replacement member grant is
  synthesized. Personal roles are removed from their organization, not self-managed.
- Every grant names a subject usable as an OpenFGA user and known to the configured
  user directory, checked after authorization; otherwise 422 (I27).
- Owner changes are platform operations and do not require the actor to belong to
  the target organization. A new owner must exist in the configured Keycloak realm;
  removal can clean up a deleted identity. The other space-role routes require the
  actor's matching organization context.
- Mutation checks occur after the organization lock and before the OpenFGA fence
  and write. A previous UI permission response does not reserve a future right.

The ordinary role routes do not forbid naming oneself as the recipient. An admin
can grant themselves `editor` where the target-role and parent-membership conditions
above are satisfied; an organization owner can grant themselves organization admin.
Thus the separation between management and content read is a distinction between
current permissions, not a prohibition on self-assignment through governance.
Personal-space role additions remain forbidden, including for organization admins.

## Platform operations

Space roles grant none of these operations.

| Action and HTTP entry | platform_owner | platform_observer | feature_manager | prompt_editor | Extra condition |
| --- | --- | --- | --- | --- | --- |
| List direct platform-role grants - `GET /users/platform-roles` | Yes | No | No | No | Real authentication required; lists stored direct grants, not computed implications |
| Grant platform role - `PUT /users/{user}/platform-roles/{role}` | Yes | No | No | No | Includes owner; real authentication, compatible Keycloak directory and existing target identity required |
| Revoke platform role - `DELETE /users/{user}/platform-roles/{role}` | Yes | No | No | No | Includes root's owner grant; preserve at least one owner; real authentication required |
| Grant/revoke organization owner - space role routes | Yes | No | No | No | Conditions above |
| Import identities, organizations, teams, projects and roles - `POST /import-export/import` | Yes | No | No | No | Real authentication, CGU, compatible directory, valid bundle and parent dependencies |
| Request project/team/organization deletion - `DELETE /spaces/{id}` | Yes | No | No | No | Real authentication and CGU; enabled lifecycle; no documents or pending uploads; complete subtree; no standalone personal deletion |
| Read deletion receipt - `GET /deletions/{operation_id}` | Yes | No | No | No | Real authentication and CGU; remains available after cleanup and when lifecycle is disabled |
| List global team registry - `GET /admin/teams` | Yes | No | Yes | No | Non-personal team metadata only; no content access |
| Read or write space content directly | No | No | No | No | Requires an independently held space content role |

**Provisioning authority is powerful.** Import can add space and platform grants
without the importing platform owner's local `can_manage`. Thus no automatic
content access does not mean an inability to grant content access. Import is
additive; its global authority is distinct from the ordinary space-role routes.

## Entry points with no role prerequisite

| Action and HTTP entry | Any of the roles above | No role | Additional gate |
| --- | --- | --- | --- |
| Frontend configuration - `GET /frontend/config` | Yes | Yes | Public; no bootstrap secret returned |
| Health - `GET /healthz` | Yes | Yes | Public |
| Own onboarding - `GET /me/onboarding` | Yes | Yes | Authenticated human identity; no CGU yet |
| Accept own CGU - `POST /gcu` | Yes | Yes | Authenticated human, current version; cannot act for another person |
| Claim initial platform ownership - `POST /bootstrap/platform-admin` | Yes | Yes | Real human authentication, CGU, deployment secret, unfinished bootstrap; failed reservation retry belongs to claimant |
| Own platform-role metadata - `GET /me` | Yes | Yes | Authenticated and CGU; returns own effective platform roles |
| Own spaces - `GET /me/spaces` | Yes | Yes | Authenticated and CGU; own direct/inherited roles; empty allowed; contradictory organization attachment, or a space role without its parent membership, returns 409 |
| Probe own platform permission - `POST /authorize/platform` | Yes | Yes | Authenticated and CGU; result may be false |
| Probe own space permission - `POST /authorize/space` | Yes | Yes | Authenticated and CGU; a missing, foreign or retired target, or a missing permission, gives false; contradictory context gives 409 |
| Probe own document permission - `POST /authorize/document` | Yes | Yes | Authenticated and CGU; a missing document, or the owning space's refusal, gives false; requested read/write/manage determines true/false |

Calling a probe is not performing the requested action. Probes never accept a
replacement user id. Missing targets give false; dependency failures are errors,
not positive authorization decisions.

## Permission answers beyond the content and governance actions

These rows describe the current authorization API's boolean answers. In particular,
an evaluation permission answer does not run an evaluation or read a conversation.

| Space permission queried | member | editor | admin | analyst | owner | personal_space_creator |
| --- | --- | --- | --- | --- | --- | --- |
| `run_evaluations` | No | No | Yes | Yes | No | No |
| `manage_evaluation_corpus` | No | No | Yes | Yes | No | No |
| `read_conversations_for_evaluation` | No | No | No | Yes | No | No |
| `own_organization` | No | No | No | No | Yes, organization | No |
| `create_personal_space` | No | No | No | No | No | Yes, organization |

| Platform permission queried | platform_owner | platform_observer | feature_manager | prompt_editor |
| --- | --- | --- | --- | --- |
| `list_all_teams` | Yes | No | Yes | No |
| `delete_team` | Yes | No | No | No |
| `delete_space` | Yes | No | No | No |
| `rescue_team_admin` | Yes | No | No | No |
| `edit_agent_class_path` | Yes | No | No | No |
| `observe_platform` | Yes | Yes | No | No |
| `administer_users` | Yes | No | No | No |
| `manage_platform` | Yes | No | No | No |
| `manage_capabilities` | Yes | No | Yes | No |
| `edit_platform_prompt` | Yes | No | No | Yes |

`read`, `write` and `manage` answers follow the corresponding space matrices above.
`/authorize/document` also accepts `manage`: an effective admin can receive true
without receiving read/write. The folder mutation handlers require write,
not manage. Platform owner includes the other platform permissions through the
OpenFGA model; that implication is not a stored grant of every role.

## Operator commands

| Entry point | Authority and effect |
| --- | --- |
| `import-provisioning ... --token-file ...` | Authenticated bearer, CGU, platform owner and compatible directory; same provisioning engine as HTTP. |
| `serve` | Verifies the SQL schema, then supervises HTTP and background tasks, including Temporal connections. |
| `migrate` | Applies embedded SQLx migrations using database credentials only. |
| `generate-openapi` | Offline schema generation, no service credentials needed. |
| `--help` / `-h` | Local command help. |

Document storage and folder operations make no Temporal call. Lifecycle background tasks inside `control-plane serve` own their Temporal connection.

## Evidence and maintenance

The matrices are checked against [the model](../../apps/control-plane/openfga/model.fga),
[typed permissions](../../apps/control-plane/src/roles.rs),
[HTTP handlers](../../apps/control-plane/src/api.rs),
[original storage](../../apps/control-plane/src/documents/http.rs),
[space governance](../../apps/control-plane/src/spaces.rs),
[organization supervision](../../apps/control-plane/src/supervision/mod.rs),
[platform governance](../../apps/control-plane/src/platform.rs), and
[operator commands](../../apps/control-plane/src/main.rs).
Role truth tables, ancestor behavior, private isolation and revocation are exercised
by [manager integration tests](../../apps/control-plane/tests/integration.rs) and
[resource contract tests](../../apps/control-plane/tests/support/resource_browsing.rs).

Changes to an authority boundary update this matrix and its regression tests.
