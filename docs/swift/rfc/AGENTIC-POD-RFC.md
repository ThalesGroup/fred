

# 📄 RFC — Fred Runtime Discovery Contract (FRDC) v1

## Status

Proposed

## Authors

Dimitri Tombroff

## Version

v1

---

# 1. Overview

This document defines the **Fred Runtime Discovery Contract (FRDC)**.

It standardizes how:

* a **Fred runtime** (built with `fred-runtime`)
* deployed on **Kubernetes**
* exposes its **agent catalog**
* and is discovered automatically by the **Fred core platform**

## 1.1 Migration Direction

This RFC also records the current frontend/runtime migration direction so
runtime discovery stays aligned with the target architecture:

- the Fred frontend uses the native `fred-runtime` SSE protocol as the primary
  execution surface:
  - `POST /agents/execute/stream`
  - `POST /agents/execute`
  - `GET /agents/sessions/{session_id}/messages`
- all execution is team-scoped and must be attributable to
  `user_id + team_id + agent_instance_id`
- managed execution targets `agent_instance_id`; raw agent names are secondary
  and remain for internal/dev compatibility only
- `control-plane-backend` is the single authority for product, tenancy,
  authorization, runtime discovery, and managed agent enrollment
- runtime pods are execution-only surfaces: they validate authorized requests
  but do not decide permissions, team membership, or routing
- runtime observability is part of the execution contract: logs, KPI, metrics,
  and trace metadata must remain attributable to
  `user_id + team_id + agent_instance_id`, including when exported to Langfuse
- `fred-agents-cli` remains a first-class backend validation client for
  managed team-scoped execution, resume, and local KPI inspection
- `agentic-backend` is no longer the convergence layer for frontend chat/runtime
  behavior and must not regain that role
- OpenAI-compatible endpoints remain a secondary interoperability surface, not
  the primary frontend contract

Kubernetes-native routing remains the default platform boundary:

- use `Service`, DNS, Ingress, and deployment descriptors for routing/discovery
- do not reimplement pod discovery, traffic steering, or topology logic in Fred code

---

# 2. Design Principles

### 2.1 Kubernetes-native discovery

* Discovery MUST rely on **Kubernetes Services**
* Pods MUST NOT be directly discovered

### 2.2 Separation of concerns

* Kubernetes manages **network identity (runtime)**
* Fred manages **logical agents (inside runtime)**

### 2.3 Multi-agent runtime support

* One runtime MAY expose multiple agents
* Agents MAY be public or internal

### 2.4 Minimal friction for developers

* Runtime MUST expose a **simple HTTP contract**
* Deployment MUST rely on **labels + annotations only**

---

# 3. Terminology

| Term           | Definition                                  |
| -------------- | ------------------------------------------- |
| Runtime        | A deployed application using `fred-runtime` |
| Agent          | A logical agent exposed by the runtime      |
| Public agent   | Visible and invokable from Fred             |
| Internal agent | Only usable within the runtime              |
| Service        | Kubernetes Service exposing the runtime     |

---

# 4. Kubernetes Contract

## 4.1 Required Resources

A Fred runtime MUST deploy:

* a `Deployment`
* a `Service` (ClusterIP)
* a container exposing HTTP

---

## 4.2 Service DNS

Fred MUST resolve runtimes using Kubernetes DNS:

```
<service>.<namespace>.svc.cluster.local
```

---

# 5. Label Contract

## 5.1 Standard Kubernetes Labels (REQUIRED)

```
app.kubernetes.io/name: "<runtime-name>"
app.kubernetes.io/instance: "<instance-name>"
app.kubernetes.io/component: "agent-runtime"
app.kubernetes.io/part-of: "fred"
app.kubernetes.io/managed-by: "<tool>"
```

These MUST be applied to:

* Deployment
* PodTemplate
* Service

---

## 5.2 Fred Labels (REQUIRED)

Applied to Service (mandatory):

```
fred.io/runtime: "true"
fred.io/runtime-name: "<runtime-name>"
fred.io/runtime-version: "<semver>"
fred.io/protocol: "http"
fred.io/discovery: "v1"
```

---

## 5.3 Optional Labels

```
fred.io/environment: "dev|test|prod"
fred.io/team: "<team>"
fred.io/domain: "<domain>"
```

---

# 6. Annotation Contract

## 6.1 Required Annotations (Service)

```
fred.io/api-base-path: "/samples/agents/v1"
fred.io/metadata-path: "/samples/agents/v1/metadata"
fred.io/agents-path: "/samples/agents/v1/agents"
fred.io/health-path: "/samples/agents/v1/health"
fred.io/default-agent-id: "<agent-id>"
fred.io/auth-mode: "none"
```

