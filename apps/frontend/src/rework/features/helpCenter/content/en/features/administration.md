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
- **Announcements** — the banners and patch notes shown to users.
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
theme changes. When a single theme is offered, the profile only shows the mode. Changes apply
the next time each user loads the application.

## Announcements

The **Announcements** page lets a **Platform admin** reach every user. It
offers two types of announcement:

- the **banner**: a short message shown at the top of the application while it
  is active. It suits news of the moment (maintenance, an incident). Several
  banners can be active at once;
- the **patch note**: a longer text shown in a window when users arrive in the
  application. It suits presenting a new release.

To create one, click **New announcement**, then choose **Banner** or
**Patch note**: the matching form opens straight away.

Both types appear in the same list. A patch note shows there in a neutral
style, under its title, with the number of users who chose to hide it.

### Writing a patch note

Choosing **Patch note** opens the editor. Start with the **Patch note title**:
plain text that names the patch note in the list and at the top of the window
users see. The text below is written in Markdown (headings, lists, links).
Title and text are written in French and in English: the language switch moves
from one to the other. Each language you fill in needs both a title and a text.
A preview next to the text updates as you type. If you close the editor with
changes that are not saved, you are asked before they are lost.

On a patch note that is not active, **Save** keeps it without showing it to
users: switch it on in the list when it is ready, or use **Save and activate**
to do both at once.

**Preview as users see it** opens the exact window users will see, with the
current text, even before it is saved. The same preview is available from the
list. A preview has no effect: ticking **Don't show again** in it records
nothing.

### One active patch note at a time

Activating a patch note deactivates the one that was active. Before that
happens, a confirmation names the patch note that will be switched off. Banners
are not affected.

Switching a patch note off and on again shows it to everyone again, even to
those who had ticked **Don't show again**. Changing it while it is active does
not show it again. To announce a new release, create a new patch note: everyone will see
it. A patch note activated while a user is working is shown to them the next
time they load the application. Users can also reopen the active patch note at
any time from their profile menu, under **What's new**.

### Activation history

At the top of the page, the **Announcements** / **History** switch moves
from the list of announcements to the history. **History** is a table of the
latest activations and deactivations, banners and patch notes alike, newest
first: the announcement, its type, the action, the date and time, and the
administrator who did it. A banner's type takes the banner's colour. Clicking
a column title sorts the table. The **All**, **Activations** and
**Deactivations** filters above the table show one kind of action only; your
choice is kept for next time. An automatic deactivation (when another patch
note is activated) is listed under the administrator who did the activation.
The history stays available after an announcement is deleted.

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
