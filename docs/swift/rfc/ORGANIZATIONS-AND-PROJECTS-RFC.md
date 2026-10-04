# RFC: Future organization administration

**Status:** future multi-organization target, not shipped; project delivery is
specified separately below. Organization onboarding remains open.
**Author:** Dimitri Tombroff
**Related:** [#2921](https://github.com/ThalesGroup/fred/issues/2921)

## Scope and authoritative references

[Team/project authorization OpenSpec](../../../openspec/changes/simplify-corpus-authorization/proposal.md)
is the proposed authority for projects, local roles, corpus ownership, agent reach
and conversation context in the current single organization. This RFC no longer
maintains parallel project rules. Its former transversal editor/analyst access and
folder-parent permission model are superseded by that proposal. The governance/content-access decision is recorded in its
[canonical design](../../../openspec/changes/simplify-corpus-authorization/design.md#governance-decision-and-delivery).

[REBAC.md](../platform/REBAC.md) describes the shipped authorization model.
Neither this RFC nor the OpenSpec changes runtime behavior by being merged.

## Remaining future target

Several organizations may eventually share an instance with tenant isolation,
in place of today's singleton `organization:fred`. Extend the explicit ownership
tree above teams; do not infer organization identity from naming conventions.
Each person belongs to exactly one organization; a team never changes organization.
Organizations are visible to platform/organization administrators, not ordinary
users. A deployment with one user is data, not a separate operating mode.

The future `platform` ReBAC type holds platform roles and catalog anchors;
`organization` denotes a tenant only. Platform and organization governance grant
no implicit access to team or project content. Organization-level resources and
prompts are common to that organization's members; organization-defined agents
can serve its descendant spaces under the contextual-access contract linked above.
That contract also governs inherited read versus local write authority and keeps
conversation outputs and memory in their execution space.
Existing platform-common resources/prompts remain above the tenant boundary;
there are no platform-owned agents in this target.

Two proposed organization roles:

- `org_admin` manages organization membership, team creation and nomination of
  initial team administrators, without implicit access to their content.
- `org_editor` manages organization-common prompts and resources.

A `platform_admin` creates organizations and nominates their first `org_admin`.
The future organization administration replaces `team_manager`; that role remains
unchanged in the current single-organization project delivery.
A personal space remains a one-member team under its owner's organization;
its kind is explicit data and it holds no project.

## Remaining design and delivery work

- Decide how an account joins its organization: invitation or an external request
  reached from a landing page outside any organization.
- Specify organization administration and membership lifecycle, tenant isolation
  validation, and the separation of platform anchors from the current singleton.
- Scope existing-data translation and rollout independently, including an explicit
  assignment of existing teams/users and backup/restore behavior.

Explicit ancestry in the project change prepares this extension; it does not
establish multi-tenant safety or deliver the administration above.
