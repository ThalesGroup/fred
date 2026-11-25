---
schema: 1
title: "Organization home with featured agents and a question launcher"
impact: minor
configuration: none
configuration_reason: "Organization settings use existing Owner roles and agent access; no environment or chart key is added."
---
## Applicability
Fresh Weaver installations with matching Control Plane and frontend versions.

## Prerequisites
Initialize the schema through the normal immutable SQLx migration chain, including
`0040_organization_home.sql`. No Swift or older Weaver data upgrade is provided.

## Configuration
An organization Owner chooses Classic or Advanced in Administration > Home page,
orders up to ten featured agents, and optionally chooses a question launcher.
Selection is limited to agents the Owner can already read in that organization's
teams/projects. Personal agents are excluded. Existing access rights are unchanged.
Themes may use the existing frontend home CSS variables.

## Upgrade
Deploy matching Control Plane and frontend components on the fresh schema.
Classic remains the default until the Owner saves Advanced.

## Validation
Save different home settings in two organizations. Check ordered cards, badges,
highlights and the question launcher. Each viewer sees only currently authorized,
enabled and prepared agents; the chat performs its usual admission again.
Check organization switches, revoked access and deleted agents. A submitted home
question must open a new conversation and send once, under normal composer guards.

## Rollback
Restore mutually compatible application and database state. Do not edit migration
checksums or assume a data-preserving downgrade; no reverse migration is supplied.

## Limitations
Featuring an agent grants no additional rights and does not publish it to other
spaces. Previously selected but inaccessible agents are shown as unavailable to
the Owner, without exposing their identity details. Deleted agents are removed by
foreign-key cascade. The chat enforces the pod input limit; home has no separate
live pod metadata lookup. Local checks do not constitute deployed UI acceptance.
