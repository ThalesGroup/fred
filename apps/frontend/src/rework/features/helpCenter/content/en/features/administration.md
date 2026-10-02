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
- **Platform prompt** — the shared instructions prepended to every agent's own.
- **User interface** — the default theme and the themes available to users.
- **Analytics** — platform-wide usage indicators.
- **Activity** — running work and its history.
- **Self-test** and **Corpus audit** — the health checks.
- **Platform data** — export and import of the platform's state.

## The interface theme

Each user picks their theme (Pebble, Cobalt, Cloud…) and their light, dark or
system mode in **Profile** → **Interface: theme and mode**.

On the **User interface** page, a **Platform admin** decides:

- the **default theme**, the one users get until they choose one;
- the **offered themes**: an unchecked theme disappears from users' profile.

A user whose theme is no longer offered moves to the default theme, or to the
first offered theme when no default is set. Their choice is kept: it comes back if the theme is offered again. Picking a theme in
the profile, even the one already shown, keeps it afterwards if the default
theme changes. When a single theme is offered, the profile only shows the mode. Changes apply
the next time each user loads the application.

## Who opens functions to your team

Opening a function is the responsibility of a **Platform admin** or a **Feature
manager**, never of a team administrator. That is why a function can show as not
allowed in an agent's configuration: nobody in your team can open it, and the
request has to be addressed to the platform.

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
