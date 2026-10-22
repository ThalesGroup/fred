# Fred sandbox broker prototype

The broker runs short Bash or Python programs in isolated Kata or gVisor workloads. Fred agent pods call its authenticated HTTPS API; only the broker has Kubernetes or Docker control credentials. One conversation keeps its assigned workload across executions, including files under `/tmp`, until 20 minutes after its last execution by default. Calls without a conversation identity remain single-use. A different conversation or user never receives that claimed workload. An optional pool holds unassigned, clean workloads to reduce first-use latency. Connected chat users who never run code consume no sandbox.

This prototype is for a controlled pilot. It has one broker replica and local admission accounting. It has no per-team quota, durable work queue, or session recovery after a broker restart. SIG claim shutdown times still clean up orphaned workloads. Docker and Job workloads have a 24-hour hard lifetime if the broker disappears, and a long-running conversation can lose its scratch files at that boundary. A cluster's CNI behavior, node virtualization support, image provenance, and actual first-execution latency require operator validation.

The [broker Dockerfile](Dockerfile) packages the trusted API service; it is not
the image that runs agent code and does not provide isolation. Agent code runs
in the separately pinned `SANDBOX_IMAGE`. Kata Containers or gVisor supplies
the execution boundary, while this prototype supplies admission and workload
lifecycle.

