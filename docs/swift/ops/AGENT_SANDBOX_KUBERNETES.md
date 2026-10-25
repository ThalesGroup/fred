# Agent code sandbox on Kubernetes

This is the operator path for a production cluster. The [broker README](../../../apps/sandbox-broker/README.md) is the configuration reference; the manifests under `deploy/sandbox/` are examples to review and adapt, not a certified profile for every cluster. Start with code execution, then enable the optional read-only `/inputs` mount after validating the storage path on the chosen runtime.

## 0. Start from a cluster without sandbox components

This procedure assumes Kubernetes and the ordinary Fred services (control plane, Knowledge Flow and agent pods) are already deployed. For a completely empty cluster, install the [Fred base chart](../../../deploy/charts/fred/README.md) and its dependencies first. This sandbox procedure does not require k3d or any `make k3d-*` target. Use the chart's optional `sandboxBroker` section or render the standalone example manifests through Helm, Kustomize or GitOps; do not deploy both broker definitions. Do not apply an example containing `REPLACE_WITH_*` values. Keep the resulting image digests, RuntimeClass, Service names, TLS trust and namespace policy together as one approved profile.

| Order | Operator-owned prerequisite or resource | Fred-side result to verify |
| --- | --- | --- |
| 1 | A sandbox node pool with Kata or gVisor, an enforcing CNI, a finite kubelet `podPidsLimit`, and a digest-pinned Bash/Python image | The selected `RuntimeClass` runs a restricted test Pod on every eligible node pool. |
| 2 | `fred-sandbox` and `fred-sandbox-system`, deny-all policy, quota, broker RBAC, broker token and TLS certificate | The enabled Fred chart creates the broker and its policies after the namespaces and Secrets exist. The [base manifest](../../../deploy/sandbox/kubernetes.yaml) remains an alternative standalone example. |
| 3 | For `/inputs`: a reviewed rclone CSI installation with FUSE, node access to the internal Knowledge Flow HTTPS endpoint, the [StorageClass](../../../deploy/sandbox/rclone-webdav-storageclass.yaml) and [file-mount RBAC](../../../deploy/sandbox/file-mount-rbac.yaml) | The CSI controller and node plugin are Ready, and the controller can read mount Secrets only in `fred-sandbox`. |
| 4 | For `/inputs`: an internal read-only TLS gateway, its CA, and one shared signing secret delivered separately to Knowledge Flow, broker and trusted agent namespaces | Knowledge Flow serves only authorized WebDAV views; the broker has a separate trusted revocation URL. |
| 5 | For `/skills`: one operator-published skill tree and read-only mounts of the same storage in the Fred agent namespace and `fred-sandbox` | The agent uses `skills.directory: /skills`; the sandbox PVC is Bound and labeled `fred.sandbox/skills=approved`. No skill-content ConfigMap or guest hostPath is used. |
| 6 | A rendered Job profile or, after installing SIG CRDs and controller, the matching SandboxTemplate with zero warm replicas | The broker has the exact approved image, RuntimeClass and mount configuration, and starts no guest until the first code call. |
| 7 | Fred agent values for broker access and, when `/inputs` is enabled, file-view signing and mount activation | A real conversation reads an authorized file and skill, denies writes and cross-scope reads, then disposes its Pod after inactivity. |

For a full `/inputs` plus `/skills` profile, the cluster deployment bundle must contain the following rendered resources. The files under `deploy/sandbox/` show the expected shape but are not a production installer:

