# RFC: Organizations and projects

**Status:** model agreed (2026-10-02); release 1 scoped in §4, its OpenSpec changes not yet written
**Author:** Dimitri Tombroff
**Date:** 2026-10-02
**Related:** issue #2921; `docs/swift/platform/REBAC.md`

---

## 1. Problem

Fred knows two levels: the platform and its teams. Two common needs fit neither.

- **Multi-tenancy.** Several organizations share one instance with real isolation
  between them. Today `organization:fred` is a hard-coded singleton.
- **Sub-teams.** Inside a team, a subset of members wants to work among
  themselves. Today the only answer is a new team, which loses what the parent
  team shares.

## 2. Model

A strict tree, each node with exactly one parent:

    platform → organization → team → project

No structural fact is hard-coded or derived from an identifier convention:
every node, its kind and its parent are explicit data. The platform is its own
ReBAC type (`platform`), carrying platform roles and catalog anchors;
`organization` is a tenant only.

A node never changes parent: a project stays in its team, a team in its
organization. Moving one would silently change who reads what.

| Object               | platform | organization | team | project |
| -------------------- | :------: | :----------: | :--: | :-----: |
| Prompts              |    ✓     |      ✓       |  ✓   |    ✓    |
| Resources (KB docs)  |    ✓     |      ✓       |  ✓   |    ✓    |
| Agents               |          |      ✓       |  ✓   |    ✓    |

**Membership**

- M1. A person belongs to exactly one organization.
- M2. A project member is a member of the project's team. A team member is not
  implicitly a project member.

**Isolation**

- I1. Read access flows down, never up or sideways: an object at one level is
  readable from every level below it. A project sees nothing of a sibling
  project; an organization sees nothing of another.
- I2. Write access requires a role at the object's own level.
- I3. Nothing flows up: content of a level never reaches a level above it,
  whether through a conversation, a write, or agent memory.
- I4. Platform and organization roles govern (membership, structure) and grant
  no access to team or project content — the rule `platform_admin` already
  follows today.
- I5. `team_admin`, `team_editor` and `team_analyst` read the content of every
  project of their team. `team_member` does not.

**Agents**

- A1. An agent is available at its own level and below, like a prompt.
- A2. An agent's reach is set by where the conversation runs, not where the
  agent is defined: it reads that level and above, and everything it produces
  stays at that level. A team agent used in a project reads the project; used
  in the team, it never does. An organization agent's author holds no right on
  team content (I4): only I3 keeps that content from reaching them.
- A3. An agent's configuration (e.g. a pinned folder) references only objects
  at its own level or above. The pin narrows A2, never widens it. An agent
  pinned to a project folder therefore lives in that project; copying a team
  agent into a project is a plain UI copy, with no link to the original.

**Roles**

- R1. Existing team roles are unchanged; platform roles too, except R5.
- R2. Two organization roles: `org_admin` governs (organization members, team
  creation, naming each team's first `team_admin`) with no access to team
  content; `org_editor` writes organization-level prompts and resources.
  `platform_admin` creates organizations and names their first `org_admin`.
- R3. A project carries the four team roles, with the same meaning, scoped to
  the project.
- R4. `team_admin` and `team_editor` create projects. The creator names the
  project's initial `project_admin`(s), who must be team members; the creator
  gets no project role by creating it. Same shape as team creation today.
- R5. The platform role `team_manager` is deleted: `org_admin` covers it.

**Personal space**

- S1. A personal space is a one-member team, placed under its owner's
  organization. It follows the general rules: reads organization and platform
  content, sees no other team, holds no project.
- S2. A team's kind (`shared` or `personal`) is explicit data, answered by a
  single authority. No other code infers it from an identifier.

## 3. Migration

- MG1. An existing installation upgrades into one organization. Every team,
  personal space, membership, role, agent, resource and conversation keeps its
  id and works unchanged. No project exists after the upgrade.
- MG2. Platform roles and catalog anchors move to the `platform` object with
  the same holders. `team_manager` holders become `org_admin` of that
  organization.
- MG3. The upgrade is repeatable and never reattaches a team that is already
  explicitly attached to an organization.
- MG4. Existing APIs keep their behavior for an installation with a single
  organization.
- MG5. The operator supplies that organization's id and name in configuration,
  with no default; the upgrade refuses to run without them.

- MG6. No deployment variant in code or configuration. A single-user laptop is
  an installation where no shared team exists: data, not a mode.

## 4. Delivery

**Release 1 — the model under existing behavior, no user-facing change.**
Organizations stay invisible to users; only `platform_admin` and `org_admin`
see them, on the admin pages.

1. Refactor, behavior unchanged: the `platform` type takes over platform roles
   and anchors; team kind becomes explicit (S2).
2. Explicit organization (MG1–MG5); `org_admin` replaces
   `team_manager` (R5).

**Later releases, each with its UI:** projects; organization-level content,
`org_editor` and organization agents; creating further organizations.

## 5. Impact on existing contracts

- **ReBAC schema** (`fred_core/security/rebac/schema.fga`). `organization`
  stops being a singleton; `team#organization` already exists. New `platform`
  type takes over platform roles and every platform-level `… from organization`
  anchor (capability, app, knowledge-base definition). New `project`
  type with parent `team` and the four roles. `organization` and `project`
  join `[user, team]` as owners of `tag` (libraries, folders) and `agent`;
  documents and resources inherit through `tag#parent` unchanged.
- **Control-plane.** `team_metadata` gains its organization; new organization
  and project registries; team creation moves to `org_admin`.
- **Conversation context.** A conversation carries its level (team or
  project); agent reach (A2) and every write resolve from it.
