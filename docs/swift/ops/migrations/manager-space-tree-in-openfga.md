---
schema: 1
title: "Move the fred-manager space tree to OpenFGA with descending roles"
impact: major
configuration: local
configuration_reason: "Experimental fred-manager only; no configuration key changes. Existing manager data must be reset because its OpenFGA model and SQL schema change incompatibly."
---

## Applicability

Experimental `chore/rust-rebac` deployments running fred-manager. Python services,
the production Fred chart and Fred's frontend behavior are unchanged.

## Prerequisites

A dedicated local k3d installed by the factory, with its `k3d-app-reset` command.
Existing manager spaces, roles, consent and bootstrap state are discarded.

## Configuration

No new setting. `security.rebac.sync_schema_on_init` must stay enabled so manager
can publish its store after the reset.

## Upgrade

Deploy the new manager image. Migration 0006 removes `space.parent_id` and
`space.path`; the space tree now lives in OpenFGA `parent` links. Manager refuses
to start on existing state without a matching published model, and the offline
`migrate-authorization` command no longer exists. From the factory, run
`make k3d-app-reset DIR=<fred checkout>` to preview, then add `CONFIRM=reset`.
Accept CGU, bootstrap root and import the bundle again.

## Validation

Sign in as a person holding analyst or editor on an organization: Home lists its
teams and projects. A member of the organization only sees the organization. A
personal space is listed alone, without the organization in its path.

## Rollback

Reset local data again, then deploy the previous manager image. Data created with
this version is not readable by the previous one.

## Limitations

Editor, admin and analyst reach every descendant; a project cannot be hidden from
its team's editors, administrators or analysts. Scope levels are available in
`POST /authorize/scope`; no Python caller uses them yet.
