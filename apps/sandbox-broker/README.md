# Fred sandbox broker prototype

For a production cluster, follow the [step-by-step Kubernetes installation guide](../../docs/swift/ops/AGENT_SANDBOX_KUBERNETES.md). This README remains the configuration and backend reference.

The broker runs short Bash or Python programs in isolated Kata or gVisor workloads. Fred agent pods call its authenticated HTTPS API; only the broker has Kubernetes or Docker control credentials. The first code execution creates a workload on demand. One conversation keeps its assigned workload across executions, including files under `/work`, until 20 minutes after its last execution by default. Calls without a conversation identity remain single-use. A different conversation or user never receives that claimed workload. Connected chat users who never run code consume no sandbox.

This prototype is for a controlled pilot. It has one broker replica and local admission accounting. It has no per-team quota, durable work queue, or session recovery after a broker restart. On restart, the broker removes its prior labeled Kubernetes or Docker workloads and mount resources before serving requests; SIG claim shutdown times provide a separate upper bound if it does not restart. Docker workloads have a 24-hour hard lifetime if the broker disappears. A cluster's CNI behavior, node virtualization support, image provenance, and actual first-execution latency require operator validation.

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
| `SANDBOX_MAX_SANDBOXES` | Operator cap on active workloads, default 8 |
| `SANDBOX_EXECUTION_TIMEOUT` | Per-call deadline in seconds, default 15 |
| `SANDBOX_OUTPUT_LIMIT_BYTES` | Limit for each stdout/stderr stream, default 8192 |
| `SANDBOX_IDLE_TIMEOUT` | Conversation inactivity expiry in seconds, default 1200 |
| `SANDBOX_SETTINGS_URL` | Optional HTTPS control-plane internal sandbox settings endpoint |
| `SANDBOX_SETTINGS_TOKEN` | Separate 32+ character service token for that endpoint |
| `SANDBOX_NETWORK_POLICY_VERIFIED` | Kubernetes only: set `true` after the CNI probe below |
| `SANDBOX_PID_LIMIT_VERIFIED` | Kubernetes only: set `true` after checking a finite kubelet `podPidsLimit` on every eligible node |
| `SANDBOX_MOUNT_PROVIDER` | Optional file mount: `none` (default), `rclone_csi` on Kubernetes, or `rclone_docker` on Docker |
| `SANDBOX_FILE_GATEWAY_URL` | HTTPS Knowledge Flow URL ending in `/sandbox-mount`, reachable from CSI nodes or the Docker host |
| `SANDBOX_FILE_GATEWAY_SECRET` | Shared 32+ character secret for per-workload mount credentials and revocation |
| `SANDBOX_FILE_STORAGE_CLASS` | Approved CSI StorageClass name for `rclone_csi` |
| `SANDBOX_DOCKER_VOLUME_PLUGIN` | Enabled, approved Docker volume plugin name for `rclone_docker` |
| `SANDBOX_SKILLS_VOLUME` | Optional approved PVC name (Kubernetes) or Docker volume name mounted read-only at `/skills` |

The agent pod needs `FRED_SANDBOX_BROKER_URL`, `FRED_SANDBOX_BROKER_TOKEN`, and a trusted CA for the broker certificate. The URL must use HTTPS unless it points to loopback. Its tool schema contains only `language` and `code`; the runtime derives an opaque session key from user, team and conversation identity. Never put credentials in code. Grant the capability to a team through Fred's normal admin gate. The capability remains unavailable without a configured broker. Each execution starts a fresh Bash or Python process, so files persist within a conversation but interpreter variables do not.

### Platform admin controls

The Capabilities page shows two sandbox settings: inactivity expiry (1-120 minutes, default 20) and maximum active conversations. It displays the operator-approved profile ID as read-only. Images, runtime classes, network policy and resource restrictions stay in deployment configuration. The settings live in the control-plane `sandbox_settings` singleton table, separate from UI theme settings because they govern execution lifecycle and capacity.