---

## 6.2 Optional Annotations

```
fred.io/docs-url: "https://..."
fred.io/ui-category: "samples"
fred.io/icon: "bot"
fred.io/owner: "team-x"
fred.io/compatibility-min-core-version: "1.0.0"
```

---

# 7. HTTP Runtime Contract

## 7.1 GET /metadata

Response:

```
{
  "discovery_version": "v1",
  "runtime": {
    "id": "samples-agents",
    "name": "samples-agents",
    "version": "1.0.0",
    "fred_runtime_version": "0.9.0",
    "fred_sdk_version": "0.9.0",
    "protocol": "http",
    "base_path": "/samples/agents/v1",
    "default_agent_id": "fred.samples.assistant",
    "auth_mode": "none"
  }
}
```

---

## 7.2 GET /agents

Response:

```
{
  "discovery_version": "v1",
  "runtime_id": "samples-agents",
  "agents": [
    {
      "id": "fred.samples.assistant",
      "display_name": "Assistant",
      "kind": "assistant",
      "visibility": "public",
      "entrypoint": true,
      "description": "Generic assistant",
      "capabilities": ["chat"]
    }
  ]
}
```

---

## 7.3 Agent Schema

Required fields:

* id
* display_name
* kind
* visibility
* entrypoint

Visibility values:

* public
* internal
* admin
* deprecated

---

## 7.4 GET /health

* MUST return 200 when ready
* MUST return non-200 otherwise

---

# 8. Probes

Runtime MUST define:

* readiness probe (REQUIRED)
* liveness probe (RECOMMENDED)
* startup probe (STRONGLY RECOMMENDED)

---

# 9. Fred Core Behavior

## 9.1 Discovery

Fred MUST select Services with:

```
fred.io/runtime=true
```

---

## 9.2 Runtime Processing

Fred MUST:

1. Resolve Service DNS
2. Call /metadata
3. Call /agents

---

## 9.3 Validation

Fred MUST verify:

* discovery version
* default agent exists
* at least one public agent

---

## 9.4 Registration

Fred MUST:

* register runtime
* register public agents

---

## 9.5 Failure Handling

Runtime is unavailable if:

* Service not ready
* metadata fails
* agents fails

---

# 10. RBAC Requirements

Fred MUST have:

* get/list/watch on Services

---

# 11. Namespace Discovery

Recommended:

```
fred.io/discovery-enabled=true
```

---

# 12. Compatibility

Runtime MUST declare:

* fred.io/discovery=v1
* discovery_version=v1

---

# 13. Helm Template Example

```
metadata:
  labels:
    app.kubernetes.io/name: {{ .Values.name }}
    app.kubernetes.io/component: agent-runtime
    app.kubernetes.io/part-of: fred
    fred.io/runtime: "true"
    fred.io/runtime-name: {{ .Values.name }}
    fred.io/runtime-version: {{ .Chart.AppVersion }}
    fred.io/protocol: "http"
    fred.io/discovery: "v1"
  annotations:
    fred.io/api-base-path: {{ .Values.basePath }}
    fred.io/metadata-path: "{{ .Values.basePath }}/metadata"
    fred.io/agents-path: "{{ .Values.basePath }}/agents"
    fred.io/health-path: "{{ .Values.basePath }}/health"
    fred.io/default-agent-id: {{ .Values.defaultAgent }}
    fred.io/auth-mode: "none"
```

---

# 14. Non-Negotiable Rules

1. Discovery MUST use Services
2. Runtime MAY expose multiple agents
3. Internal agents MUST NOT be exposed externally
4. Labels = selection, annotations = metadata
5. Runtime MUST implement /metadata, /agents, /health
6. Readiness MUST gate routing
7. Default agent MUST exist and be public

---

# 15. Implementation Guidance

In `fred-runtime`:

* auto-expose endpoints
* validate agents at startup

In Helm:

* enforce labels/annotations

In Fred core:

* implement reconciler loop
* maintain runtime registry


[1]: https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/?utm_source=chatgpt.com "DNS for Services and Pods | Kubernetes"
[2]: https://kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/?utm_source=chatgpt.com "Recommended Labels - Kubernetes"
[3]: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/?utm_source=chatgpt.com "Configure Liveness, Readiness and Startup Probes - Kubernetes"
[4]: https://kubernetes.io/docs/concepts/overview/working-with-objects/annotations/?utm_source=chatgpt.com "Annotations - Kubernetes"
