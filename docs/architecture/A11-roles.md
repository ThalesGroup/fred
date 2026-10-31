# Reference: roles and responsibility boundaries

This is the role reference for architecture and security reviews (SSI). It separates
**agreed responsibilities** from **current Control Plane permissions**. A responsibility
is not proof of an implemented control. Current permissions below come from source
inspection; this documentation change includes no live authorization tests.

Read each row as the authority of **that role alone**. Current roles are cumulative;
the ability to grant another role is listed separately. Authentication, admission,
organization matching and resource-specific checks still apply. For individual
actions, endpoints and exact permission answers, use [A7](A7-action-role-matrix.md).

## Reference roles

**Admin** denotes a limited institutional mandate. **Owner** denotes business
management. Owner, analyst, editor and member have the same meaning in an
organization, team or project; scope changes where they apply, not their purpose.
There is no team-admin or project-admin role.

| Role | Scope of grant | Agreed responsibility | Current permissions and limits, role alone | Current inheritance |
| --- | --- | --- | --- | --- |
| **Platform admin** (`platform_admin`) | Platform | Bootstrap platform administration and create organizations, selecting their admin and initial owner; no business role or right to know their contents. | Organization creation, platform-role and organization-admin assignment, provisioning and space retirement. Does not imply observer, feature-manager or prompt-editor roles. No direct space-content access. Platform-role assignment and standalone team/project retirement remain broader than organization-only governance. | Platform only; no space role or content inheritance. |
| **Organization admin** (`organization_admin`) | Organization only | Execute express steering committee decisions within a limited mandate, such as team creation and organization access-allowlist changes. No model choices, business activity or right to inspect business data and agents. | Assign/revoke organization owners and read organization supervision aggregates. No content read/write, model management or evaluation permissions. Team creation and access-allowlist changes are **not granted**; see the comparison below. | Organization only; does not descend. |
| **Owner** (`owner`) | Organization, team or project | Manage the business workspace and its community. At organization level, manage model choices and shared resources with analysts, editors and members. | Space management and role assignment; creation of teams/projects under an authorized parent. Organization owner manages model inventory/policy and template governance. Evaluation run/corpus permissions; no content read/write or evaluation-conversation read. | Granted space and all team/project descendants. |
| **Analyst** (`analyst`) | Organization, team or project | Consult content and evaluate the space's agents and their use. | Content read; evaluation run, corpus management and evaluation-conversation-read permissions. No ordinary content write, space management or organization model management. | Granted space and all team/project descendants. |
| **Editor** (`editor`) | Organization, team or project; personal space at creation | Contribute to the space's content. | Content read/write, including agent-instance authoring where supported and template-authorized. No role management, evaluation permissions or organization model management. | Granted space and all team/project descendants; personal space stays isolated. |
| **Member** (`member`) | Organization, team or project; personal space at creation | Consult the space's content and use its authorized assistants. | Content read and assistant access subject to template-use and execution checks. No content write, role management, evaluation permissions or organization model management. | Granted space only. |

Content read also lets an editor or analyst use an authorized assistant under the
same checks. Managing organization model choices does not authorize reading
another person's conversation. The evaluation permissions above are the model's
`run_evaluations`, `manage_evaluation_corpus` and, for analysts only,
`read_conversations_for_evaluation`: a positive permission answer does not prove
that an evaluation or conversation-reading journey is wired and validated.

Any business role (`owner`, `member`, `editor` or `analyst`) on an active
organization, team or project makes the person eligible for their personal space
in that organization. Technical
`platform_admin` and `organization_admin` roles alone do not. The roles can
accumulate: an admin who also holds a business role remains eligible. Personal content
still belongs only to its own member/editor, never to other business owners.

## Complementary roles in the current implementation

These roles complete the current inventory. Their implementation is recorded here
without implying that their long-term place in the agreed governance model has
been settled. The responsibility column describes their current purpose.

| Role | Scope of grant | Current purpose | Current permissions and limits, role alone | Current inheritance |
| --- | --- | --- | --- | --- |
| **Platform observer** (`platform_observer`) | Platform | Hold platform observation authority. | `observe_platform`; no space membership or content access. A permission declaration does not establish an observation UI or unrestricted access to logs. | Platform only; also implied by platform admin. |
| **Feature manager** (`feature_manager`) | Platform | Hold capability-management and global team-registry authority. | `manage_capabilities` and `list_all_teams`; registry access exposes team metadata, not content. No organization model-management permission. | Platform only; also implied by platform admin. |
| **Prompt editor** (`prompt_editor`) | Platform | Hold platform-prompt editing authority. | `edit_platform_prompt`; no right to edit a space's resources or read its content. This permission alone does not establish a wired prompt-editing journey. | Platform only; also implied by platform admin. |

Inheritance follows the organization -> team -> project hierarchy, never upwards
or to siblings. A personal space has **no parent link** and inherits no role from
its organization. Its initial grants are `member` and `editor`, not owner or
organization admin. Folders and documents use their owning space's permissions;
they introduce no additional role scope.

## Attribution, accumulation and removal

This table describes **current ordinary role-management authority**, not the
agreed institutional mandate. Effective owner includes an inherited owner role.

| Role being assigned or removed | Current authority | Conditions and limits |
| --- | --- | --- |
| Platform admin, observer, feature manager, prompt editor | Platform admin | First admin established by bootstrap; subsequent grants through platform-role management. The last platform admin cannot be removed. |
| Organization admin | Platform admin | Appointed at organization creation or through role management; the last organization admin cannot be removed. The actor need not belong to that organization. |
| Organization owner | Organization admin or organization owner | Initial owner selected by platform admin at organization creation. The organization must retain an owner. |
| Team/project owner | Effective owner of the target space | Initial owner selected by the creator, who currently needs owner on the parent. Every non-personal space retains a direct owner. |
| Member, editor, analyst in a collective space | Effective owner of the target space | Child-space grants require direct parent content membership. |
| Personal-space member/editor | System at creation; organization owner for removal | No role additions afterwards, including by the person themselves or an organization owner. Reopening restores no removed role. |

