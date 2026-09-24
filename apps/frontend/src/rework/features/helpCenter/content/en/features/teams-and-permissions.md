---
title: Teams and permissions
order: 50
description: Who may do what in a team, how you get in, and who creates teams.
icon: groups
---

# Teams and permissions

Every piece of content belongs to a team and is visible only to its members.
What you may do depends on your **role** in that team.

## The four team roles

They **stack**: one person can hold several, each granted separately.

| Role        | Can                                                                     | Cannot, without another role                      |
| ----------- | ----------------------------------------------------------------------- | ------------------------------------------------- |
| **Member**  | Use the agents, read the team's conversations and files, leave the team | Change anything shared                            |
| **Editor**  | Create and edit agents, prompts, resources and model routing            | Manage members or team settings                   |
| **Admin**   | Manage members and their roles, the team's settings and policy          | **Create or edit an agent, a prompt, a document** |
| **Analyst** | Create and run evaluation campaigns, manage evaluation corpora          | Touch the general corpus, members or settings     |

> **Admin and Editor are two distinct permissions, not two rungs.** This point
> is frequently misunderstood: an Admin governs the team and holds no rights
> over its agents or documents until they are also an Editor. Holding both means
> holding two permissions, not occupying a higher level.

**Member** is the baseline: automatic as soon as you hold any role above it. And
a team always keeps **at least one Admin** — removing the last one is refused.

## Getting into a team

The **marketplace** lists the teams visible in your organization. A **public**
team appears there and is joined in one click if it is open; otherwise a team
Admin has to add you. A **private** team does not appear at all, and is never
joined alone: ask one of its members.

Note: a private team **cannot** be open to free joining. Members are added by
one of its existing members.

## Who creates teams

Creating a team is an administration action: it requires the platform role
**Platform admin** or **Team manager**. These roles are granted and are not part
of an ordinary user's rights. If you need a team, ask your administrator for
one.

An important detail: **whoever creates a team does not become its
administrator.** The initial administrators are named explicitly at creation
time. The separation is deliberate: creating a team belongs to platform
administration, running one belongs to the team.

## Team settings

The **Settings** page gathers what governs the team. Access to each section
depends on your role.

- **Members** — add, remove, change roles (**Admin**).
- **Settings** — the team's description, its marketplace visibility, how it is
  joined, and the **retention** period after which deleted conversations are
  permanently erased (**Admin**).
- **Model routing** — which model profile the team's agents use, by default and
  per operation. Left empty, the deployment's profile applies (**Editor**).
- **Evaluations** — campaigns measuring an agent's quality (**Analyst** or
  **Admin**). See the guide
  [Evaluate an agent](/help/en/guides/evaluate-agents).

## Platform roles

Five roles exist outside teams. They carry cross-cutting responsibilities and
**give no access to a team's data**:

| Role                       | Responsibility                                                                                 |
| -------------------------- | ---------------------------------------------------------------------------------------------- |
| **Platform admin**         | Everything below, plus deleting a team, managing users, and rescuing a team left with no Admin |
| **Team manager**           | Creating teams and seeing the list of all teams                                                |
| **Feature manager**        | Opening or closing the functions available to each team                                        |
| **Platform prompt editor** | Editing the shared instructions added to every agent                                           |
| **Platform observer**      | Reading platform-wide usage indicators                                                         |

> **A platform role never replaces a team role.** A platform admin with no role
> in your team can neither touch its agents nor read its conversations. And
> nobody, them included, reaches your personal space.

## How it is enforced

Every permission is a server-side record, checked **on every action** — not
merely hidden in the interface. Signing in proves who you are; it grants no role
by itself.

Missing a permission? See
[Common problems](/help/en/troubleshooting/common-problems).
