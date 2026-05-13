# Architectural Security Report: Managed Agent Execution

**Subject:** Secure Decoupled Control & Data Plane (Valet Key Pattern)
**Status:** Architecture Review (Security / RSSI)

---

## 1. Executive Summary

The platform uses a **decoupled architecture**:

* A **Control Plane** decides *who is allowed to do what*
* A **Runtime (Agentic Pod)** performs *execution only*

This separation enables:

* **Strong security (Zero Trust)**
* **High performance (direct streaming, no proxy bottleneck)**
* **Clear responsibility boundaries**

To securely connect both worlds, the system uses a **short-lived authorization token** called an **Execution Grant**, following a well-known pattern similar to **RUNTIME-01/MinIO presigned URLs**.

---

## 2. Key Concepts (Simple View)

| Concept                   | Meaning                                                     |
| ------------------------- | ----------------------------------------------------------- |
| **User**                  | Authenticated via Keycloak (identity)                       |
| **Team**                  | Security boundary (all data & agents are scoped to a team)  |
| **Control Plane**         | Central authority (permissions, agents, teams)              |
| **Runtime (Agentic Pod)** | Stateless execution engine (runs agents, streams responses) |
| **Execution Grant**       | Short-lived authorization proof for a specific action       |

---

## 3. The Execution Flow (Step-by-Step)

### Step 1 — Authorization (Control Plane)

When a user wants to execute an agent:

1. The user calls the **Control Plane**
2. The Control Plane:

   * verifies identity (via Keycloak)
   * checks permissions (via OpenFGA)
   * confirms:

     * user belongs to the team
     * agent instance is allowed
3. The Control Plane generates a **short-lived Execution Grant** (e.g. 5 minutes)

The grant contains:

* `user_id`
* `team_id`
* `agent_instance_id`
* allowed action (`execute` / `resume`)
* expiration timestamp

---

### Step 2 — Direct Execution (Runtime)

The frontend then calls the Runtime **directly** (no proxy).

Each request includes:

* the **User Bearer Token** (identity)
* the **Execution Grant** (authorization)

---

### Step 3 — Double Validation (Runtime)

The Runtime enforces **two independent checks**:

#### 🔒 Lock A — Identity (Who are you?)

* Validate the **Bearer Token**
* Provided by Keycloak
* Ensures the caller is authenticated

#### 🔒 Lock B — Authorization (What are you allowed to do?)

* Validate the **Execution Grant**
* Ensures:

  * correct team
  * correct agent instance
  * correct action
  * not expired

#### 🔗 Correlation Check

* `user_id` in token **must match** `user_id` in grant
  → otherwise: **request is rejected**

---

## 4. Why This Design (Key Benefits)

### ✅ No Central Bottleneck

* Control Plane does NOT proxy execution
* Runtime streaming (SSE) goes directly to the user
* Enables scalability and low latency

### ✅ Strong Security (Zero Trust)

Every request must prove:

* **Who** you are (Bearer Token)
* **What you are allowed to do** (Execution Grant)

No trust based on:

* network location
* internal services
* implicit relationships

---

## 5. Analogy: RUNTIME-01 / MinIO Presigned URL

This architecture is equivalent to a widely used pattern:

| Feature   | File Storage (RUNTIME-01 / MinIO) | Agent Execution (This System) |
| --------- | ------------------------- | ----------------------------- |
| Authority | Storage server            | Control Plane                 |
| Resource  | File                      | Agent                         |
| Token     | Presigned URL             | Execution Grant               |
| Access    | Direct download           | Direct execution (SSE)        |
| Benefit   | No proxy                  | No proxy                      |

👉 The Execution Grant is effectively a **“temporary key”** to access a specific execution.

---

## 6. Security Model (Standards-Aligned)

This design follows well-known principles:

### ✔ Separation of Concerns

* Control Plane = decision
* Runtime = execution

### ✔ Capability-Based Security

* Execution Grant = **explicit permission token**
* Scoped, short-lived, non-reusable outside context

### ✔ Zero Trust

* No implicit trust
* Every request validated independently

### ✔ OAuth-Compatible Model

* Bearer Token = identity
* Execution Grant = delegated authorization

---

## 7. Infrastructure Security (Defense in Depth)

The platform relies on standard Kubernetes security:

### 🔐 Transport Security

* HTTPS / mTLS (via ingress / service mesh)

### 🔒 Network Isolation

* Runtime pods are **not publicly exposed directly**
* Only accessible through controlled ingress paths

### 🚫 No Internal Exposure

The frontend never sees:

* internal service names (`*.svc.cluster.local`)
* pod IPs
* cluster topology

---

## 8. Important Security Note (Current State)

At this stage:

* Execution Grants are **validated structurally** (content + expiry)
* Cryptographic signing is **planned but not yet enforced**

This is acceptable temporarily because:

* all requests are authenticated (Keycloak)
* all traffic is secured (HTTPS)
* grants are short-lived

### Planned Hardening

* Add **HMAC or signature validation**
* Prevent any tampering of the grant payload

---

## 9. Conclusion

This architecture provides:

* **Clear separation** between authorization and execution
* **High performance** through direct runtime access
* **Strong security guarantees** via dual validation (identity + grant)

The pattern is:

* widely used in cloud systems
* compatible with Kubernetes networking
* aligned with Zero Trust principles

👉 In simple terms:

> The Control Plane gives you a temporary, scoped key.
> The Runtime only executes if both your identity and your key are valid.

---

## 10. One-Line Summary (for reviewers)

> The system enforces security by requiring both authenticated identity and a short-lived, control-plane-issued execution authorization for every direct runtime call, eliminating proxy bottlenecks while maintaining strict team-scoped access control.
