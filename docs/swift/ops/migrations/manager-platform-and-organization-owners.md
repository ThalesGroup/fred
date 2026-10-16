---
schema: 1
title: "Replace fred-manager platform admin and team manager with owners"
impact: major
configuration: local
configuration_reason: "Experimental fred-manager only; no configuration key changes. Role names and the OpenFGA model change incompatibly, so existing manager data must be reset."
---

## Applicability

Experimental `chore/rust-rebac` deployments running fred-manager. Python services and
the production Fred chart keep their own role catalog.

## Prerequisites

A dedicated local k3d installed by the factory, with its `k3d-app-reset` command.
Existing manager roles, spaces, consent and bootstrap state are discarded.

## Configuration

No new setting. Provisioning bundles use `platform_owner` instead of `platform_admin`
(alias `owner` instead of `admin`), drop `team_manager`, and declare at least one
`owner` on every new organization.

## Upgrade

Deploy manager and frontend from the same revision. Reset local data from the factory
with `make k3d-app-reset DIR=<fred checkout> CONFIRM=reset`, then accept CGU, bootstrap
root and import a bundle built with `make build-demo-bundle`.

## Validation

Root sees Provisioning. In the demo, Oscar is owner of Demo: he names Demo's admins
and sees no content. Alice, also a platform owner, can replay the bundle.

## Rollback

Reset local data again, then deploy the previous manager and frontend images.

## Limitations

Organization owners have no quota or FinOps settings yet. The bootstrap route keeps
its `/bootstrap/platform-admin` path.
