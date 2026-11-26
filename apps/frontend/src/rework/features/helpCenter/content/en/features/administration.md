---
title: Administration
order: 60
description: What reaches beyond a single team, and why you probably cannot see it.
icon: admin_panel_settings
---

# Administration

Some decisions reach beyond one team: which teams exist, which functions are
open to them, who holds a platform role. They live in the **administration
console**.

> Pages depend on your role: organization Owners manage business features;
> technical administrators manage their administrative scope (see
> [Teams and permissions](/help/en/features/teams-and-permissions)).

## Getting there

**Profile menu** (bottom of the navigation panel) → **Administration**. Everyone
lands on the first page they are allowed to see; two administrators therefore
do not necessarily reach the same page.

## Organization applications

As an **organization Owner**, open **Administration > Features > Apps**.
Register the UI address and, if needed, API address supplied by the service
operator. The service must already be deployed and trusted. A new registration
is not authorized: use **Edit** to review it and authorize use in the organization.
Team and project settings can restrict this access further. Registration does
not deploy the service and requires no Fred restart.

The cog beside the organization name manages that workspace's members and resources;
**Administration** contains organization-wide feature configuration.

## Organization Knowledge Bases

Each application or KB collector deployment serves one organization only. Reusing
the image does not share its service, credentials or data.

In **Administration > Features > Knowledge Bases**, the organization Owner registers
the collector identity and credential reference names supplied by the operator.
The operator deploys the collector; refresh the page to see and authorize its
published definitions. No Fred restart is needed.

A space Owner then opens **Knowledge Bases** in that space to create a collection:
source settings, credential references, document processing and synchronization
interval. Source settings are fixed at creation; the interval and pause flag can
be changed. Documents open in the usual read-only explorer. Deleting the collection
also retires its documents. Never paste secret values into Fred.

## What is in it

- **Teams** — the list of every team, and team creation.
- **Platform roles** — who holds which cross-cutting role.
- **Users** — the platform's accounts.
- **Features** — the catalogue of functions and their opening per team.
- **Platform prompts** — the instructions shared by agents.
- To choose the model the **creation assistant** uses for drafts, open
  **Features → Models → Default models → Agent design**. Without a dedicated
  choice, it follows the space default model.
- **User interface** — the default theme and the themes available to users.
- **Announcements** — the banners and patch notes shown to users.
- **Marketplaces** — who may publish agents to the marketplace, and how many.
- **Analytics** — platform-wide usage indicators.
- **Activity** — running work and its history.
- **Self-test** and **Corpus audit** — the health checks.
- **Platform data** — export and import of the platform's state.

## The interface theme

Each user picks their theme (Pebble, Cobalt, Cloud…) and their light, dark or
system mode in **Profile** → **Interface: theme and mode**.

On the **User interface** page, each theme has its tile, with its three main
colors. A **Platform admin** decides there:

- the **offered themes**: a disabled theme disappears from users' profile;
- the **default theme**, with **Set as default**: the one users get until they
  choose one. Pebble is the default until someone changes it. The default theme
  is always offered.

Each change is saved at once.

A user whose theme is no longer offered moves to the default theme. Their choice is kept: it comes back if the theme is offered again. Picking a theme in
the profile, even the one already shown, keeps it afterwards if the default
theme changes. When a single theme is offered, the profile only shows the mode. Changes apply at once
for the administrator, and for other users when they return to the
application or within a minute.

To add a theme in your organization's colors, see
[Create a custom theme](/help/en/guides/custom-theme).

## Marketplaces

On the **Marketplaces** page, a **Platform admin** decides in which teams the
editors may publish agents to the marketplace (see
[Agents](/help/en/features/agents#the-agents-marketplace)):

- a **Publishing** row: **Disabled** or **Enabled**, and how
  many agents a team may publish (5 unless changed). Every team follows it,
  including teams created later;
- per team, **Off**, **Default** or **On**. Its **Max agents** follows the
  default value; **Customize** gives it its own, with a way back to the default.

Turning publishing off for a team removes its published agents from the
marketplace; the confirmation states how many first. Lowering the max agents
keeps the agents already published but blocks new publications.

## The platform presentation template

On the **Features** page, the **Generate a presentation** row has a
**Platform settings** icon. A **Platform admin**
chooses there the PowerPoint template of agents without one of their own (the
built-in template until changed):

- **Upload a .pptx template** — the file is read in the background. Until the
  reading succeeds, or if it fails, agents keep the previous template.
- **Use a vision model** — unavailable in Weaver. Structural analysis works without a model call; review slide names and kinds manually.
- **Review slides** — rename a slide, change its kind or set it aside. The
  edits are saved when the review closes and apply to every agent using this
  template. A new reading of the same file keeps them; another file starts
  without edits. With no uploaded template, you edit the built-in template's
  slides the same way.
- **Resetting to the built-in template** — deletes the template and every edit,
  including edits to the built-in template, after a confirmation.

A change reaches every agent within a minute.

## Who opens functions to your team

The **organization Owner** authorizes business features in **Features**.
Team and project Owners can restrict that ceiling, but cannot open a feature
that the organization has not authorized. Address that request to your
organization Owner.

When a function an agent already uses is closed again, that agent is
**suspended** until it is restored.

## Two usage pages, not to be confused

- **Your team's usage** — the team's **Usage** page: consumption over time, by
  agent and by model, plus your own share. The team-wide view requires the
  **Admin**, **Editor** or **Analyst** role; a plain Member sees only their own
  consumption.
- **The platform's usage** — the console's **Analytics** page, across all users.
  It requires the **Platform observer** role.

The two pages therefore do not duplicate one another: their scopes and their
access conditions differ.
