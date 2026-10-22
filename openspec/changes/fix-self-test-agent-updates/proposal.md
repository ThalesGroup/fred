## Why

The self-test harness templates (`fred.github.self_test`, `fred.github.self_test_web`) are exempt from the agent-template capability gate: they are never admitted, so no team ever holds a `can_use` tuple on them. Enrollment, listing, copy and impact checks honour that exemption, but `update_agent_instance` re-checks the gate unconditionally. An admin can enroll the harness agent yet every later edit (system-prompt tuning, disable/enable) returns 403 "template access has been revoked", which breaks the self-test agents family. Origin: #3198.

## What Changes

- Skip the template access re-check on agent update for gate-exempt templates, using the existing `capability_gate_exempt` allowlist.
- Keep the re-check, and its 403, for every ordinary template.
- Add regression tests for disable/enable and prompt tuning of an exempt instance with no `can_use` tuple.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `admin-self-test`: the harness agent instance stays editable after enrollment.

## Impact

Control-plane backend `product/service.py` and its tests only. No API, schema, permission model, configuration or migration change.
