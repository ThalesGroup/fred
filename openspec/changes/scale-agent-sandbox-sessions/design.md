## Context

See `proposal.md`. The current `ConversationPool` and `OnDemandCapacity` hold state only in one Python process. Broker startup deletes all managed Kubernetes workloads, and shutdown disposes its leases. `/work` is an `emptyDir` (or Docker tmpfs). The SIG backend already owns a SandboxClaim and uses a zero-replica SandboxWarmPool; its controller provides pod suspension while retaining PVCs. Fred already deploys PostgreSQL for control-plane state, so a dedicated broker table does not introduce a new service.

## Goals / Non-Goals

**Goals:** Preserve conversation identity and `/work` across pod suspension and broker failover; admit no more running sandboxes or concurrent preparations than the operator limits; make the full-mount profile measurable before production sizing.

**Non-Goals:** Share a running sandbox across users, guarantee sub-second cold start, provision a cloud-provider node autoscaler from the Fred chart, checkpoint arbitrary process memory, or store submitted code in the coordinator.

## Decisions

1. **Shared coordinator backed by PostgreSQL.** Add one dedicated session table and one bounded wait-ticket table in a single Alembic migration. The broker uses a restricted database credential. A session row contains an opaque HMAC conversation key, a random workspace identity, state, activity deadlines, and the broker-owned resource reference; it contains no code or source bytes. Row locks serialize calls for one conversation. A short transaction under a global capacity lock reserves active and preparation slots before any Kubernetes object is created. Queue tickets are ordered by arrival, bounded globally and per tenant, and expire quickly. Other brokers may observe and resume a session after a crash. The existing in-process coordinator remains for one-replica Docker development. Alternative: Kubernetes Lease/ConfigMap objects for every request. Rejected because this would add significant API-server churn to the path we are trying to protect.

2. **Two lifecycle clocks.** The admin-controlled 20-minute inactivity period remains final expiry. A shorter operator-approved active-idle interval suspends the pod and releases active capacity; it does not revoke the conversation or delete `/work`. The next execution reserves capacity, resumes the workload and validates the admitted pod. Final expiry removes the claim, private workspace and input view. The idle cutoff applies only after the current code call finishes. A retained-conversation and storage quota bounds dormant PVC cost. Alternative: shorten the only timeout. Rejected because it would lose generated files during an ongoing conversation.

3. **Persistent workspace only in the scalable SIG profile.** An approved RWO PVC backs `/work`; `/tmp` remains bounded `emptyDir`. The read-only `/inputs` CSI claim and approved `/skills` volume keep their existing authorization path. The broker validates the expected PVC names, mounts and ownership before execution. SIG `Sandbox.spec.operatingMode` suspends and resumes the pod; the SandboxClaim stays until final expiry. Kubernetes Job and Docker backends keep their existing single-broker semantics until their workspace adapters implement the same contract; selecting shared suspension with either fails at startup. Alternative: copy scratch to an object store on every call. Rejected because it duplicates files and adds a new sensitive transfer path.

4. **No speculative pod pool.** The SIG pool stays at zero replicas. A dedicated autoscaled node group is an operator responsibility: the examples expose approved node placement and the guide requires per-RuntimeClass overhead measurements. Brokers may scale horizontally only when the shared coordinator is configured. Neither the broker nor admin UI may silently switch Kata to gVisor. Alternative: prewarm sandboxes. Rejected because it consumes resources before any user executes code.

5. **Bound Kubernetes API operations.** Admission caps simultaneous preparations separately from active sessions. Job readiness polling backs off rather than querying every 250 ms. SIG readiness uses the controller's condition wait. Observe admission wait, prepare/resume duration, active and suspended counts, API errors and cleanup lag. Maintain explicit fail-closed behavior for unavailable coordination or invalid template/storage profile.

## Risks / Trade-offs

- **A broker dies during execution** -> PostgreSQL releases its row lock; the next owner terminates stale code processes and revalidates the pod before reuse. Server-side SandboxClaim expiry remains a backstop.
- **Database outage** -> Shared-mode execution and view creation fail closed; existing guest workloads retain their server-side expiry. The local mode remains available only when explicitly selected.
- **Persistent scratch holds sensitive generated data** -> One PVC per conversation, restricted StorageClass, encryption at rest where available, quota, final deletion and no cross-conversation reuse. The storage driver must be validated for both gVisor and Kata.
- **Suspension frees pod requests but leaves PVC and control-plane objects** -> Separate retained-session quota and load tests include PVC, Secret and CRD counts.
- **Kata and gVisor have different overhead and filesystem behavior** -> No inferred common sizing; benchmark each approved profile with CSI and apply measured `RuntimeClass.overhead`.

## Migration Plan

1. Apply the one migration and create a least-privilege database credential for the broker. Existing deployments remain single-replica and unchanged by default.
2. Install the approved persistent StorageClass and update the SIG SandboxTemplate to mount `/work` from a conversation PVC. Verify suspend/resume, CSI and security admission on the target cluster.
3. Enable shared mode, bounded queue and optional broker replicas in the chart. Keep the active ceiling low until a 50/100/250/500/1,000 ramp with full mounts confirms node, CSI and API-server capacity.
4. Roll back by setting one broker replica and disabling new admission, allowing active sessions to expire or deleting their resources under the operator runbook. Never start the old recover-all logic while shared sessions exist.
