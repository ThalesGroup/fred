---
schema: 1
title: "Patch pyasn1 ASN.1 decoding denial of service"
impact: none
configuration: none
configuration_reason: "Only the locked pyasn1 patch release changes; application configuration and Helm values are unchanged."
no_action_reason: "The corrected dependency is included by the normal locked build and deployment process; no data migration or extra operator step is required."
---
## Applicability

Fred Python applications and libraries whose lockfiles include pyasn1.

## Prerequisites

No additional prerequisites beyond the normal build and deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Build and deploy normally using the committed lockfiles. They resolve pyasn1
0.6.5 instead of 0.6.4 to address CVE-2026-119194, CVE-2026-119195,
CVE-2026-119196 and CVE-2026-119197.

## Validation

Confirm that affected lockfiles and rebuilt environments use pyasn1 0.6.5,
then rerun dependency scanning and the existing default offline tests.

## Rollback

Revert the dependency update and rebuild using the previous lockfiles. This
restores the vulnerable dependency version and should only be temporary.

## Limitations

This note covers the pyasn1 patch only. It does not declare unrelated operating
system packages or other dependencies free of vulnerabilities.