1. The chart-managed `sandboxBroker` profile or the reviewed standalone `kubernetes.yaml` example, with pinned broker and execution images, approved runtime, namespace policy and broker configuration. Create the two Restricted namespaces and the broker token and TLS Secrets in `fred-sandbox-system` through the cluster's secret manager. On the standalone path, deploy with verification flags false and let the broker remain unready until the network and PID probes pass. On the Helm path, keep `enabled: false` until those probes pass, then set the two verification flags and enable it.
2. A pinned rclone CSI chart with cluster-specific node, FUSE, CA and RBAC values, followed by `rclone-webdav-storageclass.yaml`. On the standalone broker path, add `file-mount-rbac.yaml`; the Fred chart creates this RBAC itself when `mountProvider: rclone_csi`. Keep the CSI plugin in its own privileged namespace, outside the restricted guest namespace.
3. An internal TLS gateway to Knowledge Flow and secret-manager deliveries of the same signing value to Knowledge Flow, the agent namespace and `fred-sandbox-system`. Supply a broker-only revocation URL that does not go through the read-only gateway.
4. One approved skill source, its read-only mount in the Fred agent pods, and a separate approved PVC in `fred-sandbox` pointing to the same data. Set `skills.directory: /skills` in Fred's agent configuration and `SANDBOX_SKILLS_VOLUME` in the broker.
5. Either the Job backend with `SANDBOX_MOUNT_PROVIDER=rclone_csi`, or SIG CRDs/controller plus the combined `agent-sandbox-files-skills.yaml` template and a zero-replica pool. Set the broker pool name to the rendered template's name for SIG.
6. Fred chart values for `FRED_SANDBOX_BROKER_URL`, `FRED_SANDBOX_BROKER_TOKEN`, `FRED_SANDBOX_FILE_GATEWAY_SECRET` and `FRED_SANDBOX_FILE_MOUNTS_ENABLED=true`. The agent trusts the broker CA; the broker and CSI plugins trust the gateway CA. Enable `code_sandbox` for the intended teams only after the probes and conversation test pass.

The operator applies those rendered resources with its normal Helm or GitOps release process. `kubectl apply -f deploy/sandbox/kubernetes.yaml` without rendering will leave example image values in place, and `make k3d-sandbox-files-demo` uses a hostPath and Python WebDAV fixture that are unsuitable as the production skill source or gateway.

There is currently no one-command production installer for this full profile. Fred supplies the broker, Knowledge Flow view endpoint, StorageClass/RBAC examples and workload templates. The cluster operator must supply the approved runtime installation, pinned CSI release and trust configuration, production TLS gateway, shared skill storage and rendered deployment values. Do not mark the file-backed profile ready until all of these pieces pass the checks below.

The always-on components are the broker, CSI driver and any operator-managed file gateway or skill source. There is no always-on sandbox Pod. `/inputs` is one per-conversation virtual tree over Knowledge Flow: the broker creates a separate Secret and PVC when a workload starts, and the CSI plugin mounts it read-only. `/skills` is a separate, persistent operator-approved PVC mounted read-only in the guest. `/work` and `/tmp` use ephemeral scratch, not CSI. A future `/inputs/knowledge-bases` alias is not deployed by these manifests; knowledge-base documents currently use their authorized corpus library path.

Run these checks against the intended context before enabling the capability:

```sh
kubectl config current-context
kubectl get runtimeclass,csidriver,storageclass
kubectl -n fred-sandbox get networkpolicy,resourcequota,pvc
kubectl -n fred-sandbox-system get deployment,service
kubectl -n fred-sandbox-csi get deployment,daemonset
```

The `fred-sandbox-csi` namespace and its resources exist only if rclone CSI was installed there; use the operator's actual CSI namespace otherwise. For the Job backend, no Agent Sandbox CRDs are needed. For SIG, also check `kubectl get crd sandboxes.agents.x-k8s.io sandboxclaims.extensions.agents.x-k8s.io sandboxtemplates.extensions.agents.x-k8s.io sandboxwarmpools.extensions.agents.x-k8s.io` and `kubectl -n fred-sandbox get sandboxtemplate,sandboxwarmpool`. Do not set either broker verification flag to true merely because these objects exist; perform the network and PID probes in section 3.

## 1. Choose the isolation profile and assign ownership

