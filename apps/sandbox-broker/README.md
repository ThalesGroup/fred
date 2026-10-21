# Fred sandbox broker prototype

The broker runs short Bash or Python programs in disposable Kata or gVisor workloads. Fred agent pods call its authenticated HTTPS API; only the broker has Kubernetes or Docker control credentials. Each workload is leased once, then destroyed. By default, workloads start on demand and no sandbox Pod remains idle. An optional warm pool trades idle cost for lower request latency. The broker holds at most `SANDBOX_MAX_SANDBOXES` prepared, active, and terminating workloads combined. Connected chat users do not each consume a sandbox.

This prototype is for a controlled pilot. It has one broker replica and local admission accounting. It has no per-team quota or durable work queue. A cluster's CNI behavior, node virtualization support, image provenance, and actual first-execution latency require operator validation.

## Configuration

| Variable | Purpose |
| --- | --- |
| `SANDBOX_BACKEND` | `kubernetes` or `docker` |
| `SANDBOX_ISOLATION` | `kata` or `gvisor` |
| `SANDBOX_RUNTIME_NAME` | Exact RuntimeClass or Docker runtime name |
| `SANDBOX_IMAGE` | Approved Python image pinned as `name@sha256:<64 hex chars>` and containing Bash |
| `SANDBOX_BROKER_TOKEN` | Random token of at least 32 characters |
| `SANDBOX_MAX_SANDBOXES` | Hard cap on prepared plus active workloads, default 8 |
| `SANDBOX_WARM_POOL_SIZE` | Ready workloads held before requests, default 0 |
| `SANDBOX_COLD_START_ON_MISS` | Provision on demand when no ready workload exists, default `true` |
| `SANDBOX_EXECUTION_TIMEOUT` | Per-call deadline in seconds, default 15 |
| `SANDBOX_OUTPUT_LIMIT_BYTES` | Limit for each stdout/stderr stream, default 8192 |
| `SANDBOX_NETWORK_POLICY_VERIFIED` | Kubernetes only: set `true` after the CNI probe below |
| `SANDBOX_PID_LIMIT_VERIFIED` | Kubernetes only: set `true` after checking a finite kubelet `podPidsLimit` on every eligible node |

The agent pod needs `FRED_SANDBOX_BROKER_URL`, `FRED_SANDBOX_BROKER_TOKEN`, and a trusted CA for the broker certificate. The URL must use HTTPS unless it points to loopback. Its tool schema contains only `language` and `code`; never put credentials in code. Grant the capability to a team through Fred's normal admin gate. The capability remains unavailable without a configured broker.

## Kubernetes pilot

1. Install Kata or gVisor on selected nodes and create a RuntimeClass whose handler selects that runtime. For Kata, verify KVM access and node scheduling; for gVisor, verify `runsc` is installed on scheduled nodes. Pre-pull the approved image to reduce cold start time. `kubectl get runtimeclass <name> -o jsonpath='{.handler}'` must show the intended handler. Where the installed Kata implementation supports it, evaluate QEMU VM templating on the sandbox nodes; it accelerates VM creation without keeping sandbox Pods alive. Validate the exact Kata runtime and configuration before enabling it.
2. Review [kubernetes.yaml](../../deploy/sandbox/kubernetes.yaml), set the broker image, pinned execution image, runtime name, and pool size. Create `fred-sandbox-broker-auth` (key `token`) and `fred-sandbox-broker-tls` in `fred-sandbox-system`. The TLS certificate must cover `fred-sandbox-broker.fred-sandbox-system.svc` and its private key must be readable by group 65532. Keep both verification flags `false` for this first deployment.
3. Apply the manifest. Verify that the `fred-sandbox` namespace enforces Pod Security Restricted and has exactly one NetworkPolicy, `fred-sandbox-deny-all`, selecting every pod for both ingress and egress. Kubernetes policies are additive: an additional allow policy can reopen traffic. Restrict changes to this namespace with RBAC or admission policy so the deny policy cannot be removed or supplemented after broker startup. The broker checks the policy set at startup, but its existence alone does not prove the CNI enforces it.
4. Probe the CNI with a temporary pod in `fred-sandbox` using the selected RuntimeClass and the same non-root security context. Choose a controlled reachable IP and port. Apply a temporary egress policy selecting only that probe pod and allowing that target; verify a TCP connection succeeds. Remove the temporary allow policy and verify the same connection fails. Delete the probe pod. A failure in both phases is inconclusive. Repeat on every sandbox node pool and after CNI changes.
5. Check the kubelet configuration on every node that can host a sandbox: `podPidsLimit` must be finite and positive. Set `SANDBOX_PID_LIMIT_VERIFIED=true` only after this check and keep node admission restricted to those nodes. Pod specifications cannot set a PID limit themselves.
6. Set `SANDBOX_NETWORK_POLICY_VERIFIED=true` only after the probe, then restart the broker. With the default pool size of zero, startup creates no sandbox Pods; each call provisions a Job on demand. Configure the agent pod with the HTTPS URL and token through `extraEnvVars` and mount the broker CA with `extraVolumes` / `extraVolumeMounts` in the `agent-pod` Helm chart. Set `SSL_CERT_FILE` to that CA path if needed. Do not mount a Kubernetes token in the agent pod.

