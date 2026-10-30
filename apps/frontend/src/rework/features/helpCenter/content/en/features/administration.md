---
title: Platform administration
order: 60
description: What reaches beyond a single team, and why you probably cannot see it.
icon: admin_panel_settings
---

# Platform administration

Some decisions reach beyond one team: which teams exist, which functions are
open to them, who holds a platform role. They live in the **administration
console**.

> Access to these surfaces is reserved to platform roles (see
> [Teams and permissions](/help/en/features/teams-and-permissions)): not seeing
> them is the expected behaviour. This page indicates who to address a request
> to.

## Getting there

**Profile menu** (bottom of the navigation panel) → **Administration**. Everyone
lands on the first page they are allowed to see; two administrators therefore
do not necessarily reach the same page.

## What is in it

- **Teams** — the list of every team, and team creation.
- **Platform roles** — who holds which cross-cutting role.
- **Users** — the platform's accounts.
- **Features** — the catalogue of functions and their opening per team.
- **Platform prompts** — two tabs: the **platform system prompt**, the shared
  instructions prepended to every agent's own, and the **creation assistant**,
  which helps users draft an agent from the agent form. For the assistant you
  can adapt its instructions and restore the default at any time (keep the
  `{language}` text, replaced with the user's language), and choose the model
  it uses; by default, the platform's default model. The **Reasoning**
  setting next to it lets that model think before answering when it can.
  It is off by default: in our tests it made drafts slower and costlier
  without clearly better results, so we recommend an intermediate model
  without reasoning. Depending on the model it is a switch or a choice of levels from
  Off to High; a higher level thinks longer. When reasoning is slow, the
  assistant also asks the same model without it and keeps the first proposal
  ready, which uses more tokens. This choice does not change the model of the
  agents it drafts. If the default instructions change
  after you customised them, a warning says so and lets you view them. Anyone
  who can edit a team's agents can read these instructions and the chosen
  model, so never put confidential notes in them.
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

## Who opens functions to your team

Opening a function is the responsibility of a **Platform admin** or a **Feature
manager**, never of a team administrator. That is why a function can show as not
allowed in an agent's configuration: nobody in your team can open it, and the
request has to be addressed to the platform.

When a function an agent already uses is closed again, that agent is
**suspended** until it is restored.

## The Analytics page

The **Analytics** page shows how the platform is used over a period you choose
(7 or 30 days, the last 3 or 12 months, a month or your own dates; the arrows move to
the previous or next period). Each figure is compared with the previous period
of the same length.

Its tabs: **Overview**, **Adoption** (who has access, who comes, who sends
messages, and whether newcomers come back), **Usage**, **Teams**, **Agents and
tools**, **Quality and cost** (failed answers, tokens, estimated cost in euros
and footprint) and **Technical** (storage, web research, instructions length).
Each indicator has a short explanation behind its info icon.

**Scope** narrows the page to a few teams, or comes back to **Whole platform**.
Some figures are not attached to a team and say so when teams are selected.

**User filter** limits every figure to people whose account attributes match
conditions, built like a platform access rule (for example "organisation
equals …"). Only the attributes the access rule records are offered, with
their last known value. Before you apply it, the filter shows how many people
match and how many are "without data": those who have not signed in since the
rule started using that attribute. A few configuration figures (agents
existing, team members, storage) are not filtered; the filter's info icon
lists them.

**Export** downloads the current period and scope as a workbook, with
the same figures and explanations. It contains no names, emails or messages.

## A team's analytics

A team's **Analytics** page (in its settings) shows a team **Admin** the same
analytics as the **Analytics** page, limited to their team: the same tabs
except **Technical**, the same periods and comparisons, costs in euros. There
is no scope choice: the page always shows the selected team. Figures that
only make sense across teams (active teams, share of team conversations, the
teams table) are left out; the **Teams** tab shows the team's members, how
many are active and their share.

**Export** downloads the workbook of that team only. It says nothing
about the platform's other teams.

The last tab, **My usage**, shows your own token usage, by agent and by
model, with its footprint and estimated cost. The team's Editors, Analysts and
Members see only this personal part, under the name **My usage** in the
team's settings, and in your personal space it comes with your skills.

## Two usage pages, not to be confused

- **Your team's usage** — the team's **Analytics** page, whose team part is for
  the team's **Admins**.
- **The platform's usage** — the console's **Analytics** page, across all users
  or the chosen teams. It requires the **Platform observer** role.