| Component | Role | Protection and boundary |
| --- | --- | --- |
| Fred `code_sandbox` capability and runtime adapter | Offer `execute_code` and prepare its file view from the current user, team and conversation. | Keep broker credentials and deployment choices out of model tool arguments. This interface does not isolate a process. |
| Fred sandbox broker | Authenticate calls, create on demand, retain one workload per executing conversation, and expire it after inactivity. | Keep Kubernetes or Docker control credentials outside the guest; bound execution time, output and active capacity. Protect the broker and its bearer token as trusted control components. |
| Kubernetes Job or SIG Agent Sandbox | Create and dispose of Pods. SIG reconciles `SandboxTemplate`, `SandboxClaim` and `SandboxWarmPool`; keep pool replicas at zero for this profile. | Enforce lifecycle and approved templates. Neither backend isolates syscalls or closes network access by itself. |
| Kata Containers RuntimeClass | Start a lightweight VM for each Pod, with its own guest kernel. | Separate guest kernel execution from the host kernel. Validate KVM, the actual handler and CSI volumes on eligible nodes. |
| gVisor RuntimeClass | Run the Pod through `runsc`, which handles guest system calls in a userspace kernel. | Reduce the host kernel surface exposed to guest code. This is not a per-Pod VM; validate the handler and volumes on eligible nodes. |
| Approved execution image and Pod Security | Supply Bash/Python and enforce non-root UID, read-only root, seccomp, dropped capabilities, no privilege escalation and no guest service account token. | Limit files and privileges inside the guest. Only `/work` and `/tmp` should be writable; authorized `/inputs` and `/skills` mounts remain read-only. |
| CNI and deny-all NetworkPolicy | Apply ingress and egress filtering to every sandbox Pod. | Block guest connections to the Kubernetes API, broker, other workloads and the Internet. Policies are additive and require a CNI that enforces them. |
| Kubernetes RBAC and ResourceQuota | Give the broker only the required namespace operations and cap Pod, CPU, memory and storage use. | Limit control-plane blast radius and resource exhaustion. The privileged broker remains part of the trusted boundary. |
| Optional rclone CSI | Mount a per-workload `/inputs` PVC in the guest; the CSI node plugin connects to the file gateway. | Present authorized files read-only without placing the WebDAV credential in the guest. The privileged node plugin is a trusted cluster component, not a guest security boundary. |
| Knowledge Flow file gateway | Resolve selected corpus documents and conversation attachments on each read. | Recheck active account, team or personal scope, conversation binding and document authorization; never expose the whole corpus bucket. |
| Control plane admin settings | Set the inactivity timeout (20 minutes by default) and active-conversation cap. | Bound workload lifetime and cost. Image, RuntimeClass, network and resource profiles remain operator-approved deployment settings. |

Use a dedicated sandbox node pool where possible. Install an operator-approved Kata or gVisor distribution there and create a `RuntimeClass` with the corresponding handler. For Kata, verify KVM and the node runtime configuration. For gVisor, verify `runsc` on every eligible node. Managed offerings may supply a different RuntimeClass name; use that exact name throughout the manifests. Never fall back to the default container runtime when the requested handler is unavailable.

```sh
kubectl get runtimeclass
kubectl get runtimeclass <approved-runtime-class> -o jsonpath='{.handler}'
kubectl get nodes -o wide
```

Check RuntimeClass scheduling and Pod overhead against the actual node pool. Select an approved Python image containing Bash, pin it as `registry/name@sha256:<digest>`, and make it available on those nodes. Image pull, scheduling, CSI and VM creation all contribute to first-call latency. The example `agent-sandbox*.yaml` templates name `gvisor`; replace this with the approved RuntimeClass when using Kata or a managed cluster handler. Test each runtime and CSI combination independently.

The optional document analysis image in
`fred-deployment-factory/k3d/agent-sandbox/python-documents.Dockerfile` adds
pinned `openpyxl`, `pypdf`, `python-docx`, `python-pptx`, `pandas` and `duckdb` packages with `uv`.
Build and scan it in your registry, then use its digest in the approved
SandboxTemplate. Do not allow the agent to choose or install packages at run time.

## 2. Prepare the sandbox namespace and broker

For Helm, create `fred-sandbox` and `fred-sandbox-system` first with Pod Security Restricted labels. Configure `sandboxBroker.enabled: true`, digest-pinned `image` and `executionImage`, `backend`, `isolation`, `runtimeName` and capacity in the Fred values overlay. The chart creates the deny-all policy, object-count quota, broker RBAC, ServiceAccount, Deployment and Service. Size `sandboxBroker.quota` for the selected `maxSandboxes` and existing namespace objects; the chart rejects a cap above its Pod, Job or file-mount object counts and reserves one PVC for a skills volume. Guest Pods carry their own CPU and memory limits. If the cluster also has CPU, memory or storage quotas, size them for the approved guest profile and capacity. `networkPolicyVerified` and `pidLimitVerified` must remain false until the probes in section 3 succeed; the chart refuses to render an enabled broker while either is false. For the standalone path, review [kubernetes.yaml](../../../deploy/sandbox/kubernetes.yaml), replace its placeholders and apply it through a separate owner. Never apply the standalone broker manifest alongside the chart-managed broker. The default broker Deployment is one replica because its admission and conversation map are process-local. The shared SIG profile described below permits more replicas. Give access to the template and policy resources only to cluster operators.

