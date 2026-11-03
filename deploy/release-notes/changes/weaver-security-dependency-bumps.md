---
schema: 1
title: "Update frontend and Python dependencies to patched versions"
impact: none
configuration: none
configuration_reason: "Only dependency constraints and lockfiles change; deployment settings are unchanged."
no_action_reason: "Normal image and frontend builds install the updated locked dependencies without an operator migration."
---
## Applicability

Existing Weaver deployments and frontend package consumers upgrading to this release.

## Prerequisites

Use the normal build process with access to the locked package sources.

## Configuration

No configuration changes are required.

## Upgrade

Build and deploy the updated frontend, agent and Knowledge Flow images. The
frontend package fixtures and isolated consumers use the matching Vite version.

## Validation

Check the resulting lockfiles for Temporal 1.35.0, pyasn1 0.6.5, pypdf 6.21.4,
Vite 6.4.5, KaTeX 0.18.6, happy-dom 21.0.4, fast-uri 3.1.9 and minimatch 10.2.6.

## Rollback

Use the previous application images and frontend packages. No data migration is involved.

## Limitations

This update does not alter the installed Node.js major version; that change is
delivered separately.