The broker service account can create and delete Jobs, read Pods and list policies, and execute in Pods only in `fred-sandbox`; it can read RuntimeClasses and the namespace object cluster-wide. Kubernetes 1.31+ WebSocket exec can use GET, so the RBAC grants both `get` and `create` on `pods/exec`. The Job has `activeDeadlineSeconds` and TTL cleanup as backstops if the broker dies.

## Docker or local pilot

Run the broker on a dedicated host with a Docker daemon configured with Kata or gVisor, or use [docker-compose.yaml](../../deploy/sandbox/docker-compose.yaml) against a dedicated TLS Docker daemon. Never mount the Docker socket into a Fred agent pod. `docker info --format '{{json .Runtimes}}'` must show the configured runtime backed by the expected Kata or `runsc` binary. Pre-pull the pinned execution image on that daemon; pool preparation uses `--pull never`.

For local host execution, install this package and its dependencies, set the variables above, and start `uvicorn sandbox_broker.main:app --host 127.0.0.1 --port 8443` with a local certificate or reverse proxy. The Docker backend uses `--runtime`, `--network none`, read-only root, non-root UID, dropped capabilities, bounded resources, and `--rm`; each lease is forcibly removed after one call. The broker's Docker control access is effectively host-admin access, so isolate its daemon from Fred and other workloads.

## Latency and cost

On-demand mode provisions a Job or Docker container when the call arrives, then runs code and destroys it. Kubernetes scheduling, image preparation, and VM startup all contribute to this cold path; a fast VM alone does not imply a fast first call. Run [benchmark.py](../../deploy/sandbox/benchmark.py) with `--mode cold` on the actual cluster, using `FRED_SANDBOX_BROKER_URL` and `FRED_SANDBOX_BROKER_TOKEN`. The script takes at least 20 sequential samples and reports p50 and p95 broker request-to-result latency. If the cold path is too slow for the product, set `SANDBOX_WARM_POOL_SIZE` to the smallest useful value, set `SANDBOX_COLD_START_ON_MISS=false` during the ready-path measurement, and rerun with `--mode ready`. This avoids labeling a concurrent cold fallback as a ready sample. A ready workload runs through `kubectl exec` or `docker exec` without VM creation; idle workloads are retired and replaced before their one-hour deadline. Excess calls receive retryable `busy` at the hard cap. Compare latency with the idle VM cost and burst rejection before choosing a configuration. A pool of 8 Kata VMs is a fixed idle cost for a platform with 2,000 connected users; zero warm Pods avoid that idle VM cost, although the broker Pod and any Kata template remain. This pilot uses one broker replica because its cap is process-local.

Code is visible in process arguments and Kubernetes Pod exec requests to administrators with sufficient access. Do not send secrets in source. Untrusted code output is returned as data, never as platform instructions.
If the agent disconnects after submission, execution may continue until the configured deadline before cleanup. Cancelling the broker request task triggers immediate cleanup. A disconnect during cold provisioning may still complete the bounded preparation step before cleanup.
