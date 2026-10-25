---
schema: 1
title: "Add optional shared agent sandbox sessions"
impact: minor
configuration: production
configuration_reason: "The Fred chart adds an optional PostgreSQL-backed broker profile, broker replicas, workspace PVCs, and admission limits. Existing values remain disabled by default."
after: [agent-code-sandbox]
---

## Applicability

Existing Fred deployments may upgrade normally. The steps below apply only when enabling the shared SIG Agent Sandbox profile.

## Prerequisites

Install the SIG controller and CRDs, a verified Kata or gVisor RuntimeClass, a deny-all sandbox NetworkPolicy, and a private RWO StorageClass compatible with that runtime. Verify the full read-only file mount separately if `/inputs` or `/skills` is required.

## Configuration

Create a PostgreSQL credential limited to the two new sandbox coordination tables and store its DSN in a Secret. Set `sandboxBroker.shared.enabled`, `coordinatorDsnSecret`, `workspaceStorageClass`, and the approved capacity, storage and queue values in the Fred chart overlay. The default profile remains disabled.

## Upgrade

Apply the control-plane Alembic migration before starting a shared broker. Install the persistent SIG template and zero-replica pool, then enable the shared broker profile. Keep one broker replica until storage, suspension and admission checks pass; increase replicas only with shared coordination enabled. Do not turn shared coordination off while its retained claims remain.

## Validation

Execute twice in one conversation with a file saved under `/work`; suspend and resume the Sandbox, then verify the file remains. Check that a second conversation cannot see it. Compare `/healthz` counts with SandboxClaims, Pods and PVCs, and verify final expiry removes the claim and PVC. Repeat with the full `/inputs` and `/skills` profile before production sizing.

## Rollback

Disable new admission and allow retained sessions to expire or explicitly delete their claims and PVCs under the operator runbook. Then return to one broker replica and the prior process-local profile. The earlier profile deletes its labeled claims at startup, so switching directly would lose retained workspaces.

## Limitations

The shared profile currently supports SIG Agent Sandbox only. It does not share a running sandbox between conversations or guarantee a cold-start target; node and CSI capacity must be measured on the target cluster.
