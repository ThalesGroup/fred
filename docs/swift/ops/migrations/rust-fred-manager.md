---
schema: 1
title: "Replace the Python control-plane with the Rust fred-manager"
impact: major
configuration: production
configuration_reason: "The control-plane-backend image and workloads run Rust fred-manager with its own configuration; optional storage.content enables S3 original storage."
---

## Applicability

Fred deployments adopting the Rust fred-manager reconstruction. Manager serves
organizations, teams, projects, personal spaces, roles, provisioning, folders,
immutable originals and deferred space deletion. It runs as `control-plane-backend`
and `control-plane-worker`, next to Knowledge Flow API/worker and the frontend. The
Python control-plane and fred-agents do not run. APIs not yet reconstructed fail.

## Prerequisites

Fred does not migrate existing data. Users, roles, teams, conversations and
documents from a Python control-plane or Knowledge Flow installation are the
concern of a separate migration application, never of Fred code.

Manager keeps no backward compatibility before its first production release: its
SQL schema is one baseline and its OpenFGA model is replaced, not upgraded. Startup
refuses a database or store created by an earlier manager build. On a dedicated
factory k3d, reset Fred data first with `make k3d-app-reset DIR=<fred checkout>
CONFIRM=reset`; Keycloak accounts and infrastructure are retained.

## Configuration

Configure manager on `applications.control-plane-backend`; API and worker share its
configuration and lifecycle catalog. `security.m2m.enabled` is required; the chart
default sets it to `true`. The existing `control-plane` Keycloak client
and `fred-secrets/KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET` supply directory access;
`CONTROL_PLANE_BOOTSTRAP_TOKEN` remains the bootstrap secret. Manager uses database
`fred`, OpenFGA store `fred-manager` and lifecycle queue `fred-manager-lifecycle`.
Space deletion stays disabled until `scheduler.lifecycle.enabled` is set.

Original storage is optional and disabled when `storage.content` is omitted. To
enable it, apply `deploy/charts/fred/examples/document-storage.yaml` as an instance
overlay with a private bucket that never has versioning, Object Lock or enabled
lifecycle rules, and grant Put/Get/Delete/List plus bucket configuration reads.

## Upgrade

From the unchanged factory `swift` checkout, run `make k3d-app APP=fred DIR=../fred`.
When the previous build used manager-named applications, first move the active
cache's `.cache/k3d-apps/fred-<id>/images.yaml` and `images.txt` aside; otherwise
the initial lint rejects the retired names. The migration hook applies the SQL
baseline with `DATABASE_URL` only. A separately owned `fred-manager` release is
refused: retire it explicitly before retrying.

## Validation

Check five ready application Deployments with matching API/worker images. Log in,
accept the active CGU, bootstrap the platform owner and import a provisioning ZIP.
An editor creates a folder in Resources; with original storage enabled, uploads a
file, reloads and downloads identical bytes. An admin alone cannot read content.

## Rollback

There is no data rollback. Returning to the Python control-plane requires restoring
coordinated SQL, OpenFGA and object storage backups taken before the switch, with
manager writers stopped.

## Limitations

Manager does not serve agents, conversations, ingestion or search, and does not
evaluate Python platform-access admission or the team-administrator charter.
Individual originals are capped at 100 MiB; stored means retained, not indexed.
