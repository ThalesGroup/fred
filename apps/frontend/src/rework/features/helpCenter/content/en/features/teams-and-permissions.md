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
| **Editor**  | Create and edit agents, prompts and resources                           | Manage members or team settings                   |
| **Admin**   | Manage members and their roles, the team's settings and policy          | **Create or edit an agent, a prompt, a document** |
| **Analyst** | Create and run evaluation campaigns, manage evaluation corpora          | Touch the general corpus, members or settings     |

> **Admin and Editor are two distinct permissions, not two rungs.** This point
> is frequently misunderstood: an Admin governs the team and holds no rights
> over its agents or documents until they are also an Editor. Holding both means
> holding two permissions, not occupying a higher level.

**Member** is the baseline: automatic as soon as you hold any role above it. And
a team always keeps **at least one Admin** — removing the last one is refused.

## Publishing agents

Every **Editor** can share the team's agents with the whole organization
through the agents marketplace. A team **Admin** may take an agent down from
the marketplace without being an Editor. How publishing works is explained on
the [Agents](/help/en/features/agents#the-agents-marketplace) page.

Publishing is **enabled for each team by the platform administrator**, who
also sets how many agents a team may publish. If the administrator turns it
off later, the team's published agents leave the marketplace.

## Getting into a team

The **marketplace** lists the teams visible in your organization. A **public**
team appears there with the way it is joined:

- **Open**: **Join** makes you a member in one click.
- **On request**: **Ask to join** sends a request to the team's Admins.
- **Invite only**: a team Admin has to add you or send you an invite link.

A **private** team does not appear at all, and is never joined alone: ask one
of its members.

Note: a private team **cannot** be open to free joining or to requests. You get
in when one of its Admins adds you or sends you an invite link.

A team's pages open to its members only: following a link to a team you do not
belong to (or no longer belong to) shows **You are not a member of this team**,
with **Ask to join** when the team takes requests.

### Asking to join a team

On the card of an **On request** team, **Ask to join** opens a short form. You
can add a message for the team's Admins (up to 280 characters, only they read
it), then **Send the request**. The card then shows **Request sent**: **Cancel
request** withdraws it while nobody has answered.

The bell tells you the answer. If an Admin accepts, you become a **Member** and
the team moves to **Your teams**. If they decline, the card shows **Request
declined** and when you can ask again: 24 hours later. A request nobody
answers is dropped after 30 days.

### Handling join requests (Admins)

To receive requests, a team Admin chooses **On request** in **Settings →
Settings → Joining mode**. Only a public team offers it.

Each request reaches the team's Admins in their notifications, with the
person's message: **Refuse**, on the left, declines; **Accept**, on the right,
makes them a **Member**. The first answer counts; the other Admins then see who answered. The same requests
appear at the top of **Settings → Members**, under **Join requests**, with
the same buttons. A request refused in the last 7 days stays listed there with
**Accept anyway**, in case of a mistake.

Leaving **On request** (or making the team private) declines every pending
request, and each person is told.

### Invite links

A team Admin can open **Settings → Members → Invite link** and turn on
**Enable invitation by link**. The team then has one link, shown in full with a
**Copy** button, to share however they like (chat, e-mail…). Opening it and
choosing **Join the team** makes you a **Member**; an Admin can then give you
other roles.

The link only works for people who already have access to the platform. It does
not give access to the platform itself: without that access, the link leads to
the page that explains how to request it.

Turning the switch off pauses the link: it stops working until the switch is
turned on again, with the same link. **Generate a new link** replaces it for
good: the previous link no longer works. Neither removes the people who already
joined.

## Who creates teams

Creating a team is an administration action: it requires the platform role
**Platform admin** or **Team manager**. These roles are granted and are not part
of an ordinary user's rights. If you need a team, ask your administrator for
one.

An important detail: **whoever creates a team does not become its
administrator.** The initial administrators are named explicitly at creation
time. The separation is deliberate: creating a team belongs to platform
administration, running one belongs to the team.

## The team description

Every team has a **description**: a few sentences stating what the team wants
to achieve with AI. It is required when the team is created (20 to 500
characters) and appears on the team's card in the marketplace, so that
everyone understands what the team is for.

A team **Admin** can rewrite it at any time in the team's **Settings**, but
cannot leave it empty.

A team created before descriptions became required shows "Description to be
completed by the team administrator." until one is written. Its Admins see a
reminder on the team's home page and in its settings; the reminder disappears
as soon as the description is saved.

## Team settings

The **Settings** page gathers what governs the team. Access to each section
depends on your role.

- **Members** — add, remove, change roles, share invite links, answer join
  requests (**Admin**).
- **Settings** — the team's description, its marketplace visibility, how it is
  joined, and the **retention** period after which deleted conversations are
  permanently erased (**Admin**).
- **Models** — among the language models the platform opens to the team: which
  ones members can use, the default one, and whether reasoning starts on for
  each (**Admin**; Editors and Analysts can view it). The default model cannot
  be disabled. Disabling a model first shows the agents that recommended it:
  they then follow the team's default model. Conversations that were using it
  go back to the agent's recommended model. A model the platform newly opens
  arrives enabled.

## Evaluation application

Open the registered evaluator through the team's **Apps** entry. It is a
standalone application, not a team settings section. It must be deployed,
registered and enabled for your team; its access permissions still apply.
If it is unavailable, contact your administrator. See
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
