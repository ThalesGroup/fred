# Agent code sandbox on Kubernetes

This is the operator path for a production cluster. The [broker README](../../../apps/sandbox-broker/README.md) is the configuration reference; the manifests under `deploy/sandbox/` are examples to review and adapt, not a certified profile for every cluster. Start with code execution, then enable the optional read-only `/inputs` mount after validating the storage path on the chosen runtime.

## 1. Choose the isolation profile and assign ownership

| Component | Role | Protection and boundary |
| --- | --- | --- |
| Fred `code_sandbox` capability and runtime adapter | Offer `execute_code` and optional `select_code_input`; bind calls to the current user, team and conversation. | Keep broker credentials and deployment choices out of model tool arguments. This interface does not isolate a process. |
| Fred sandbox broker | Authenticate calls, create on demand, retain one workload per executing conversation, and expire it after inactivity. | Keep Kubernetes or Docker control credentials outside the guest; bound execution time, output and active capacity. Protect the broker and its bearer token as trusted control components. |
| Kubernetes Job or SIG Agent Sandbox | Create and dispose of Pods. SIG reconciles `SandboxTemplate`, `SandboxClaim` and `SandboxWarmPool`; keep pool replicas at zero for this profile. | Enforce lifecycle and approved templates. Neither backend isolates syscalls or closes network access by itself. |
| Kata Containers RuntimeClass | Start a lightweight VM for each Pod, with its own guest kernel. | Separate guest kernel execution from the host kernel. Validate KVM, the actual handler and CSI volumes on eligible nodes. |
| gVisor RuntimeClass | Run the Pod through `runsc`, which handles guest system calls in a userspace kernel. | Reduce the host kernel surface exposed to guest code. This is not a per-Pod VM; validate the handler and volumes on eligible nodes. |
| Approved execution image and Pod Security | Supply Bash/Python and enforce non-root UID, read-only root, seccomp, dropped capabilities, no privilege escalation and no guest service account token. | Limit files and privileges inside the guest. Only `/work` and `/tmp` should be writable; selected `/inputs` and `/skills` mounts remain read-only. |
| CNI and deny-all NetworkPolicy | Apply ingress and egress filtering to every sandbox Pod. | Block guest connections to the Kubernetes API, broker, other workloads and the Internet. Policies are additive and require a CNI that enforces them. |
| Kubernetes RBAC and ResourceQuota | Give the broker only the required namespace operations and cap Pod, CPU, memory and storage use. | Limit control-plane blast radius and resource exhaustion. The privileged broker remains part of the trusted boundary. |
| Optional rclone CSI | Mount a per-workload `/inputs` PVC in the guest; the CSI node plugin connects to the file gateway. | Present selected files read-only without placing the WebDAV credential in the guest. The privileged node plugin is a trusted cluster component, not a guest security boundary. |
| Knowledge Flow file gateway | Resolve selected corpus documents and conversation attachments on each read. | Recheck active account, team or personal scope, conversation binding and document authorization; never expose the whole corpus bucket. |
| Control plane admin settings | Set the inactivity timeout (20 minutes by default) and active-conversation cap. | Bound workload lifetime and cost. Image, RuntimeClass, network and resource profiles remain operator-approved deployment settings. |

Use a dedicated sandbox node pool where possible. Install an operator-approved Kata or gVisor distribution there and create a `RuntimeClass` with the corresponding handler. For Kata, verify KVM and the node runtime configuration. For gVisor, verify `runsc` on every eligible node. Managed offerings may supply a different RuntimeClass name; use that exact name throughout the manifests. Never fall back to the default container runtime when the requested handler is unavailable.

```sh
kubectl get runtimeclass
kubectl get runtimeclass <approved-runtime-class> -o jsonpath='{.handler}'
kubectl get nodes -o wide
```

Check RuntimeClass scheduling and Pod overhead against the actual node pool. Select an approved Python image containing Bash, pin it as `registry/name@sha256:<digest>`, and make it available on those nodes. Image pull, scheduling, CSI and VM creation all contribute to first-call latency. The example `agent-sandbox*.yaml` templates name `gvisor`; replace this with the approved RuntimeClass when using Kata or a managed cluster handler. Test each runtime and CSI combination independently.

## 2. Prepare the sandbox namespace and broker

Review [kubernetes.yaml](../../../deploy/sandbox/kubernetes.yaml) before applying it. Replace the broker image, sandbox image, runtime name, isolation choice and capacity. The example creates `fred-sandbox` with Pod Security Restricted, deny-all ingress/egress, a ResourceQuota, and narrow broker RBAC; `fred-sandbox-system` holds the broker. The broker Deployment is one replica because its active admission and conversation map are currently in memory. Give access to the template and policy resources only to cluster operators.

