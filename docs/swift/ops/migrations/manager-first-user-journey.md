---
schema: 1
title: "Move the experimental first-user journey to fred-manager"
impact: major
configuration: local
configuration_reason: "The experimental manager reference and standalone k3d overlay enable app.gcu_version v1; the production Fred chart does not configure this experimental component. The branch frontend entry now requires manager instead of the control-plane shell."
---

## Applicability

Experimental `chore/rust-rebac` deployments using manager and the frontend from this
branch. This entry exposes only personal CGU, root bootstrap, memberships and
provisioning. It replaces the full product entry for this branch; it is not a
transparent upgrade of the legacy Fred UI.

## Prerequisites

Deploy Keycloak, PostgreSQL and OpenFGA for manager, its existing service-account
credentials and deployment bootstrap secret. Preserve coordinated SQL/OpenFGA
backups before upgrading an existing experimental installation.

## Configuration

The manager reference YAML and standalone k3d overlay set `app.gcu_version: v1`.
Deploy corresponding frontend legal markdown assets with the configured version.
A version change requires renewed personal consent, including root. `null` disables
the gate; an omitted setting remains disabled. No consent is imported from Python.

## Upgrade

Build and deploy manager and frontend from the same branch revision. Manager runs
additive migration 0005 at startup. The frontend reads manager public configuration
before login and shows a reload action when unavailable. Accept CGU in the UI before
bootstrap or import; the obsolete `bootstrap-local` helper is removed. Existing
manager roles and spaces remain unchanged. No organization membership is implicit.

## Validation

Run `make -C apps/frontend test-provisioning-browser` against its disposable services.
For the deployed journey, accept CGU, bootstrap root, import the Make ZIP and read
its completed report. Sign out and sign in as an imported person: accept their own
CGU and verify their organization/space memberships. Root remains without implicit
membership. Legacy Python admission records do not satisfy manager admission.

## Rollback

Prefer a forward correction. Older manager binaries reject an unknown applied SQL
migration, so replacing images alone is insufficient. To return to the prior pair,
stop writers and restore the coordinated pre-upgrade SQL/OpenFGA backup, then deploy
the prior manager/frontend images. This loses changes made after that backup. Do
not edit an applied migration or delete its history record to force a rollback.

## Limitations

The legacy full Fred UI is outside this experimental entry. Existing root roles
remain authoritative in OpenFGA; there is no role mirroring or compatibility layer.
The browser acceptance uses real governance APIs but does not start Temporal or
validate the remaining content, admission and administration journeys.
