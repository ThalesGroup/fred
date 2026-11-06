## Context

See proposal.md. `capability_gate_exempt` (product/service.py) is the single allowlist of internal harness templates whose template capability is never admitted. Its other callers (template listing, enrollment, copy, capability impact) already bypass the gate for them.

## Decisions

Apply the same allowlist check before the update gate. Visibility of non-public templates (platform admin only) remains the access control for the harness, exactly as at enrollment. Treating every `public=False` template as exempt is rejected: that flag has its own meaning and other non-public templates must still go through admission.

## Risks / Trade-offs

None beyond the existing exemption: an instance that could be enrolled without a grant can now also be edited without one. Ordinary templates keep the revoked-access 403.

## Migration Plan

Normal control-plane deployment and rollback; no operator action.