To apply admin changes without redeploying, configure the control plane with `FRED_SANDBOX_SETTINGS_TOKEN` and set `FRED_SANDBOX_PROFILE_ID` to the actual operator-approved profile name, then configure the broker with `SANDBOX_SETTINGS_URL=https://<control-plane>/control-plane/v1/internal/sandbox-settings` and the same token as `SANDBOX_SETTINGS_TOKEN`. Use a separate secret from the execution bearer token and a trusted TLS CA. The broker refreshes every 30 seconds, retains its last valid settings if the control plane is temporarily unavailable, and clamps active capacity to `SANDBOX_MAX_SANDBOXES`. One broker replica remains required because conversation leases and active admission are in memory. The SIG pool remains at zero replicas. Size the active ceiling to fit the namespace quota and node budget.

For the Kubernetes example, create `fred-sandbox-settings` in `fred-sandbox-system` and `control-plane-sandbox-settings` in the control-plane namespace, each with the same `token` key and value. The Fred chart references the second Secret optionally; restart the control-plane Deployment after creating it so the token enters its environment. Set the HTTPS control-plane host in [admin-settings.patch.yaml](../../deploy/sandbox/admin-settings.patch.yaml), then apply the strategic merge patch with `kubectl -n fred-sandbox-system patch deployment fred-sandbox-broker --type strategic --patch-file deploy/sandbox/admin-settings.patch.yaml`. The control-plane TLS certificate must cover that host, and the broker must trust its CA. This one-time wiring enables later settings changes without a rollout. All workloads are provisioned on demand.

## Kubernetes pilot

1. Install Kata or gVisor on selected nodes and create a RuntimeClass whose handler selects that runtime. For Kata, verify KVM access and node scheduling; for gVisor, verify `runsc` is installed on scheduled nodes. Pre-pull the approved image to reduce cold start time. `kubectl get runtimeclass <name> -o jsonpath='{.handler}'` must show the intended handler. Where the installed Kata implementation supports it, evaluate QEMU VM templating on the sandbox nodes; it accelerates VM creation without keeping sandbox Pods alive. Validate the exact Kata runtime and configuration before enabling it.
2. Review [kubernetes.yaml](../../deploy/sandbox/kubernetes.yaml), set the broker image, pinned execution image, runtime name, and active capacity limit. Create `fred-sandbox-broker-auth` (key `token`) and `fred-sandbox-broker-tls` in `fred-sandbox-system`. Write the token without a trailing newline (`printf`, not `echo`) so it can be sent as an HTTP bearer value. The TLS certificate must cover `fred-sandbox-broker.fred-sandbox-system.svc` and its private key must be readable by group 65532. Keep both verification flags `false` for this first deployment.
3. Apply the manifest. Verify that the `fred-sandbox` namespace enforces Pod Security Restricted and has exactly one NetworkPolicy, `fred-sandbox-deny-all`, selecting every pod for both ingress and egress. Kubernetes policies are additive: an additional allow policy can reopen traffic. Restrict changes to this namespace with RBAC or admission policy so the deny policy cannot be removed or supplemented after broker startup. The broker checks the policy set at startup, but its existence alone does not prove the CNI enforces it.
4. Probe the CNI with a temporary pod in `fred-sandbox` using the selected RuntimeClass, the same non-root security context, and CPU/memory requests and limits required by the namespace quota. Choose a controlled reachable IP and port. Apply a temporary egress policy selecting only that probe pod and allowing that target; verify a TCP connection succeeds. Remove the temporary allow policy and verify the same connection fails. Delete the probe pod. A failure in both phases is inconclusive. Repeat on every sandbox node pool and after CNI changes.
5. Check the kubelet configuration on every node that can host a sandbox: `podPidsLimit` must be finite and positive. Set `SANDBOX_PID_LIMIT_VERIFIED=true` only after this check and keep node admission restricted to those nodes. Pod specifications cannot set a PID limit themselves.
6. Set `SANDBOX_NETWORK_POLICY_VERIFIED=true` only after the probe, then restart the broker. Startup creates no sandbox Pods; the first execution in a conversation provisions a Job on demand. Configure the agent pod with the HTTPS URL and token through `extraEnvVars` and mount the broker CA with `extraVolumes` / `extraVolumeMounts` in the `agent-pod` Helm chart. Set `SSL_CERT_FILE` to that CA path if needed. Do not mount a Kubernetes token in the agent pod.

