---
schema: 1
title: "Move the experimental first-user journey to fred-manager"
impact: major
configuration: production
configuration_reason: "The manager reference and integrated Fred chart enable app.gcu_version v1; the coordinated deployment is described in integrate-manager-fred-deployment.md. The branch frontend entry now requires manager instead of the control-plane shell."
---

## Applicability

Experimental `chore/rust-rebac` deployments using manager and the frontend from this
branch. The complete existing Fred UI remains available. Manager owns personal
CGU, root bootstrap, provisioning, membership/personal navigation and Resources folders. Other
features retain their previous service calls and may fail when those services are
stopped; visible UI does not imply complete Rust feature reconstruction.

## Prerequisites

Deploy Keycloak, PostgreSQL and OpenFGA for manager, its existing service-account
credentials and deployment bootstrap secret. Preserve coordinated SQL/OpenFGA
backups before upgrading an existing experimental installation.

## Configuration

The manager reference YAML and integrated Fred chart set `app.gcu_version: v1`.
Deploy corresponding frontend legal markdown assets with the configured version.
A version change requires renewed personal consent, including root. `null` disables
the gate; an omitted setting remains disabled. No consent is imported from Python.

## Upgrade

Build and deploy manager and frontend from the same branch revision. Manager runs
additive migration 0005 at startup. The frontend reads manager public configuration
before login and shows a reload action when unavailable. Accept CGU in the UI before
bootstrap or import; the obsolete `bootstrap-local` helper is removed. Existing
manager roles and spaces remain unchanged. No organization membership is implicit.
Rebuilding the frontend restores this journey in Fred's existing layout; it needs
no additional migration, Keycloak reset or reimport. Ordinary users use Home for team/personal navigation. Platform owners land on
Organizations, beside Provisioning, with no business navigation even if they also
hold organization/team roles. The account menu opens the existing
profile with manager roles and organization, browser preferences, legal texts and static release
notes. Restoring these account pages requires only a frontend rebuild/deployment;
it adds no manager migration or configuration key. The organization console requires
both manager and frontend from the same revision for GET/POST `/admin/organizations`.
It adds no SQL migration or FGA model change. Owner/admin nominees must already exist
in Keycloak and be unattached to another organization. HTTP creation grants only
Owner/Admin, while the operator `create-org` behavior remains unchanged.

Resources folder listing now returns a paged directory object instead of an array;
deploy manager and frontend together. Creation, rename and document-free subtree
deletion use manager. This requires no SQL migration, model replacement or role
rewrite. Existing manager folder IDs remain valid. No legacy knowledge-flow tags
or documents are converted.

## Validation

Run `make -C apps/frontend test-provisioning-browser` against its disposable services.
For the deployed journey, accept CGU, bootstrap root, import the Make ZIP and read
its completed report. Sign out and sign in as an imported person: accept their own
CGU and verify their organization/space memberships. Root remains without implicit
membership. Verify the owner registry shows imported organizations and a direct
Home/team URL returns to Organizations. Create an organization using two existing
unattached accounts and verify the selected Owner/Admin roles without content grants.
From either admitted account, open Profile, check the platform roles,
change a preference and reload, then consult CGU, privacy and release notes. CGU
consultation must not ask for a second acceptance. Legacy Python admission records
do not satisfy manager admission.

## Rollback

Prefer a forward correction. Older manager binaries reject an unknown applied SQL
migration, so replacing images alone is insufficient. To return to the prior pair,
stop writers and restore the coordinated pre-upgrade SQL/OpenFGA backup, then deploy
the prior manager/frontend images. This loses changes made after that backup. Do
not edit an applied migration or delete its history record to force a rollback.

## Limitations

The original Resources components display manager folders. Document sending is
explicitly unavailable from upload/drop/import and selection actions; this deployment
does not migrate ingestion or display manager documents in that view. Knowledge-base
consumers and statistics/quota retain their existing services. Manager resource UUIDs
are not converted to knowledge-flow tag IDs.
Existing root roles
remain authoritative in OpenFGA; there is no role mirroring or compatibility layer.
The browser acceptance uses real governance APIs but does not start Temporal or
validate the remaining content, admission and administration journeys.
