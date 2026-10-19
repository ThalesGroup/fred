---
schema: 1
title: "Deploy Fred Manager as part of the Fred application release"
impact: major
configuration: production
configuration_reason: "Fred chart defaults now deploy manager API/worker, Knowledge Flow API/worker and frontend; control-plane and fred-agents are disabled. Manager configuration is validated by the generated chart schema."
---

## Applicability

The manager reconstruction checkout and matching fred-deployment-factory integration.
The default composition has five Deployments using three images. This replaces the
legacy default composition; it is not feature parity with every control-plane API.
The factory's pinned published legacy release retains its own composition.

## Prerequisites

Retain PostgreSQL, OpenFGA, Keycloak, Temporal and content/search infrastructure.
Use coordinated SQL/OpenFGA backups for operational rollback. Keep existing
`fred-secrets` and the operator-created `fred-model-credentials` Secret. The factory
must include the manager-aware Fred values, identity declaration and transition hook.

## Configuration

Set manager configuration and lifecycle catalog on `applications.fred-manager`;
the API and worker share these mounts and both roll when either changes. Set their
image tags together. Reference existing SQL/OpenFGA Secrets for both processes,
and identity-client/bootstrap Secrets for the API. The factory retains
`CONTROL_PLANE_BOOTSTRAP_TOKEN` as the bootstrap Secret key. Lifecycle cleanup
remains disabled by default. The single Knowledge Flow worker serves all ingestion
roles; specialized workers remain opt-in. A direct Helm deployment requires its
own addresses, ingress and credential references.

## Upgrade

For local k3d, run `make k3d-app APP=fred DIR=../fred` from the matching factory.
It builds/imports manager, Knowledge Flow and frontend, then synchronizes `fred-app`.
There is no separate manager deployment command.

When `fred-manager` already exists as a standalone release, the factory checks its
live ownership, known stateless inventory, storage/identity/lifecycle settings,
policy catalog and environment sources before removal. Unrecognized resources,
persistence, hooks or changed protected settings stop the transition. Reconcile
those differences explicitly before retrying; do not bypass the checks.
The hook saves protected manifest/values snapshots under the printed cache directory,
removes the old release with foreground waiting, then the ordinary Fred sync
creates the replacement. This causes a manager interruption; the sync is not atomic.
No database, FGA store, account or foundation Secret is reset.

## Validation

Verify five ready application Deployments, identical API/worker image references
for each pair and no control-plane/fred-agents Deployment. Check frontend and manager
health, existing accounts/consent/spaces and the paged Resources folder response.
Rerun the command: it upgrades the existing Fred release without recreating the old
manager release. A data reset is neither required nor part of this procedure.

## Rollback

After a failed sync, correct the cause and rerun the same command with the same
Fred/factory revisions. Data and credentials remain in the infrastructure; the
protected snapshots support inspection and are not a standalone rollback chart.
Do not run old and integrated manager producers together. Returning to an older
manager binary may require the coordinated pre-upgrade data backup because applied
SQL migration compatibility still applies. Removing the entire `fred-app` release
also removes Knowledge Flow and frontend; it is not a manager-only rollback.

## Limitations

Application packaging does not migrate legacy content, roles or service APIs.
Existing UI and legacy proxy routes remain; requests to stopped services return
errors. Manager owns the reconstructed folder journey; document ingestion remains
outside that journey. This lot does not change the Docker Compose development topology.
