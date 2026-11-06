---
schema: 1
title: "Build the Python images behind TLS inspection with the host's CA bundle"
impact: none
configuration: none
configuration_reason: "Only the image build changes: make docker-build lends the host's CA bundle to BuildKit as a secret; no chart value, configuration key or default changes."
no_action_reason: "The published images are built the same way and never contain the bundle; deployments pull and run them as before."
---

## Applicability

Developers and CI building Fred's Python images (control-plane-backend,
fred-agents, knowledge-flow-backend) with `make docker-build`, notably behind
TLS inspection (e.g. Zscaler). Deployments of published images are unaffected.

## Prerequisites

Docker with BuildKit, the default builder since Docker 23.

## Configuration

No configuration changes are required. `make docker-build` passes
`SSL_CERT_FILE` (by default `/etc/ssl/certs/ca-certificates.crt`, when present)
as the `ca-bundle` build secret; set `SSL_CERT_FILE` to another bundle to use it.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

`make -n docker-build` in `apps/control-plane-backend` shows
`--secret id=ca-bundle,src=<bundle>`, and the build succeeds behind TLS
inspection once the corporate root is in the host's bundle.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The frontend image does not take the bundle: its `npm` install behind TLS
inspection is not covered by this change.
