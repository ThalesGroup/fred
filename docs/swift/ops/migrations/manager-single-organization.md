---
schema: 1
title: "Enforce one organization per person in fred-manager"
impact: major
configuration: none
configuration_reason: "No new configuration or SQL/OpenFGA schema; manager now rejects cross-organization role assignments and ambiguous business context."
---

## Applicability

Experimental `chore/rust-rebac` manager deployments. A person can belong to only one
organization per Fred instance, including governance-only roles. Platform authority
remains independent and does not grant content access.

## Prerequisites

Preserve coordinated SQL/OpenFGA backups. Inspect existing direct role tuples and
committed space placement for subjects whose roles span organizations. Confirm the
intended organization with its administrators; do not automatically choose one.

## Configuration

No new configuration, identity-provider claim or organization URL parameter.

## Upgrade

Deploy all manager API/CLI writers and the frontend from the same revision. No
SQL or OpenFGA model migration runs for this rule. Old writers must not remain active:
they can violate the new assignment invariant. Contradictory existing grants cause
HTTP 409 on business-context operations; no grant or content is silently removed.

Use the existing authorized revocation paths to remove unintended grants bottom-up,
respecting required administrators/owners and dependent personal roles. The target
may have ambiguous context; the administrator must retain their required authority.
Platform-owner authority only bypasses organization context for its explicit platform
operations, including organization-owner administration. It is not content authority.
See [organization recovery](../../../architecture/A3-manager-operations.md#organization-conflict-recovery).

## Validation

An imported person opens their one organization at `/home`, without a tenant selector
or organization parameter. A second organization assignment fails. Another
organization's space/document identifiers grant no business access. Platform-only
root still sees an empty Home and authorized provisioning. Run manager integration
and browser acceptance against disposable services.

## Rollback

No schema rollback is needed. Restoring earlier manager/frontend binaries restores
the former permissive assignment behavior and removes this guarantee. Preserve
coordinated backups and correct unwanted grants explicitly before resuming writers;
do not reset shared data or edit applied migrations.

## Limitations

Role changes across organizations serialize under the existing platform lock and
OpenFGA guard. This favors a single enforceable invariant over concurrent unrelated
role mutations; it does not establish a throughput guarantee. Authentication and
consent alone attach nobody and create no personal space.
