## Why

The 2026-10-19 fred-manager audit (issue #3092) found five edge behaviours that differ
from the Python stack or hide operational causes. Fred's rule for this reconstruction
is behaviour parity with Python, with no new feature.

## What Changes

- `serve` drains in-flight requests on SIGTERM/Ctrl-C, as uvicorn does; the chart
  grants the pod enough termination time for the upload transfer deadline.
- A malformed role subject is refused with 422 before any authorization write,
  instead of a misleading 409 "authorization changed; retry".
- Revoking a space role the target does not hold emits no revocation audit event.
- Object-store failures log their cause server-side; clients keep the neutral 503.
- CLI import setup failures are classified by error type, not by message text.

## Capabilities

### New Capabilities

### Modified Capabilities
- `fred-manager-provisioning`: role subjects are validated before writes; revocation
  audit reports only removed roles.
- `document-storage`: transfers survive a graceful stop; storage failures are diagnosable.

## Impact

`apps/fred-manager` (serve shutdown, role routes, audit emission, object store,
CLI import), chart deployment template/values/schema for the termination grace
period, arc42 operations and security chapters, the branch migration note.
