---
schema: 1
title: "Gate JavaScript in HTML artifacts behind a per-team setting"
impact: minor
configuration: none
configuration_reason: "The posture is stored per team in the existing capability-settings table and edited from the admin UI; no configuration key, default, or chart value changes."
---
## Applicability

Existing Fred deployments upgrading to this release, on which the
`html_artifact` capability is enabled for at least one team.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. The new `allow_javascript` setting is
per team, stored in the capability-settings table the platform already has, and
edited from the capability administration screen.

## Upgrade

Deploy Fred normally. No schema change and no data migration: a team with no
stored value is treated as not allowed, which is the declared default.

Every team keeps HTML and CSS generation exactly as before. Script execution is
**off** for every team until an administrator turns it on, so an upgrade alone
changes nothing an operator has to prepare for.

## Optional activation

Granting a team the right to run model-authored JavaScript is a posture
decision, not an upgrade step. It is optional, and it is what makes this note
`minor` rather than `none`.

To grant it: administration → the capability's team matrix → the team's
settings → enable **Allow JavaScript**. The pinned **All personal spaces** row
carries the same control for every personal space at once. The decision is read
at display time,
so revoking it immediately renders already-generated interactive artifacts
inert, including those in conversation history.

What the grant does and does not widen:

- It allows script to execute inside the artifact frame, which stays sandboxed
  without `allow-same-origin`.
- It does **not** relax the content security policy. Both postures keep
  `default-src 'none'`, so an artifact cannot fetch a subresource or reach the
  network in either mode.
- A team that has not been granted it cannot store a page containing script at
  all: the tool refuses it and the model re-renders without it.

## Validation

With a team that has not been granted the setting, ask its agent for an
interactive page: the artifact renders and its buttons do nothing, and the
viewer says script was suppressed. Grant the setting to that team, ask again,
and the new artifact is interactive.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
Stored settings rows are inert to an older build, which reads no team setting
for this capability.

## Limitations

Personal spaces are governed as one class: granting the option turns it on for
every personal space at once, and there is no way to grant it to one person
only. This mirrors how personal access itself is granted.