The broker service account can create and delete Jobs, read Pods and list policies, and execute in Pods only in `fred-sandbox`; it can read RuntimeClasses and the namespace object cluster-wide. Kubernetes 1.31+ WebSocket exec can use GET, so the RBAC grants both `get` and `create` on `pods/exec`. The Job has `activeDeadlineSeconds` and TTL cleanup as backstops if the broker dies.

### Optional read-only conversation files

The file mount is opt-in. With the mount provider set to `none`, existing code execution and all ordinary skill, corpus, attachment, and tabular tools keep their current behavior. To enable it, configure the same `SANDBOX_FILE_GATEWAY_SECRET` in Knowledge Flow and the broker, and set it as `FRED_SANDBOX_FILE_GATEWAY_SECRET` in the trusted agent runtime. The runtime signs a conversation view request before the first `execute_code`; the secret is never passed to guest code. Set `FRED_SANDBOX_FILE_MOUNTS_ENABLED=true` only after the gateway and mount provider are ready. The sandbox then lists authorized team or personal corpus documents under `/inputs/corpus` and the current conversation attachments under `/inputs/attachments`, without a separate model tool. Knowledge Flow checks the user's scope on each listing and read. A newly added file appears in the existing sandbox after the configured 1-second rclone directory cache refresh. The sandbox still starts only on the first code execution.

Knowledge Flow verifies the authenticated account, persisted conversation owner and team, source authorization, and attachment uploader before binding and on subsequent reads. A personal conversation sees only document libraries owned by that user; a team conversation sees only document libraries owned by that team. The corpus is browsed in 128-candidate pages under `/inputs/corpus/libraries/<library-id>/pages/block-XX/block-XX`, with fixed block levels that bound each directory listing; only attachments in the current conversation appear under `/inputs/attachments`. The mount exposes authorized originals, never the entire corpus bucket. New conversation attachments retain their original object in private content storage for this use; legacy attachments without an original remain available through existing tools but cannot be mounted. A single file is limited to 20 MiB, attachments to 32 files, and a view to 100 MiB of reads and 600 WebDAV requests per minute. The gateway supports read-only WebDAV with ranged reads and fails closed when ReBAC is disabled. Broker disposal revokes its per-workload credential and deletes the workload. An active view refreshes its expiry as it is read, with a 130-minute inactivity backstop if the broker disappears.

