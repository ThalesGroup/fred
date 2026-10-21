## Context

The Deep agent's `/scratchpad/` is text-only and deliberately has no executor. Fred capabilities expose model tools through `tools(ctx)` and reach platform services through optional typed `RuntimeServices` ports. Agent pods currently do not mount a Kubernetes service account token. See `proposal.md` and `specs/agent-code-sandbox/spec.md`.

## Goals / Non-Goals

**Goals:**
- Keep host and cluster control credentials out of agent pods.
- Make a single one-shot execution contract usable with Kubernetes Jobs and Docker containers.
- Make runtime selection and absence of network access visible in operator configuration.

**Non-Goals:**
- Persistent interactive sandboxes, package installation, GPU access, filesystem mounts, and Wasm modules.
- Proving a specific cluster's CNI or hypervisor isolation from repository tests.
- Starting one VM for every connected user; only active code calls consume a workload.

## Decisions

1. The `code_sandbox` capability contributes one tool. Its LLM schema has only `language` and `code`. An optional SDK port carries the call to an out-of-pod broker. This preserves the ReAct, Deep, and Graph capability path and keeps broker URL, credentials, and identity out of model arguments. An MCP tool alone would not make the execution security and admin gate part of Fred's first-party capability contract.
2. The broker owns backend selection and admission. It accepts one-shot requests, holds a finite capacity counter, and exposes a backend protocol with `preflight`, `prepare`, `execute`, and `dispose`. Default on-demand mode keeps zero sandbox Pods idle. An optional small pool prepares Kubernetes Jobs or Docker containers ahead of requests. Each workload is leased exactly once, then deleted; a background task replenishes warm capacity. At the hard cap, admission returns `busy`. There is no local subprocess backend for agent code.
3. An operator chooses `kata` or `gvisor` plus an explicit RuntimeClass/runtime name. Kata is preferred when KVM and node support are proven; gVisor is an explicit alternative for clusters where nested virtualization is unavailable. Runtime discovery checks the configured selection and refuses the default runtime. No runtime is chosen by the agent.
4. The execution image is fixed by the broker. Code is passed as an argument to `bash -c` or `python -c`; it is therefore visible to administrators with workload-read privileges. Do not send secrets as code. A later artifact channel can improve this without changing the execution port.
5. Kubernetes isolation uses a dedicated namespace with exactly one default-deny ingress and egress policy, no service account token, a non-root container, read-only root filesystem, bounded emptyDir scratch space, dropped capabilities, no privilege escalation, seccomp RuntimeDefault, resource limits, `activeDeadlineSeconds`, and Job TTL. Docker uses `--network none`, explicit `--runtime`, equivalent container restrictions, and forced cleanup. A platform operator must verify CNI policy enforcement and finite kubelet `podPidsLimit`, and govern policy changes, before production admission.
6. The broker requires a bearer credential delivered outside the agent tool schema. Kubernetes RBAC is scoped to Jobs and Pods in the sandbox namespace. The broker is a separate service; the agent pod receives no Docker socket or Kubernetes API privilege. Production transport must be protected by TLS or a service mesh.
7. The benchmark measures broker request-to-result time for a trivial program on both cold and ready paths. It reports p50 and p95 on the actual cluster without a fixed acceptance threshold. The operator increases the warm pool from zero only if cold latency is unsuitable for the product and the idle cost is justified. Pool refill and burst admission are measured separately.

## Risks / Trade-offs

- [Kata requires node virtualization and adds VM overhead] -> preflight node support; choose gVisor explicitly on unsupported clusters; schedule only active code calls.
- [Kubernetes scheduling or VM startup may dominate cold latency] -> benchmark the target cluster before production, tune the pool or use an explicit gVisor deployment where its isolation is acceptable.
- [NetworkPolicy objects do not prove CNI enforcement] -> operator network probe and restricted namespace are required before production; do not label this prototype production-ready on s3ns without that check.
- [NetworkPolicy is additive and kubelet owns Pod PID limits] -> fail startup unless the namespace has exactly the deny policy and the operator attests network and PID controls; enforce policy immutability and eligible node configuration outside the broker.
- [One broker process has only local capacity and warm-pool accounting] -> run one replica for the prototype; add distributed admission or a queue before horizontal scaling. Size the pool from measured simultaneous code calls, not total connected users.
- [Container arguments can expose source to cluster administrators] -> prohibit secrets in code; consider encrypted input delivery in a later slice.
- [The broker is privileged by design] -> isolate it from agent pods and limit Docker daemon or Kubernetes RBAC access.

## Migration Plan

Deploy the sandbox namespace and verify runtime/CNI prerequisites, then deploy one broker replica and configure the agent pod with its endpoint and credential. Register the capability but keep it disabled for teams until validation. Roll back by removing the agent endpoint, disabling the capability, and deleting the broker; finished Jobs expire automatically.
