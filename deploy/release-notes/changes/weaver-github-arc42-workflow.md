---
schema: 1
title: "Use GitHub and arc42 for Weaver delivery"
impact: none
configuration: none
configuration_reason: "Contributor instructions, retired specification tooling, image-selection documentation paths and test-only corrections do not change deployment configuration."
no_action_reason: "No runtime behavior, schema, permissions or operator procedure changes; deploy normally."
covers: [850e11718b90426768759c8cc75eff9dd89768fe]
---
## Applicability

Weaver contributors preparing the first integration release. This applies the
team's OpenSpec retirement decision tracked in GitHub #3653 to Weaver.

## Prerequisites

No additional deployment prerequisites.

## Configuration

No configuration changes. GitHub epics and issues own shared work and acceptance;
arc42 remains the architecture reference. OpenSpec commands, skills and files are
removed. The frozen porting journal is retained only for evidence reconciliation.

## Upgrade

No additional action. Old specifications remain recoverable from Git history
before this change, including commit `a19d183da` on Weaver.

The reviewed contribution `850e11718` only corrects spreadsheet test synchronization
and session-title test deadlines under coverage. It changes no application code.

## Validation

Verify the contributor entry points use GitHub and arc42, the image selector's
focused checks pass, and the initial release report passes coverage and freshness
verification. These checks do not certify a deployed platform.

## Rollback

Revert the contributor-tooling change if needed. No data rollback is required.

## Limitations

This cleanup does not close historical issues or certify the old porting journal.
Domain owners still need to reconcile remaining work and record platform reception
in the existing GitHub issues.
