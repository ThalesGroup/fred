---
schema: 1
title: "Open explicit personal spaces through fred-manager"
impact: major
configuration: none
configuration_reason: "No configuration key, default or chart change. The upgrade uses the existing sync_schema_on_init option during coordinated startup."
---

## Applicability

Experimental `chore/rust-rebac` deployments with the pinned model immediately before
personal-space eligibility. The new role is explicit, organization-only and grants
no content access. No SQL migration is needed.

## Prerequisites

Preserve coordinated SQL/OpenFGA backups and stop all older API/CLI writers. Deploy
matching manager and frontend versions. The upgrade accepts only the exact published
predecessor; unknown models require operator reconciliation and are not reset.

## Configuration

Enable existing `security.rebac.sync_schema_on_init` for manager startup. Ordinary
load, create-org and import do not upgrade and refuse the predecessor until startup
publishes the new model. No new configuration key or chart value is introduced.

## Upgrade

Start manager with schema synchronization enabled. Under its platform SQL lock,
it publishes the additive model in the same store and commits its model ID to
`authorization_store`. Existing tuples, guards and spaces remain unchanged.
A failed SQL publication leaves the old pointer usable for retry; concurrent
initializers converge. An unused model does not become authority.

Grant `personal_space_creator` explicitly through organization role administration
or bundle roles. The person must have direct content membership of that organization.
The demo declares it only for Priya. First explicit opening creates the space;
import, login and consent do not. Remove this entitlement before removing the
person's final organization content role, along with dependent personal/child roles.

## Validation

Priya's first `POST /me/personal-space` returns 201. Repeated opening returns 200
with the same UUID, replacing the former duplicate-creation 409. Existing readable
spaces remain usable without the creation role. Opening restores no revoked grants.
`GET /me/spaces` includes `organization_id`, while a personal path contains only
its own UUID. Bob without entitlement cannot create. Run manager integration and
browser acceptance against disposable services.

## Rollback

Old binaries reject the upgraded pinned model. Stop writers and restore coordinated
SQL/OpenFGA backups before restoring old API/CLI/frontend versions. Do not point
SQL at an older model while retaining new role tuples. Preserve post-backup content
before restoration; do not reset a shared installation.

## Limitations

Personal lookup reads all organization links under the organization lock. Tests
cover pagination and concurrency 2, not a throughput guarantee. Resources,
documents and conversations are separate features from this navigation command.
