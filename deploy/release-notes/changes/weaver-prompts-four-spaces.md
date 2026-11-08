---
schema: 1
title: "Weaver prompts in organization, team, project and personal spaces"
impact: minor
configuration: none
configuration_reason: "Prompt placement uses existing space roles and the existing Control Plane connection; no environment variables, secrets or chart settings are added."
---

## Applicability

Fresh Weaver installations using the matching Control Plane and frontend from this
change. This note does not certify a data upgrade from Swift or an older Weaver.

## Prerequisites

Coordinate the Control Plane, frontend and any direct prompt API consumers.
Publication routes now address an explicit marketplace space, and prompt metadata
uses `published_in` instead of the former `published` boolean.

## Configuration

No configuration changes. Existing space Read and Write permissions govern prompts
in all four space kinds; technical administration grants no prompt-content access.

## Upgrade

Initialize an empty database through the normal immutable migration chain, including
`0016_prompt_publications.sql`, and deploy matching components. The migration replaces
the publication boolean with explicit relationships; it does not copy historical
publication state. Do not apply this as a data-preserving upgrade to an older database.

## Validation

Check prompt creation, editing, favorites and deletion in each space kind with the
appropriate business roles. Platform admins can run the Prompts auto-test after
explicitly selecting a space; each write still requires that space's permission.
Confirm readers cannot edit and that personal content remains private.

## Rollback

Restore a mutually compatible application and database state. The old Control Plane
expects the removed boolean; rolling back only its image is insufficient. Do not
edit migration history or reset a shared database as part of an automatic rollback.

## Limitations

Prompt management has been received on local k3d. Marketplace publication remains a
separate application acceptance lot. No platform-wide marketplace or skill-content
management is introduced. Revoking an author's roles preserves space-owned prompts;
it does not transfer private personal content to organization editors.