For Kubernetes, install and review an operator-approved [rclone CSI driver](https://github.com/veloxpack/csi-driver-rclone) with FUSE support on every eligible node. It runs privileged node-level components, so treat installation as a cluster administration action. Apply [rclone-webdav-storageclass.yaml](../../deploy/sandbox/rclone-webdav-storageclass.yaml) and [file-mount-rbac.yaml](../../deploy/sandbox/file-mount-rbac.yaml) after checking the namespace and driver version. The broker preflight accepts only that exact provisioner, per-PVC node-publish Secret reference, `dir-cache-time=1s`, `vfs-cache-mode=off`, no other mount options, and `Delete` reclaim policy. Use [file-mount-broker.patch.yaml](../../deploy/sandbox/file-mount-broker.patch.yaml) to configure the broker; replace the gateway URL and set the matching Knowledge Flow secret. The CSI controller and node driver must trust the gateway's certificate. If the read-only TLS gateway rejects DELETE, set `SANDBOX_FILE_GATEWAY_REVOKE_URL` to a trusted internal Knowledge Flow mount endpoint for broker-only view revocation. Internal HTTP is accepted only for a Kubernetes Service DNS name ending in `.svc.cluster.local`; use TLS when available. The guest never reaches this endpoint. Mount `/inputs` read-only in the guest, and verify it with `findmnt /inputs` plus a denied write attempt. For the SIG backend, apply [agent-sandbox-files.yaml](../../deploy/sandbox/agent-sandbox-files.yaml) and keep its pool at zero replicas. The broker creates a distinct Secret and PVC per workload; neither credential is mounted in the guest. Kata and gVisor each require a real volume test on the target cluster before this profile is approved.

For Docker, install the [rclone volume plugin](https://rclone.org/docker/) on the isolated Docker host, verify it is enabled, and configure `rclone_docker`. The broker creates a unique WebDAV volume per workload and mounts it read-only at `/inputs`. The per-view bearer is sent to the trusted Docker daemon as a volume option, so keep Docker API access restricted and avoid command-line logging of volume options. The Docker host and plugin must trust the gateway's certificate. Do not use a host-path or raw bucket mount for this feature.

### Optional platform skill scripts

The runtime accepts UTF-8 `.py` and `.sh` files inside a validated platform skill, subject to the existing 64 KiB per-file and 4 MiB catalog limits. An unsafe script is omitted without removing the skill's Markdown instructions. Its normal skill tools still work with no sandbox. An agent running a script must be granted `code_sandbox`, and the skill instructions should state that requirement. ReAct and Deep can call the capability's `execute_code` tool; Deep's native `execute` remains disabled because its conversation scratchpad is not the guest's `/work`. The sandbox starts only at the first execution. Scripts can refer to authorized `/inputs` files and write temporary results to `/work`.

To expose script paths in the guest, publish only common platform scripts approved for every agent with `code_sandbox` to an operator-owned volume. Set `SANDBOX_SKILLS_VOLUME` to an approved, already Bound PVC in `fred-sandbox` with `ReadOnlyMany` or `ReadWriteMany` and label `fred.sandbox/skills=approved`, or to an existing Docker volume with that label. The broker mounts it read-only at `/skills`; it never mounts the agent pod's filesystem or a host path. Configure the agent runtime's `skills.directory` to a read-only mount of the same approved source so `/` and the sandbox use the same files. Kubernetes PVCs are namespaced: if the source is external, create a separate agent-namespace mount of that source, and a sandbox-namespace PVC for the broker. Do not publish a copied ConfigMap of packaged skills as a second source. The runtime currently snapshots skill metadata at startup, so a newly added source skill becomes visible to `/` after an agent pod restart; the guest sees it after the CSI directory cache refresh. The volume label attests operator approval of the whole volume, not equality with Fred's filtered skill catalog. Keep private, rejected and user or team scoped files off the published volume. For SIG, use [agent-sandbox-skills.yaml](../../deploy/sandbox/agent-sandbox-skills.yaml) for skills alone or [agent-sandbox-files-skills.yaml](../../deploy/sandbox/agent-sandbox-files-skills.yaml) for skills and inputs. Replace the PVC and image placeholders, set the matching `SANDBOX_AGENT_POOL_NAME`, and retain a zero-replica pool. Guest read-only mounts do not prevent code from copying readable bytes into its own scratch. User-authored skill publishing is not provided by this profile.

### SIG Agent Sandbox backend

Install the pinned upstream v1.0.6 `sandbox-with-extensions.yaml` release in the cluster, then apply [agent-sandbox.yaml](../../deploy/sandbox/agent-sandbox.yaml) after replacing the image digest and selecting the approved RuntimeClass. Keep the dedicated namespace and deny-all NetworkPolicy from `kubernetes.yaml`. The template deliberately sets `networkPolicyManagement: Unmanaged`: the upstream managed default permits public internet egress, while this backend requires no network path. Verify CNI enforcement and pod PID limits as above before setting the two attestation flags. Keep template and pool writes restricted to cluster operators.

Set `SANDBOX_BACKEND=agent_sandbox` and `SANDBOX_AGENT_POOL_NAME=fred-code` on the broker. Keep `SandboxWarmPool.spec.replicas` at zero; the upstream claim API still requires the object, and the broker rejects positive replicas. `SANDBOX_MAX_SANDBOXES` caps active claims per broker process. Run one broker replica until admission is coordinated across replicas. The broker checks the namespace policy and template before every claim, then validates the claimed Pod's runtime, image, credentials, mounts and restrictions before exec. A claim is retained for its conversation, its shutdown time is renewed after executions, and deletion uses foreground cascading after idle expiry.

## Docker or local pilot

Run the broker on a dedicated host with a Docker daemon configured with Kata or gVisor, or use [docker-compose.yaml](../../deploy/sandbox/docker-compose.yaml) against a dedicated TLS Docker daemon. Never mount the Docker socket into a Fred agent pod. `docker info --format '{{json .Runtimes}}'` must show the configured runtime backed by the expected Kata or `runsc` binary. Pre-pull the pinned execution image on that daemon; on-demand preparation uses `--pull never`.

For local host execution, install this package and its dependencies, set the variables above, and start `uvicorn sandbox_broker.main:app --host 127.0.0.1 --port 8443` with a local certificate or reverse proxy. The Docker backend uses `--runtime`, `--network none`, read-only root, non-root UID, dropped capabilities, bounded resources, and `--rm`; a conversation lease is forcibly removed at idle expiry. The broker's Docker control access is effectively host-admin access, so isolate its daemon from Fred and other workloads.

## Latency and cost

On-demand mode provisions a Job, SandboxClaim, or Docker container on the first code call in a conversation, then retains it until idle expiry. Kubernetes scheduling, image preparation, and VM startup all contribute to this cold path; a fast VM alone does not imply a fast first call. Run [benchmark.py](../../deploy/sandbox/benchmark.py) with `--mode cold` on the actual cluster, using `FRED_SANDBOX_BROKER_URL` and `FRED_SANDBOX_BROKER_TOKEN`. The script takes at least 20 sequential one-shot samples and reports p50 and p95 broker request-to-result latency. Use `--mode reuse` to measure later executions in one retained conversation. A retained conversation workload executes through `kubectl exec` or `docker exec` without VM creation or a new SIG claim. Excess calls receive retryable `busy` at the configured cap. Compare cold latency with the cost of retaining only active conversation workloads until expiry. This pilot uses one broker replica because its cap and session map are process-local.

Code is visible in process arguments and Kubernetes Pod exec requests to administrators with sufficient access. Do not send secrets in source. Untrusted code output is returned as data, never as platform instructions.
If the agent disconnects after submission, execution may continue until the configured deadline before cleanup. Cancelling the broker request task triggers immediate cleanup. A disconnect during cold provisioning may still complete the bounded preparation step before cleanup.

### k3d comparison (2026-10-22)

The same k3d cluster (Kubernetes 1.31.5), gVisor RuntimeClass, pre-pulled Python 3.12 image and broker request-to-result script produced 30 sequential samples per mode after the mandatory post-execution process sweep was added. The ready-mode measurements predate removal of ready capacity. These are historical local measurements, not a current configuration or an s3ns or Kata result.

| Lifecycle | Cold p50 / p95 | Ready p50 / p95 |
| --- | --- | --- |
| Broker-managed Kubernetes Job | 1.974s / 2.162s | 0.516s / 0.629s |
| SIG Agent Sandbox v1.0.6 claim and warm pool | 1.858s / 2.836s | 1.687s / 1.913s |

Once a SIG claim was retained for its conversation, 30 further sequential calls measured 0.484s p50 and 0.615s p95 on the same k3d cluster. The sweep adds one more exec command per call and discards a workload if a detached process, zombie, or cleanup failure is detected.

The historical ready path included policy, template, Pod and upstream warm-label checks. Measure the on-demand path again on the intended cluster and selected RuntimeClass before setting an SLO.
