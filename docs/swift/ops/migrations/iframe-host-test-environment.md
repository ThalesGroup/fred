---
schema: 1
title: "Keep iframe host tests compatible with patched DOM tooling"
impact: none
configuration: none
configuration_reason: "Only frontend test environments and assertions change; production configuration, iframe sandbox settings and Helm values are unchanged."
no_action_reason: "This is a test-only compatibility fix and requires no operator or deployment action."
---
## Applicability

Frontend host-page tests and packed iframe SDK host integration checks.

## Prerequisites

Use the existing locked frontend development dependencies.

## Configuration

No configuration changes are required.

## Upgrade

Use the normal build and test workflow. The iframe host tests use the existing
jsdom environment to obtain child windows without remote iframe requests.

## Validation

Run frontend quality/default tests and packed SDK host integration. The checks
must retain sandbox, stale-frame, handshake, context and binary relay assertions.

## Rollback

Revert the test-only commit. Production behavior and persisted data are unaffected.

## Limitations

The security dependency updates remain in the separate Dependabot PR. This test
harness does not replace real-browser integration coverage.
