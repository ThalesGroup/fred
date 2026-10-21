## Context

The factory separates generic lifecycle commands from product-owned hooks. Fred has a `fred-app` release and optional `control-plane` release. Both use database `fred`; the factory PostgreSQL instance also hosts Keycloak, OpenFGA and Temporal. Python SQL migrations run as Helm hook Jobs, not merely when deployments restart.

## Goals / Non-Goals

Provide a bounded local reset with retained identities and installed images. Do not support production, arbitrary storage overlays, shared application environments, identity erasure, backup/restore, or a new deployment framework.

## Decisions

- Use one generic factory reset dispatch and one Fred-owned Python standard-library hook. Reuse kubectl, Helm, the installed PostgreSQL client and OpenSearch curl; no new maintenance image or dependency installer.
- Default to a read-only preview. `CONFIRM=reset` explicitly permits execution. All calls name the k3d context and namespace; never switch the current context. Verify the cluster is a local k3d cluster.
- Restrict the hook to the known factory local storage profile and the Fred releases. Refuse other application releases/workloads, autoscalers, active Jobs, unsupported endpoints and custom storage before stopping anything. The developer confirmed this dedicated-cluster restriction on 2026-10-15.
- Preserve Keycloak, foundation secrets, roles/passwords, infrastructure PVCs and observability. Recreate only Fred/tabular and Temporal databases; delete only Fred OpenFGA stores, indexes and content buckets. Keep OpenFGA's own database and service schema. Temporal restarts through its existing schema init containers and default namespace initialization.
- Stop Fred producers/workers, then Temporal, and wait for pod deletion before erasure. Re-run the installed Fred migration Job definitions before restarting applications, using their installed images and configuration. Restore original replica counts and wait for readiness; no Helm upgrade, image build/import or infrastructure release replacement.
- Save original replica counts and deployment identities in the existing ignored factory cache before stopping. Serialize locally per target within one factory checkout, across product checkouts. Concurrent deployments or control from multiple factory checkouts are unsupported. On failure, do not restart Fred against a partial reset; a retry verifies the same deployment identities and repeats idempotent cleanup. Never claim cross-store atomicity or rollback.

## Risks / Trade-offs

- Dedicated local data is deliberately lost on execution. Preview and an explicit confirmation value separate inspection from execution.
- An external process using the local service ports is outside Kubernetes inventory. The documented prerequisite is to stop local Fred processes; database recreation refuses remaining connections rather than forcing them away.
- Broad custom deployment support would require maintaining ownership rules for other products. This command refuses such setups.
- Real deletion cannot be verified on the user's cluster without separate authorization. Verify orchestration with command doubles, data operations on disposable services where available, and preview on the current cluster. Report the exact remaining live-reset validation separately.
