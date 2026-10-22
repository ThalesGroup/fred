---
schema: 1
title: "Add isolated conversation code sandboxes"
impact: minor
configuration: production
configuration_reason: "The Fred chart adds an optional sandbox settings token Secret reference and an approved profile label; sandbox broker deployment requires operator-selected runtime, image, TLS and isolation settings."
---
## Applicability

Fred deployments upgrading the control plane and optionally enabling the code sandbox capability.

## Prerequisites

No action is required for deployments that leave code execution disabled. To enable it, select and verify a Kata or gVisor runtime on sandbox nodes, a CNI that enforces NetworkPolicy, finite kubelet pod PID limits, and an approved pinned Python/Bash image. Install SIG Agent Sandbox v1.0.6 only if using that backend. Follow the CNI probe and runtime checks in `apps/sandbox-broker/README.md` before setting broker verification flags.

## Configuration

The Fred chart now references `control-plane-sandbox-settings` key `token` in the control-plane namespace with `optional: true`. Its absence leaves the internal settings endpoint disabled. The chart sets `FRED_SANDBOX_PROFILE_ID=unconfigured`; set it to the exact operator-approved profile identifier when enabling code execution. For live admin settings, create that Secret with a random 32+ character token, create `fred-sandbox-settings` with the same token in `fred-sandbox-system`, then configure the broker's HTTPS settings URL and token using `deploy/sandbox/admin-settings.patch.yaml`. Use a different token for the broker execution API. The control-plane certificate must cover the settings URL and the broker must trust its CA. There is no default network access from the sandbox namespace.

The operator configures the broker's backend (`kubernetes`, `agent_sandbox`, or `docker`), isolation (`kata` or `gvisor`), runtime name, image digest, maximum sandbox count, network and PID verification flags, and TLS credentials. The two admin controls are conversation idle expiry (default 20 minutes) and active conversation cap. The broker clamps active capacity to its operator cap and provisions workloads only on demand. These values do not permit changing the runtime, image, or network policy from the admin UI.

## Upgrade

Run the normal control-plane Alembic upgrade before starting the new control-plane image; revision `d0a1b2c3d4e5` adds one `sandbox_settings` singleton table with defaults. No backfill is needed. Deploy the frontend and control plane, then, if enabling code execution, deploy the dedicated sandbox namespaces, policies and broker. Restart the control-plane Deployment after creating the optional token Secret, then apply the broker settings patch. Later admin changes are polled within 30 seconds without a rollout. Grant the code sandbox capability only to approved teams.

## Validation

Confirm the admin Capabilities page shows the approved profile and 20-minute default. Save a different idle expiry and verify `/healthz` on the broker reflects it within 30 seconds. Run Bash to create a file under `/tmp`, read it with Python in the same conversation, and confirm a second conversation cannot read it. Check `kubectl -n fred-sandbox get sandboxclaims,sandboxwarmpools,pods` when using SIG Agent Sandbox. A cluster with no code calls should have no sandbox workloads. The SIG pool must stay at zero replicas.

## Rollback

Disable the capability gate, stop new code calls, and let active conversations expire or delete their workloads before removing the broker. Roll back the frontend and control plane using the usual deployment procedure. The previous control-plane version ignores the new table; downgrading Alembic to `c9acb7dd3ad0` removes it and discards saved sandbox settings. Remove the dedicated sandbox resources and token Secrets after the broker has stopped. Conversation scratch files are temporary and are not recoverable after workload deletion.

## Limitations

This pilot uses one broker replica with process-local admission and session state. A broker restart loses conversation leases; SIG claim shutdown times and Job/Docker hard lifetimes clean up orphaned workloads. The measured k3d gVisor latency is not a Kata or production SLO. Operators must size namespace quota and node capacity for active claims only.
