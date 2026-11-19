---
schema: 1
title: "Preserve icons and carousel styles during browser translation"
impact: minor
configuration: none
configuration_reason: "The frontend adds stable HTML attributes; no application or chart configuration changes."
---
## Applicability

Deployments with custom themes targeting the featured carousel by ARIA role description.

## Prerequisites

Access to the custom theme source and its normal deployment procedure.

## Configuration

No application configuration changes are required.

## Upgrade

In custom theme CSS, replace `section[aria-roledescription="carousel"]` with
`section[data-featured-carousel]` and `article[aria-roledescription="slide"]`
with `article[data-featured-slide]`. Deploy the updated theme with the frontend.
Themes that do not use those selectors need no changes.

## Validation

Enable browser page translation and verify carousel backgrounds, colors, and icons.

## Rollback

Roll back the frontend and theme together; restore the previous selectors in the
theme when returning to a frontend that does not expose the data attributes.

## Limitations

Custom themes are maintained outside Fred and are not automatically rewritten.