For SIG, install its CRDs/controller and a reviewed SandboxTemplate and zero-replica SandboxWarmPool before enabling the broker; set `sandboxBroker.backend: agent_sandbox` and the matching `agentPoolName`. The chart adds the broker's claim Role but does not install SIG resources. For read-only `/inputs`, install rclone CSI and the StorageClass first, then set `mountProvider: rclone_csi`, `fileGatewayUrl`, `fileGatewayRevokeUrl`, `fileGatewaySecret` and `fileStorageClass`. The chart adds its file mount RBAC; the CSI controller's own Secret-read grant is still operator managed. `skillsVolume` names the separately approved guest PVC. Use `settingsUrl` with `settingsTokenSecret` for live admin settings, and `caSecret` when the broker needs an internal HTTPS CA. Secrets stay external to the chart. These values are optional and default to code-only execution.

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

For SIG Agent Sandbox, install the pinned upstream `sandbox-with-extensions.yaml` release v1.0.6 and inspect its cluster-wide RBAC and controller image. Apply [agent-sandbox.yaml](../../../deploy/sandbox/agent-sandbox.yaml) only for code execution without file mounts; for `/inputs` or `/skills`, use the matching template in section 5 instead. Set `SANDBOX_BACKEND=agent_sandbox` and the exact `SANDBOX_AGENT_POOL_NAME`. Keep `SandboxWarmPool.spec.replicas: 0`: claims still create workloads on demand. The templates use `networkPolicyManagement: Unmanaged` so Fred's deny-all policy stays authoritative. The SIG controller handles lifecycle; it does not replace Kata/gVisor or the network checks.

```sh
kubectl get crd sandboxes.agents.x-k8s.io sandboxclaims.extensions.agents.x-k8s.io
kubectl -n fred-sandbox get sandboxtemplate,sandboxwarmpool
kubectl -n fred-sandbox get sandboxwarmpool -o custom-columns=NAME:.metadata.name,REPLICAS:.spec.replicas
```

Give the approved profile ID to the control plane. Admins can then change only the inactivity timeout (default 20 minutes) and the active-conversation cap without redeployment. Configure the internal settings endpoint and separate `SANDBOX_SETTINGS_TOKEN` as described in the broker README; the runtime, image, resource and security policy remain operator-approved deployment settings. Set the cap below the tested node, quota and budget ceiling. Connected users who never execute code use no guest Pod. A retained conversation is never assigned to another user or conversation.

## 5. Optional read-only `/inputs` and `/skills` mounts

Skip this step if code execution alone is sufficient. Existing skill, corpus, attachment and tabular tools continue to work without a sandbox file mount.

Install an operator-approved rclone CSI driver on every eligible node and review its privileged node plugin, RBAC and image digests. The `fred-deployment-factory` k3d bootstrap supplies a tested local example with pinned rclone CSI v0.5.0 chart/images and a controller Secret-read Role confined to `fred-sandbox`; adapt that installation for production rather than assuming its k3d node paths or trust policy apply to your cluster. The CSI driver needs node FUSE support and HTTPS access to Knowledge Flow. The guest still has deny-all egress.

Apply [rclone-webdav-storageclass.yaml](../../../deploy/sandbox/rclone-webdav-storageclass.yaml) only when enabling mounts. The chart grants broker Secret/PVC operations when `mountProvider: rclone_csi`; on the standalone path, apply [file-mount-rbac.yaml](../../../deploy/sandbox/file-mount-rbac.yaml) instead. The CSI controller needs separate operator-managed RBAC to read mount Secrets only in `fred-sandbox`. The StorageClass names the CSI provisioner and a per-PVC Secret in `fred-sandbox`; it uses a 1-second directory cache and no VFS write cache. It must not set a shared `remote`: each Secret supplies a distinct remote name matching its config section. The broker creates a distinct Secret/PVC/remote per workload. Give every operator-managed skills PVC its own remote name too. Existing PVCs provisioned with a shared remote must be recreated after changing the StorageClass. Keep CSI controller Secret reads confined to this namespace, and protect the privileged plugin and its configuration as part of the trusted node boundary.