The optional `agent_sandbox` backend delegates Kubernetes lifecycle to the
[Kubernetes SIG Agent Sandbox controller](https://agent-sandbox.sigs.k8s.io/docs/)
using SandboxTemplate, SandboxClaim, and SandboxWarmPool resources. Kata remains
the preferred RuntimeClass where virtualization is available.
[NVIDIA OpenShell](https://docs.nvidia.com/openshell/latest/kubernetes/setup)
is a separate candidate when its network, filesystem, and process policies are
needed; its Kubernetes driver itself uses Agent Sandbox and requires a CNI that
enforces NetworkPolicy. OpenShell is not integrated here.

## Configuration

| Variable | Purpose |
| --- | --- |
| `SANDBOX_BACKEND` | `kubernetes`, `agent_sandbox`, or `docker` |
| `SANDBOX_AGENT_POOL_NAME` | SandboxWarmPool name for `agent_sandbox`, default `fred-code` |
| `SANDBOX_ISOLATION` | `kata` or `gvisor` |
| `SANDBOX_RUNTIME_NAME` | Exact RuntimeClass or Docker runtime name |
| `SANDBOX_IMAGE` | Approved Python image pinned as `name@sha256:<64 hex chars>` and containing Bash |
| `SANDBOX_BROKER_TOKEN` | Random token of at least 32 characters |
| `SANDBOX_MAX_SANDBOXES` | Operator cap on broker-managed prepared plus active workloads, default 8; with SIG Agent Sandbox, upstream warm replicas are additional |
| `SANDBOX_WARM_POOL_SIZE` | Ready workloads held before requests, default 0 |
| `SANDBOX_COLD_START_ON_MISS` | Provision on demand when no ready workload exists, default `true` |
| `SANDBOX_EXECUTION_TIMEOUT` | Per-call deadline in seconds, default 15 |
| `SANDBOX_OUTPUT_LIMIT_BYTES` | Limit for each stdout/stderr stream, default 8192 |
| `SANDBOX_IDLE_TIMEOUT` | Conversation inactivity expiry in seconds, default 1200 |
| `SANDBOX_SETTINGS_URL` | Optional HTTPS control-plane internal sandbox settings endpoint |
| `SANDBOX_SETTINGS_TOKEN` | Separate 32+ character service token for that endpoint |
| `SANDBOX_NETWORK_POLICY_VERIFIED` | Kubernetes only: set `true` after the CNI probe below |
| `SANDBOX_PID_LIMIT_VERIFIED` | Kubernetes only: set `true` after checking a finite kubelet `podPidsLimit` on every eligible node |

The agent pod needs `FRED_SANDBOX_BROKER_URL`, `FRED_SANDBOX_BROKER_TOKEN`, and a trusted CA for the broker certificate. The URL must use HTTPS unless it points to loopback. Its tool schema contains only `language` and `code`; the runtime derives an opaque session key from user, team and conversation identity. Never put credentials in code. Grant the capability to a team through Fred's normal admin gate. The capability remains unavailable without a configured broker. Each execution starts a fresh Bash or Python process, so files persist within a conversation but interpreter variables do not.

### Platform admin controls

The Capabilities page shows only three sandbox settings: inactivity expiry (1-120 minutes, default 20), maximum active conversations, and clean ready capacity. It displays the operator-approved profile ID as read-only. Images, runtime classes, network policy and resource restrictions stay in deployment configuration. The settings live in the control-plane `sandbox_settings` singleton table, separate from UI theme settings because they govern execution lifecycle and capacity.

To apply admin changes without redeploying, configure the control plane with `FRED_SANDBOX_SETTINGS_TOKEN` and set `FRED_SANDBOX_PROFILE_ID` to the actual operator-approved profile name, then configure the broker with `SANDBOX_SETTINGS_URL=https://<control-plane>/control-plane/v1/internal/sandbox-settings` and the same token as `SANDBOX_SETTINGS_TOKEN`. Use a separate secret from the execution bearer token and a trusted TLS CA. The broker refreshes every 30 seconds, retains its last valid settings if the control plane is temporarily unavailable, and clamps active and ready capacity to `SANDBOX_MAX_SANDBOXES`. One broker replica remains required because conversation leases and active admission are in memory. The SIG controller owns additional unassigned warm replicas; total running sandboxes can be active claims plus warm replicas. Set both ceilings to fit the namespace quota and node budget.

For the Kubernetes example, create `fred-sandbox-settings` in `fred-sandbox-system` and `control-plane-sandbox-settings` in the control-plane namespace, each with the same `token` key and value. The Fred chart references the second Secret optionally; restart the control-plane Deployment after creating it so the token enters its environment. Set the HTTPS control-plane host in [admin-settings.patch.yaml](../../deploy/sandbox/admin-settings.patch.yaml), then apply the strategic merge patch with `kubectl -n fred-sandbox-system patch deployment fred-sandbox-broker --type strategic --patch-file deploy/sandbox/admin-settings.patch.yaml`. The control-plane TLS certificate must cover that host, and the broker must trust its CA. This one-time wiring enables later settings changes without a rollout. A zero warm capacity requires `SANDBOX_COLD_START_ON_MISS=true`; a strict-ready broker ignores that warm setting while applying idle and active limits.

## Kubernetes pilot

1. Install Kata or gVisor on selected nodes and create a RuntimeClass whose handler selects that runtime. For Kata, verify KVM access and node scheduling; for gVisor, verify `runsc` is installed on scheduled nodes. Pre-pull the approved image to reduce cold start time. `kubectl get runtimeclass <name> -o jsonpath='{.handler}'` must show the intended handler. Where the installed Kata implementation supports it, evaluate QEMU VM templating on the sandbox nodes; it accelerates VM creation without keeping sandbox Pods alive. Validate the exact Kata runtime and configuration before enabling it.
2. Review [kubernetes.yaml](../../deploy/sandbox/kubernetes.yaml), set the broker image, pinned execution image, runtime name, and pool size. Create `fred-sandbox-broker-auth` (key `token`) and `fred-sandbox-broker-tls` in `fred-sandbox-system`. Write the token without a trailing newline (`printf`, not `echo`) so it can be sent as an HTTP bearer value. The TLS certificate must cover `fred-sandbox-broker.fred-sandbox-system.svc` and its private key must be readable by group 65532. Keep both verification flags `false` for this first deployment.
3. Apply the manifest. Verify that the `fred-sandbox` namespace enforces Pod Security Restricted and has exactly one NetworkPolicy, `fred-sandbox-deny-all`, selecting every pod for both ingress and egress. Kubernetes policies are additive: an additional allow policy can reopen traffic. Restrict changes to this namespace with RBAC or admission policy so the deny policy cannot be removed or supplemented after broker startup. The broker checks the policy set at startup, but its existence alone does not prove the CNI enforces it.
4. Probe the CNI with a temporary pod in `fred-sandbox` using the selected RuntimeClass, the same non-root security context, and CPU/memory requests and limits required by the namespace quota. Choose a controlled reachable IP and port. Apply a temporary egress policy selecting only that probe pod and allowing that target; verify a TCP connection succeeds. Remove the temporary allow policy and verify the same connection fails. Delete the probe pod. A failure in both phases is inconclusive. Repeat on every sandbox node pool and after CNI changes.
5. Check the kubelet configuration on every node that can host a sandbox: `podPidsLimit` must be finite and positive. Set `SANDBOX_PID_LIMIT_VERIFIED=true` only after this check and keep node admission restricted to those nodes. Pod specifications cannot set a PID limit themselves.
6. Set `SANDBOX_NETWORK_POLICY_VERIFIED=true` only after the probe, then restart the broker. With the default pool size of zero, startup creates no sandbox Pods; each call provisions a Job on demand. Configure the agent pod with the HTTPS URL and token through `extraEnvVars` and mount the broker CA with `extraVolumes` / `extraVolumeMounts` in the `agent-pod` Helm chart. Set `SSL_CERT_FILE` to that CA path if needed. Do not mount a Kubernetes token in the agent pod.

The broker service account can create and delete Jobs, read Pods and list policies, and execute in Pods only in `fred-sandbox`; it can read RuntimeClasses and the namespace object cluster-wide. Kubernetes 1.31+ WebSocket exec can use GET, so the RBAC grants both `get` and `create` on `pods/exec`. The Job has `activeDeadlineSeconds` and TTL cleanup as backstops if the broker dies.

### SIG Agent Sandbox backend

Install the pinned upstream v1.0.6 `sandbox-with-extensions.yaml` release in the cluster, then apply [agent-sandbox.yaml](../../deploy/sandbox/agent-sandbox.yaml) after replacing the image digest and selecting the approved RuntimeClass. Keep the dedicated namespace and deny-all NetworkPolicy from `kubernetes.yaml`. The template deliberately sets `networkPolicyManagement: Unmanaged`: the upstream managed default permits public internet egress, while this backend requires no network path. Verify CNI enforcement and pod PID limits as above before setting the two attestation flags. Keep template and pool writes restricted to cluster operators.

Set `SANDBOX_BACKEND=agent_sandbox`, `SANDBOX_AGENT_POOL_NAME=fred-code`, and `SANDBOX_WARM_POOL_SIZE=0` on the broker; the latter disables its own pool. Scale `SandboxWarmPool.spec.replicas` from zero for ready capacity, or connect the admin settings feed to scale it dynamically. For strict ready measurements, set `SANDBOX_COLD_START_ON_MISS=false`; the broker checks the upstream pool and rejects any claim that the controller labels as a cold fallback. Production deployments that permit zero warm capacity should keep cold fallback enabled. `SANDBOX_MAX_SANDBOXES` caps active claims per broker process; idle upstream warm replicas are additional resources. Run one broker replica until admission is coordinated across replicas. The broker checks the namespace policy and template before every claim, then validates the claimed Pod's runtime, image, credentials, mounts and restrictions before exec. A claim is retained for its conversation, its shutdown time is renewed after executions, and deletion uses foreground cascading after idle expiry.

## Docker or local pilot

Run the broker on a dedicated host with a Docker daemon configured with Kata or gVisor, or use [docker-compose.yaml](../../deploy/sandbox/docker-compose.yaml) against a dedicated TLS Docker daemon. Never mount the Docker socket into a Fred agent pod. `docker info --format '{{json .Runtimes}}'` must show the configured runtime backed by the expected Kata or `runsc` binary. Pre-pull the pinned execution image on that daemon; pool preparation uses `--pull never`.

For local host execution, install this package and its dependencies, set the variables above, and start `uvicorn sandbox_broker.main:app --host 127.0.0.1 --port 8443` with a local certificate or reverse proxy. The Docker backend uses `--runtime`, `--network none`, read-only root, non-root UID, dropped capabilities, bounded resources, and `--rm`; a conversation lease is forcibly removed at idle expiry. The broker's Docker control access is effectively host-admin access, so isolate its daemon from Fred and other workloads.

## Latency and cost

On-demand mode provisions a Job, SandboxClaim, or Docker container on the first code call in a conversation, then retains it until idle expiry. Kubernetes scheduling, image preparation, and VM startup all contribute to this cold path; a fast VM alone does not imply a fast first call. Run [benchmark.py](../../deploy/sandbox/benchmark.py) with `--mode cold` on the actual cluster, using `FRED_SANDBOX_BROKER_URL` and `FRED_SANDBOX_BROKER_TOKEN`. The script takes at least 20 sequential one-shot samples and reports p50 and p95 broker request-to-result latency. For the Job or Docker backend, set `SANDBOX_WARM_POOL_SIZE` to the smallest useful value; for Agent Sandbox, set `SandboxWarmPool.spec.replicas` instead. Set `SANDBOX_COLD_START_ON_MISS=false` during the ready-path measurement, then rerun with `--mode ready`. This avoids labeling a concurrent cold fallback as a ready sample. A retained conversation workload executes through `kubectl exec` or `docker exec` without VM creation or a new SIG claim. Excess calls receive retryable `busy` at the configured cap. Compare latency with idle VM cost and burst rejection before choosing a configuration. A pool of 8 Kata VMs is a fixed idle cost for a platform with 2,000 connected users; zero warm Pods avoid that idle VM cost. This pilot uses one broker replica because its cap and session map are process-local.

Code is visible in process arguments and Kubernetes Pod exec requests to administrators with sufficient access. Do not send secrets in source. Untrusted code output is returned as data, never as platform instructions.
If the agent disconnects after submission, execution may continue until the configured deadline before cleanup. Cancelling the broker request task triggers immediate cleanup. A disconnect during cold provisioning may still complete the bounded preparation step before cleanup.

### k3d comparison (2026-10-22)

The same k3d cluster (Kubernetes 1.31.5), gVisor RuntimeClass, preloaded Python 3.12 image and broker request-to-result script produced 30 sequential samples per mode after the mandatory post-execution process sweep was added. Ready mode used one idle workload and disabled cold fallback. These are local measurements, not an s3ns or Kata result.

| Lifecycle | Cold p50 / p95 | Ready p50 / p95 |
| --- | --- | --- |
| Broker-managed Kubernetes Job | 1.974s / 2.162s | 0.516s / 0.629s |
| SIG Agent Sandbox v1.0.6 claim and warm pool | 1.858s / 2.836s | 1.687s / 1.913s |

Once a SIG claim was retained for its conversation, 30 further sequential calls measured 0.484s p50 and 0.615s p95 on the same k3d cluster. The sweep adds one more exec command per call and discards a workload if a detached process, zombie, or cleanup failure is detected.

The SIG controller owns the warm Pod and replenishes it after a claim. The ready path includes policy, template, Pod and upstream warm-label checks before execution. Those checks and claim reconciliation appear to add latency in this setup; this is an inference from the path and measured times, not a component-level trace. Measure again on the intended cluster and selected RuntimeClass before setting an SLO or pool size.
