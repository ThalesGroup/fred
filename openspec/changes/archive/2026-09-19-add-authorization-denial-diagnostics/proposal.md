## Why

An authorization denial carries no evidence of why it happened. The shared
handler discards the typed error's message and rebuilds a generic string from
the action and resource, then logs one fixed line with no fields. A denial
caused by a person's standing, a denial caused by an ordinary missing
permission, and a denial caused by the tuple store being unreachable are
therefore indistinguishable to an operator and near-identical to the caller.

The distinction already exists in the error type and is discarded: the typed
denial is raised with an `unavailable` flag at eight sites and read nowhere.
A dependency outage is additionally reported as `403`, which classifies as a
client error, so it is invisible to availability alerting.

## What Changes

- The typed authorization denial keeps its cause through the shared handler.
  A denial raised because the authorization dependency could not answer is
  distinguished from a denial that the dependency answered.
- **BREAKING** A denial whose cause is an unavailable authorization dependency
  is reported as a server-side failure rather than as `403`, so an outage is
  classified as an outage. Callers that treat any non-2xx as refusal are
  unaffected; callers that branch on `403` see the new status for this case
  only.
- The denial log line carries the fields needed to tell the causes apart:
  subject type, action, resource type, and whether the decision was reached or
  the dependency was unavailable. The line names no person and no credential.
- The caller-facing detail distinguishes a standing denial from a permission
  denial without disclosing which person, team or resource was involved, and
  without asserting a reason the platform did not establish.
- Denials arising from the standing relation are emitted as audit events, on the
  same surface the delegation grant decisions already use.

## Capabilities

### New Capabilities

- `authorization-denial-diagnostics`: what an authorization denial preserves and
  reports — the cause carried through the handler, the transport status for an
  unavailable dependency, the fields on the denial log line, the bounded
  caller-facing detail, and the audit record for a standing denial.

### Modified Capabilities

<!-- None. The rules that decide whether access is granted are unchanged; only
     what a denial reports changes. -->

## Impact

- The shared authorization error type and the shared exception handler in the
  core security library.
- The authorization engine sites that raise a denial for an unavailable
  dependency.
- Every service registering the shared handler: the platform backends, the
  agent runtime, and each first-party application backend.
- Dashboards and alerts that count `403`, which will see outage-caused denials
  move to a server-side status.
