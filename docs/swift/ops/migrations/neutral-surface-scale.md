---
schema: 1
title: "Rework the neutral palette, surfaces, text and outlines of the frontend themes"
impact: none
configuration: none
configuration_reason: "CSS token values and usages only; no configuration keys or defaults change."
no_action_reason: "The new colors ship with the frontend image; no operator or user step is needed."
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

Teams that build custom UI on `@fred-oss/design-tokens` must follow the
"Token migrations" section of that package's README when they upgrade it:
some tokens were removed (for example `--outline-retreat`).

## Validation

Open the application in the light theme: the page background is white, menus
and dialogs are white with a shadow, input fields are white with a grey border, and
secondary text is a mid grey rather than near black.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