Configure the same strong `SANDBOX_FILE_GATEWAY_SECRET` in the broker and Knowledge Flow, plus `FRED_SANDBOX_FILE_GATEWAY_SECRET` in the trusted agent runtime. For Helm, set `sandboxBroker.mountProvider: rclone_csi`, the gateway and revocation URLs, `fileStorageClass` and `fileGatewaySecret` pointing to the broker's Secret. For the standalone path, configure `SANDBOX_FILE_GATEWAY_URL`, `SANDBOX_MOUNT_PROVIDER=rclone_csi`, `SANDBOX_FILE_STORAGE_CLASS=fred-sandbox-webdav`, and the [file mount broker patch](../../../deploy/sandbox/file-mount-broker.patch.yaml). The driver and node must trust the gateway certificate. Enable `FRED_SANDBOX_FILE_MOUNTS_ENABLED=true` in the agent runtime only after the gateway and volume test pass. The shared secret and per-volume bearer stay outside the guest.

The Python `fred-sandbox-file-gateway` TLS relay in `fred-deployment-factory` is only a local k3d test fixture. In a production cluster, put operator-managed TLS termination (an internal ingress, service mesh or approved proxy) in front of the Knowledge Flow WebDAV endpoint, without a public ingress. Keep the URL path `/knowledge-flow/v1/sandbox-mount`; allow only `GET`, `HEAD`, `PROPFIND` and `OPTIONS` on the read-only WebDAV routes. The certificate must have a SAN for the Service DNS name used in `SANDBOX_FILE_GATEWAY_URL`, and the broker and rclone CSI controller and node plugins must trust its issuing CA. Keep HMAC credential checks and per-request authorization in Knowledge Flow. Neither the shared secret nor the TLS private key or certificate is mounted into the sandbox guest.

The broker separately revokes a workload's view with `DELETE /knowledge-flow/v1/sandbox-mount/views/{key}`. Set `SANDBOX_FILE_GATEWAY_REVOKE_URL` to the trusted internal Knowledge Flow mount base URL so this request bypasses the read-only WebDAV relay. The k3d fixture uses the internal Knowledge Flow Service for this route; in production, protect the broker-to-Knowledge Flow connection with operator-approved TLS and restrict access to trusted broker workloads. Knowledge Flow verifies the HMAC revocation credential. Do not expose `DELETE` on the WebDAV relay or make the revocation route reachable from the sandbox guest.

Publish approved skills from one shared source. The Fred chart does not provision or populate this source: the operator must publish the approved tree from the matching Fred runtime release and keep it writable only by the publishing process. Mount it read-only in the agent pod and configure `skills.directory` to `/skills`; expose the same storage through a separate approved PVC in `fred-sandbox`, mounted read-only at `/skills` in the guest. The skills PVC may use another CSI driver or shared storage technology if it satisfies the broker's access-mode and approval-label checks; `rclone_csi` is specifically required by the current `/inputs` provider. Because claims are namespaced, the agent and guest use distinct claims or mounts of the same underlying source. Do not mount the agent pod's root filesystem or build a second ConfigMap copy. Deep's `CompositeBackend` routes `/skills` inside the agent process, but it is not a Kubernetes volume and cannot itself be mounted by the sandbox. A new file appears in the sandbox after its filesystem cache refresh; the runtime's `/` catalog currently refreshes when its pod restarts. Compare the agent and guest `/skills` listings after publication to catch version drift.

For SIG, render [agent-sandbox-files.yaml](../../../deploy/sandbox/agent-sandbox-files.yaml) for `/inputs` only, [agent-sandbox-skills.yaml](../../../deploy/sandbox/agent-sandbox-skills.yaml) for `/skills` only, or [agent-sandbox-files-skills.yaml](../../../deploy/sandbox/agent-sandbox-files-skills.yaml) for both. Replace the image, RuntimeClass and skills PVC placeholders. Set `SANDBOX_AGENT_POOL_NAME` to the exact selected pool name (`fred-code-files-skills` for both); the example [broker file patch](../../../deploy/sandbox/file-mount-broker.patch.yaml) defaults to `fred-code-files` and must be adjusted for the combined profile. Keep `SandboxWarmPool.spec.replicas: 0`. For the Job backend, set `SANDBOX_SKILLS_VOLUME` to the approved PVC name and `SANDBOX_MOUNT_PROVIDER=rclone_csi` for `/inputs`; no SIG template or pool is required.