All space-role recipients must belong to at most one organization, including
admin-only or owner-only attachments. Every direct team/project role requires a
direct parent content role (`member`, `editor` or `analyst`); inherited access
alone is insufficient. Removing the last direct content role is refused while
dependent child roles or personal content roles remain. No replacement
membership is synthesized. Grant recipients must exist in the configured user
directory; [A6](A6-security.md#roles-permissions-and-rebac) details identity checks.

**Role accumulation is not separation of duties.** Current organization creation
accepts the same identity as admin and owner. Ordinary role routes do not forbid
self-assignment: an organization admin can grant themselves owner, and an owner
can grant themselves editor under the normal scope and parent-membership rules.
Revoking one role leaves other direct or inherited authority effective; inherited
permissions are not separate grants that can be revoked on a child.

**Provisioning is a separate, broader path.** A platform admin can import business
and platform grants without local space-management authority. Lack of direct
content read therefore does not mean inability to grant content access. See the
[provisioning contract](A8-organizations.md#provisioning-people-and-spaces) and
[current platform operations](A7-action-role-matrix.md#platform-operations).

## Responsibility boundaries and current enforcement

The following comparison is the single record of the admin/owner discrepancies
identified for SSI review. It distinguishes missing controls, broader powers and
organizational decisions; it does not change the permission model.

| Boundary | Current implementation | Assessment against the agreed responsibilities |
| --- | --- | --- |
| Model choices | Model inventory, policy changes and source refresh require organization `Manage`, supplied by `owner`, not `organization_admin`. | Aligned: Alice manages Acme's models; Oscar's admin role alone does not. |
| Team creation | `create_space` requires `Manage` on the parent organization. An organization admin alone cannot create a team. | Gap: this institutional action is assigned to the admin executing the committee's decision. Project creation remains governed by the current team-owner permission; no new project-admin role is implied. |
| Organization access allowlist | Membership derives from committed roles; `context` and `may_attach` enforce a single organization. The inspected contracts have no admin-operated allowlist or cross-organization guest-policy operation. | Gap: the agreed access-allowlist action is not available. Cross-organization admission remains refused. |
| Steering committee mandate | The inspected mutation paths check the caller's roles and lifecycle constraints; they do not require a committee decision or approval reference. | Process boundary: the mandate is an organizational rule. No application approval workflow is implemented or implied by this vocabulary. |
| Platform-admin remit | Platform admin implies all platform permissions. Role management, provisioning of business and platform grants, global team metadata and space retirement exceed bootstrap and organization creation. | Gap: the implementation is broader than the agreed limited remit. No direct content read does not mean no ability to grant it. |
| Admin/business separation | Organization creation permits the same identity as admin and owner. An organization admin can grant themselves owner, then an owner can grant themselves editor under the normal conditions. | The code enforces no content access from admin alone, but no exclusive separation of duties. The intended limits on cumulative roles and self-assignment require explicit resolution. |
| Organization supervision | `can_administer_organization` exposes document/processing/role counts, team names and scoped aggregates, without document content or named users. | Mandate question: this reveals activity metadata. Its compatibility with the admin's lack of business right-to-know must be decided explicitly; it is not equivalent to content access. |

## Responsibilities that are not additional roles

- **Steering committee:** decides institutional changes; the organization admin
  executes its express decisions. The committee is not an permission role.
- **Infrastructure operator:** deploys services and manages connections, secrets
  and infrastructure access. Operational access needs its own controls; it confers
  no Fred business role. Dana fills this responsibility in the model journey.
- **Bootstrap:** the procedure establishing the first platform admin, not another
  role or a permanent super-admin identity.
- **Personal-space owner:** the identity associated with a personal space in SQL,
  not `organization_admin`; access requires a current business role on an active collective space and
  the space's explicit content roles.
- **Service identity:** authenticates a workload. It does not replace the person's
  authority when acting on their behalf; see [service authentication](A6-security.md).

## Evidence and terminology

Role definitions and implication rules are recorded in the
[typed permission evaluator](../../apps/control-plane/src/authorization.rs),
[space roles](../../apps/control-plane/src/domain.rs) and
[typed permissions](../../apps/control-plane/src/roles.rs).
The comparison above is grounded in [`model_catalog/http.rs`](../../apps/control-plane/src/model_catalog/http.rs)
(`authorize`, `authorized_transaction`);
[`spaces.rs`](../../apps/control-plane/src/spaces.rs) (`create_space`, `context`,
`may_attach`, `may_change`, `grant`, `create_managed_organization`);
[`typed permission evaluator`](../../apps/control-plane/src/authorization.rs);
[`platform.rs`](../../apps/control-plane/src/platform.rs);
[`provisioning.rs`](../../apps/control-plane/src/provisioning.rs);
[`lifecycle/store.rs`](../../apps/control-plane/src/lifecycle/store.rs) (`permitted`);
[`supervision/mod.rs`](../../apps/control-plane/src/supervision/mod.rs) (`authorize`);
and the [organization creation contract](A5-user-journeys.md#a-platform-admin-creates-an-organization).

The canonical role identifiers are `platform_admin`, `organization_admin` and
`owner`. English labels use **Admin** for technical governance and **Owner** for
business responsibility; French labels use **Admin** and **Responsable** respectively.
`/bootstrap/platform-admin` establishes the first platform admin. Personal-space
and conversation ownership are identities, not either governance role.