Create `fred-sandbox-broker-auth` with key `token` (at least 32 random characters) and `fred-sandbox-broker-tls` in `fred-sandbox-system`. The certificate must cover the broker Service DNS name, and the broker's non-root UID/GID must be able to read its key. Configure trusted Fred agent pods with `FRED_SANDBOX_BROKER_URL`, `FRED_SANDBOX_BROKER_TOKEN` and the TLS CA. Never mount a Docker socket in an agent pod. Review the Fred chart before deployment: its current `fred-agents` defaults automount a Kubernetes token and grant Secret reads and Deployment writes. These rights do not reach the sandbox guest, but they increase the impact of an agent-pod compromise. Remove unneeded rights or separate the Kubernetes controller workload from the agent runtime before enabling the broker credential.

The guest Pod security contexts already request `runAsNonRoot`, UID/GID 65534, `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, dropped capabilities and `seccompProfile: RuntimeDefault`. They also disable service account token automount, host networking/PID/IPC and service links. Keep these controls: they reduce exposure inside the isolated runtime and catch configuration mistakes; Kata or gVisor provides a separate boundary. The broker is also non-root, but deliberately has a narrowly scoped Kubernetes token for orchestration. Do not apply the guest's Restricted policy to the privileged CSI node plugin namespace.

## 3. Prove network and process limits before enabling execution

Apply the reviewed namespace, policy, quota, RBAC, Deployment and Service. Keep `SANDBOX_NETWORK_POLICY_VERIFIED=false` and `SANDBOX_PID_LIMIT_VERIFIED=false` at first. Verify that no other policy selects sandbox Pods: Kubernetes policies are additive. On each eligible node pool, run a temporary Pod with the chosen RuntimeClass and a controlled outbound TCP target. Add a temporary allow rule for only that probe Pod and verify connectivity; remove it and verify the connection is denied. Denied in both phases proves nothing. Restrict policy mutation thereafter and monitor for drift: the Job backend checks policies at broker startup, while SIG also checks before each claim. Neither check protects an already running Pod after a policy change.

Inspect every eligible kubelet's `podPidsLimit`; it must be finite and positive. Pod specs cannot set this limit. Set the two `*_VERIFIED` flags to `true` only after the respective checks and restart the broker. Confirm its health and that there are zero guest Pods before the first code call.

```sh
kubectl -n fred-sandbox get networkpolicy,resourcequota,pods
kubectl -n fred-sandbox-system rollout status deployment/fred-sandbox-broker
kubectl auth can-i create jobs -n fred-sandbox --as=system:serviceaccount:fred-sandbox-system:fred-sandbox-broker
```

## 4. Select the on-demand lifecycle backend

For a minimal Kubernetes installation set `SANDBOX_BACKEND=kubernetes`. The broker creates a Job at the first code call, reuses its Pod for that conversation and deletes it after idle expiry. No additional CRDs are needed.

For SIG Agent Sandbox, install the pinned upstream `sandbox-with-extensions.yaml` release v1.0.6, inspect its cluster-wide RBAC and controller image, then apply [agent-sandbox.yaml](../../../deploy/sandbox/agent-sandbox.yaml) with the approved image and RuntimeClass. Set `SANDBOX_BACKEND=agent_sandbox` and the exact `SANDBOX_AGENT_POOL_NAME`. Keep `SandboxWarmPool.spec.replicas: 0`: claims still create workloads on demand. The template uses `networkPolicyManagement: Unmanaged` so Fred's deny-all policy stays authoritative. The SIG controller handles lifecycle; it does not replace Kata/gVisor or the network checks.

```sh
kubectl get crd sandboxes.agents.x-k8s.io sandboxclaims.extensions.agents.x-k8s.io
kubectl -n fred-sandbox get sandboxtemplate,sandboxwarmpool
kubectl -n fred-sandbox get sandboxwarmpool fred-code -o jsonpath='{.spec.replicas}'
```

Give the approved profile ID to the control plane. Admins can then change only the inactivity timeout (default 20 minutes) and the active-conversation cap without redeployment. Configure the internal settings endpoint and separate `SANDBOX_SETTINGS_TOKEN` as described in the broker README; the runtime, image, resource and security policy remain operator-approved deployment settings. Set the cap below the tested node, quota and budget ceiling. Connected users who never execute code use no guest Pod. A retained conversation is never assigned to another user or conversation.

## 5. Optional read-only documents at `/inputs`

Skip this step if code execution alone is sufficient. Existing skill, corpus, attachment and tabular tools continue to work without a sandbox file mount.

Install an operator-approved rclone CSI driver on every eligible node and review its privileged node plugin, RBAC and image digests. The `fred-deployment-factory` k3d bootstrap supplies a tested local example with pinned rclone CSI v0.5.0 chart/images and a controller Secret-read Role confined to `fred-sandbox`; adapt that installation for production rather than assuming its k3d node paths or trust policy apply to your cluster. The CSI driver needs node FUSE support and HTTPS access to Knowledge Flow. The guest still has deny-all egress.

Apply [rclone-webdav-storageclass.yaml](../../../deploy/sandbox/rclone-webdav-storageclass.yaml) and [file-mount-rbac.yaml](../../../deploy/sandbox/file-mount-rbac.yaml) only when enabling mounts. The StorageClass names the CSI provisioner and a per-PVC Secret in `fred-sandbox`; it uses a 1-second directory cache and no VFS write cache. The broker creates a distinct Secret/PVC per workload. Keep CSI controller Secret reads confined to this namespace, and protect the privileged plugin and its configuration as part of the trusted node boundary.

Configure the same strong `SANDBOX_FILE_GATEWAY_SECRET` in the broker and Knowledge Flow, plus `FRED_SANDBOX_FILE_GATEWAY_SECRET` in the trusted agent runtime. Configure the broker's HTTPS `SANDBOX_FILE_GATEWAY_URL`, `SANDBOX_MOUNT_PROVIDER=rclone_csi`, `SANDBOX_FILE_STORAGE_CLASS=fred-sandbox-webdav`, and the [file mount broker patch](../../../deploy/sandbox/file-mount-broker.patch.yaml). The driver and node must trust the gateway certificate. Enable `FRED_SANDBOX_FILE_MOUNTS_ENABLED=true` in the agent runtime only after the gateway and volume test pass. The shared secret and per-volume bearer stay outside the guest.

For SIG, apply [agent-sandbox-files.yaml](../../../deploy/sandbox/agent-sandbox-files.yaml), set the matching pool name, and retain zero replicas. If platform-approved skill scripts also need a `/skills` mount, use the separately documented approved-volume profile in the broker README. The `/inputs` mount exposes selected files, not an entire bucket or corpus. Authorization follows the agent's team or personal scope and the conversation's attachments; a newly selected file can appear in the same mounted conversation after the short directory cache refresh.

## 6. Validate on the target cluster

1. Execute Python and Bash from a real agent conversation. Inspect the tool detail: it should show the code and bounded stdout/stderr. Run a second call in the same conversation to confirm `/work` persists, then verify the workload disappears after the configured idle period.
2. When mounts are enabled, select a real authorized corpus document and attachment, read both through `/inputs`, and verify a write fails. Add another authorized file while the conversation stays active and verify it appears without a Pod restart. Confirm an unauthorized team/personal document and an attachment from another conversation remain inaccessible.
3. Inspect the guest Pod: pinned image, approved `runtimeClassName`, non-root user, dropped capabilities, read-only root, no service account token and deny-all policy. Verify that neither `kubectl` nor cluster credentials are in the execution image. The broker image may contain `kubectl` because it is a separate trusted control Pod.
4. Run [benchmark.py](../../../deploy/sandbox/benchmark.py) with at least 20 cold samples and a retained-session run on the real cluster. Record p50/p95, image cache state, node type, backend, runtime and mount state. Do not infer production latency from the k3d prototype. Load-test admission and quota at the intended concurrency before increasing the cap.

On AKS, evaluate its supported Kata pod sandboxing profile and its documented resource and volume limitations before using that RuntimeClass. On s3ns or another cluster, validate the runtime, CNI and CSI node path there. If any isolation or mount preflight fails, keep code execution disabled for that profile rather than silently selecting an ordinary container runtime.

## Deployment choices

Prefer Kata when the cluster provides a supported VM runtime and the `/inputs` CSI volume passes a real mount test. This gives each guest its own kernel. Use gVisor where Kata is unavailable and `runsc`, NetworkPolicy and the same file-mount tests pass. SIG Agent Sandbox is a useful Kubernetes lifecycle controller on either runtime, but the simpler Job backend is available when its CRDs or controller are not approved. Both start with zero preloaded workloads.

For native Docker development, keep the same Fred capability and broker API, set `SANDBOX_BACKEND=docker`, and use a dedicated TLS Docker daemon with an approved Kata or gVisor runtime. The optional read-only file view uses the rclone Docker volume plugin rather than Kubernetes CSI. A plain local subprocess or a default Docker runtime does not meet this arbitrary-code isolation profile. See the [Docker setup](../../../apps/sandbox-broker/README.md#docker) for daemon and plugin requirements.