The `/inputs/attachments` mount lists at most 32 retained originals from the current conversation. Corpus files are browsable under `/inputs/corpus/libraries/<library-id>/pages/block-00/block-00/page-0000/`; each page contains at most 128 candidates. Two fixed base-100 block levels keep each WebDAV listing at 100 entries or fewer and keep paths stable when the corpus grows. `find`, glob or grep can traverse these directories. Knowledge Flow checks the stored library owner, document tag type, and document READ permission before listing or serving bytes. File mounts fail closed when ReBAC is disabled. New authorized files can appear after the short CSI cache refresh without recreating the Pod; page offsets can shift as the corpus changes, so use the stable `/inputs/corpus/<document-id>/<name>` path when retaining a known file path. A view permits at most 600 WebDAV requests per minute and 100 MiB of reads. A full walk of a very large corpus remains expensive and should be load-tested against this quota and FGA capacity. The sandbox does not receive a whole bucket or storage credential.

## 6. Validate on the target cluster

1. Execute a Bash command and a Bash script invoking Python from a real agent conversation. Inspect the tool detail: it should show the full shell script and bounded stdout/stderr. Issue several code calls concurrently to confirm they open one authorized file view without errors. Run a second call in the same conversation to confirm `/work` persists, then verify the workload disappears after the configured idle period.
2. When mounts are enabled, read a real authorized corpus document and attachment through `/inputs`, and verify a write fails. Add another authorized file while the conversation stays active and verify it appears without a Pod restart. Confirm an unauthorized team/personal document and an attachment from another conversation remain inaccessible.
3. Inspect the guest Pod: pinned image, approved `runtimeClassName`, non-root user, dropped capabilities, read-only root, no service account token and deny-all policy. Verify that neither `kubectl` nor cluster credentials are in the execution image. The broker image may contain `kubectl` because it is a separate trusted control Pod.
4. Run [benchmark.py](../../../deploy/sandbox/benchmark.py) with at least 20 cold samples and a retained-session run on the real cluster. Record p50/p95, image cache state, node type, backend, runtime and mount state. Do not infer production latency from the k3d prototype. Load-test admission and quota at the intended concurrency before increasing the cap.

On AKS, evaluate its supported Kata pod sandboxing profile and its documented resource and volume limitations before using that RuntimeClass. On s3ns or another cluster, validate the runtime, CNI and CSI node path there. If any isolation or mount preflight fails, keep code execution disabled for that profile rather than silently selecting an ordinary container runtime.

## Deployment choices

Prefer Kata when the cluster provides a supported VM runtime and the `/inputs` CSI volume passes a real mount test. This gives each guest its own kernel. Use gVisor where Kata is unavailable and `runsc`, NetworkPolicy and the same file-mount tests pass. SIG Agent Sandbox is a useful Kubernetes lifecycle controller on either runtime, but the simpler Job backend is available when its CRDs or controller are not approved. Both start with zero preloaded workloads.

