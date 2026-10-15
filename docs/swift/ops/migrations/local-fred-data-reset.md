---
schema: 1
title: "Reset dedicated local Fred data without rebuilding infrastructure"
impact: minor
configuration: local
configuration_reason: "Adds an opt-in factory reset command for the dedicated base k3d installation; production chart values and APIs are unchanged."
---

## Applicability

Developers repeating first-user tests on a dedicated factory k3d with Fred and
optional fred-manager. Existing deployments require no reset to upgrade.

## Prerequisites

Use the matching factory version exposing `k3d-app-reset`, and a Fred checkout
containing `deploy/k3d/reset`. Stop host-side Fred processes using local ports.
Other applications and unsupported storage settings are refused.

## Configuration

No production changes. The command uses the installed release configuration and
images. `CONFIRM=reset` explicitly enables deletion; omission only previews.

## Upgrade

From the factory, preview with `make k3d-app-reset DIR=<fred checkout>`. To discard
Fred's test data, repeat with `CONFIRM=reset`. This retains Keycloak identities,
credentials and infrastructure, but erases business data, consent, authorization,
content, application indexes and Temporal work. It replays installed migrations
and restores service replicas. Deploy code separately with `make k3d-app`.

## Validation

Wait for reset success and refresh the browser. Log in with an existing account,
accept the active CGU, bootstrap the platform administrator and import the bundle.
Root has no organization membership until explicitly granted by provisioning.

## Rollback

Deleted data has no automatic rollback. On reset failure, keep Fred stopped,
resolve the failure and repeat the command using its saved target-scoped state.
Do not erase that state to bypass a changed-deployment refusal.

## Limitations

Dedicated base k3d only; no shared application cleanup or production recovery.
Concurrent deployment and reset, external writers, and multiple factory checkouts
controlling one target are unsupported. Reset preserves existing Keycloak accounts
and their passwords; it is not an identity-provider wipe.
