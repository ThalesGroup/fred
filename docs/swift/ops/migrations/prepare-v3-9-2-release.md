---
schema: 1
title: "Prepare Fred v3.9.2 and audit dependency updates"
impact: none
configuration: none
configuration_reason: "Release notes change and the covered dependency update changes only the frontend package manifest and lockfile; no deployment setting or default is introduced."
no_action_reason: "The covered dompurify and KaTeX updates ship inside the rebuilt frontend image; normal deployment includes them."
covers:
  - 7b9f1977afe2713eac33515bb8dc5c4d4b13dcb0
---

## Applicability

Fred deployments upgrading from v3.9.1. The covered commit updates two direct frontend dependencies: dompurify from 3.4.16 to 3.4.17, fixing GHSA-cg2g-xh64-v4q7, and KaTeX, which renders math formulas, from 0.18.3 to 0.18.4, a patch release with no advisory against 0.18.3.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required for this dependency update or release preparation.

## Upgrade

Deploy the reviewed images and chart normally. No extra action is needed for the covered dependency update.

## Validation

The release PR validates the frontend build and the locked dependency installation. After deployment, a chat answer containing a math formula still renders it.

## Rollback

Use the normal release rollback procedure. This update introduces no data migration.

## Limitations

This note covers only the listed dependency commit and release preparation. Other release changes have separate notes.