For native Docker development, keep the same Fred capability and broker API, set `SANDBOX_BACKEND=docker`, and use a dedicated TLS Docker daemon with an approved Kata or gVisor runtime. The optional read-only file view uses the rclone Docker volume plugin rather than Kubernetes CSI. A plain local subprocess or a default Docker runtime does not meet this arbitrary-code isolation profile. See the [Docker setup](../../../apps/sandbox-broker/README.md#docker) for daemon and plugin requirements.

## Shared SIG profile for many conversations

Use this optional profile when active Pods must be bounded independently of the number of conversations. It requires SIG Agent Sandbox and PostgreSQL. Docker and Kubernetes Job backends reject its configuration at startup. A conversation receives one private `ReadWriteOnce` PVC mounted at `/work`; `/tmp` remains bounded `emptyDir`. The broker suspends its Pod after a shorter active-idle interval, keeps its claim and PVC until the admin-controlled final inactivity expiry, and resumes the same Sandbox on the next execution. The SIG warm pool remains at zero replicas. No running sandbox is shared between users or conversations. The [SIG volume guide](https://agent-sandbox.sigs.k8s.io/docs/volumes/volume-claim-template/) explains PVC persistence across Pod replacement; the [SIG status guide](https://agent-sandbox.sigs.k8s.io/docs/sandbox/conditions/) defines the Ready and Suspended conditions used by the broker.

1. Apply the Fred control-plane Alembic migration before enabling `sandboxBroker.shared.enabled`. It creates `sandbox_conversation_leases` and `sandbox_wait_tickets`. Create a separate PostgreSQL login for the broker with `USAGE` on the schema and `SELECT, INSERT, UPDATE, DELETE` on those two tables only. Store its `postgresql://...` DSN in a Secret in `fred-sandbox-system`, key `dsn`. Do not reuse a control-plane owner credential. A failed database connection leaves the shared broker unready and rejects new executions.
2. Select a cluster-approved, encrypted-at-rest `ReadWriteOnce` StorageClass that can mount under the chosen Kata or gVisor RuntimeClass. Check its reclaim policy, node topology, CSI compatibility and deletion behavior. The broker validates the StorageClass name and the admitted PVC ownership, mount and security context. Test that a file in `/work` survives `Running -> Suspended -> Running`, and that final claim deletion removes its PVC. The examples [code only](../../../deploy/sandbox/agent-sandbox-persistent.yaml), [/inputs](../../../deploy/sandbox/agent-sandbox-files-persistent.yaml), and [/inputs plus /skills](../../../deploy/sandbox/agent-sandbox-files-skills-persistent.yaml) show the required template and zero-replica pool. Replace image and skills placeholders and select the exact pool name in the broker values. Keep the PVC claim template on the claim, not a shared guest hostPath.
3. Size `maxSandboxes` for concurrently active or preparing Pods, `maxPreparations` for cold starts, and `maxRetainedSessions` for dormant PVCs. With `/inputs`, each retained Sandbox uses one workspace PVC plus one rclone CSI PVC and Secret; `/skills` adds the approved shared PVC. Set namespace PVC, Secret, storage-byte and SandboxClaim quotas accordingly. The chart checks object counts, while the operator owns storage-byte, CPU and memory quotas. Queue tickets contain only opaque session and tenant hashes, expire after a bounded wait, and are limited globally and per team or personal space. Beyond the limit, clients receive `busy` and may retry. A broker replica restart does not delete retained SIG claims in this profile.
4. Enable the profile in a reviewed Helm overlay. This example has room for 1,000 retained conversations and 50 active Pods; adjust all limits from the measured node and storage budgets:

   ```yaml
   sandboxBroker:
     backend: agent_sandbox
     agentPoolName: fred-code-files-skills-persistent
     maxSandboxes: 50
     replicas: 2
     quota:
       pods: 60
       jobs: 20
       persistentVolumeClaims: 2010
       secrets: 1010
     shared:
       enabled: true
       coordinatorDsnSecret: fred-sandbox-db
       workspaceStorageClass: approved-encrypted-rwo
       workspaceSize: 1Gi
       activeIdleSeconds: 120
       maxRetainedSessions: 1000
       maxPreparations: 8
       maxQueueLength: 256
       maxQueuePerTenant: 8
       queueWaitSeconds: 30
   ```

5. Put the sandbox RuntimeClass on an approved node group using `RuntimeClass.scheduling.nodeSelector` and tolerations. Measure and declare `RuntimeClass.overhead.podFixed` for the actual Kata or gVisor runtime, then configure the node autoscaler from those measured Pod requests plus CPU, memory, PID, IP and CSI limits. Kata includes a guest kernel and VM memory overhead; gVisor uses a userspace kernel. Neither eliminates the per-Pod Kubernetes object cost. Test cold start, active reuse and resume latency separately. Keep a small active cap until a 50/100/250/500/1,000-user ramp with real `/inputs` and `/skills` reaches the intended production ceiling.
6. Observe `GET /healthz` and `GET /metrics` on the broker Service. The shared profile reports active, preparing, suspended, retained and waiting counts, plus local preparation duration and admission refusals. Use `kubectl -n fred-sandbox get sandboxclaim,sandbox,pod,pvc` to compare the counts, `kubectl -n fred-sandbox-system get deploy fred-sandbox-broker` to confirm broker replicas, and `kubectl get runtimeclass <name> -o yaml` to inspect scheduling and overhead. During a database outage, new admission fails closed; existing claims retain their server-side shutdown time. Do not switch back to the process-local profile while shared claims remain: its startup cleanup would delete them. Drain and expire the shared sessions first.
