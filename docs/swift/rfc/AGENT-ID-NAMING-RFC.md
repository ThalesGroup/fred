# RFC: Agent identity — adopt the Kubernetes domain-qualified name convention

**Status:** draft — pending developer sign-off; nothing implemented
**Author:** dimitri.tombroff
**Date:** 2026-09-16
**ID:** AGENTID-01
**Related docs:** `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` (§8.79 — `app.runtime_id`,
the pod-level identity this RFC deliberately mirrors); `docs/swift/capabilities/AUTHORING.md`;
`docs/swift/platform/OBSERVABILITY-AND-AUDIT.md` §3 (`service` as the cross-stream join key)

---

## 1. Problem

`agent_id` is the most visible identifier a third party writes when building on Fred, and it
is the only one with no rule at all.

`fred_sdk/contracts/models.py:934`:

```python
agent_id: str = Field(..., min_length=1)
```

Any non-empty string. The result is not a convention unevenly applied — it is seven
conventions coexisting. Every value below is currently declared in the three repositories:

```
fred.github.assistant          fred.samples.assistant
fred.github.deep_assistant     fred.samples.bank_transfer.graph
fred.github.platform_ops       fred.samples.hello_graph
fred.github.rag_expert         fred.samples.postal_tracking.graph
fred.github.react_rag_mcp      fred.samples.team_of_3.router
fred.github.self_test
fred.github.sentinel           rags.sample.echo
fred.github.sql_expert         rags.sample.mcp
fred.github.test_assistant     rags.sample.validated

sample.candidate_screening_team     v2.sample.screening.resume_parser
sample.research_team                support.router
sample.techblog_team                sql-analyst
custodian     rico     tessa
```

Four defects, worst first.

**The second segment names a different axis each time.** `github` is the repository an agent
ships from — a distribution channel. `samples` is what it is for. `sample`, in fred-rags, is
the same idea spelled singular. A reader cannot infer the segment's meaning, because it has
none consistently.

**The `fred.` prefix carries no information.** Everything here runs on Fred. It is the
project name prefixed onto every artifact of the project.

**The execution model leaks into identity.** `bank_transfer.graph` and `team_of_3.router`
encode *how* the agent is built. Rewriting a ReAct agent as a Graph agent would change its
identity while it remains the same agent to every user. The leak is not even uniform:
`hello_graph` puts the same information in the name rather than a segment.

**Three separators for one concept.** Dots between segments, underscores inside them
(`deep_assistant`), dashes elsewhere (`sql-analyst`) — while the pod-level `runtime_id`
uses dashes (`fred-samples-agents`).

And several agents have no namespace at all (`custodian`, `rico`, `tessa`), which is a
collision waiting for the first third party to ship an agent called `custodian`.

### Why now

Two reasons. First, `app.runtime_id` was given a validated slug this week (AGENTID-01's
sibling change) — the pod now has a rule and the agent does not, which is the wrong way
round for the more visible of the two. Second, the naming has to answer a question it was
never designed for: **Aéroport de Paris and Thales will ship their own agents.** Nothing in
the current scheme tells them what to write, and nothing stops two vendors choosing the
same name.

## 2. Proposal

Adopt the identifier convention Kubernetes already uses for exactly this problem: **a DNS
domain the author controls, a slash, and a short name within it.**

```
fredlab.dev/assistant
fredlab.dev/sql-expert
thalesgroup.com/incident-triage
adp.fr/baggage-assistant
```

This is not a Fred invention. It is the rule Kubernetes applies to label keys, annotation
keys and CRD API groups, including its reservation rule: `kubernetes.io/` and `k8s.io/` are
reserved for the core project and every other author uses a domain they own. That maps onto
Fred one-for-one — **`fredlab.dev/` is reserved for agents Fred itself ships**, and a vendor
uses their own domain.

Three properties follow for free, and none of them need designing:

- **Uniqueness is structural.** Two vendors cannot collide without one of them using a
  domain they do not own.
- **Provenance is readable.** `adp.fr/baggage-assistant` says who is responsible without a
  registry lookup.
- **The reservation rule is already understood** by anyone who has written a Kubernetes
  annotation.

### Version is not part of the identity

`v2.sample.screening.resume_parser` already exists in the tree, and it is the known
anti-pattern: the version sorts first, so every v2 agent is separated from its v1 sibling,
and "the same agent, one version newer" cannot be expressed.

Every recognized scheme keeps version on its own axis — OCI `name:tag`, Maven
`groupId:artifactId:version`, npm `@scope/name@1.2.3`. Fred does the same: **the version is
a separate field on the definition, never a segment of `agent_id`.**

### The rule, precisely

```
<domain>/<name>
```

- `<domain>` — a DNS subdomain the author controls (RFC 1123), lowercase.
- `<name>` — lowercase alphanumerics and dashes, starting with a letter.
- No underscores, no dots inside `<name>`, no execution-model suffix.
- `fredlab.dev/` is reserved for Fred's own agents.

Enforced by a `pattern` on the field in `fred-sdk`, the way `app.runtime_id` now is. **A
convention without validation is what produced the current state**; the pattern is the part
that makes this RFC real, not the prose.

## 3. Alternatives considered

**Reverse-DNS — `dev.fredlab.assistant`.** The Java package / Android `applicationId` /
macOS bundle-id / D-Bus convention. Equally standard, equally non-invented, and it avoids
`/` entirely. Rejected as the primary on two grounds: the reversal is unintuitive outside
the JVM world, and Fred is a Kubernetes platform, so the Kubernetes spelling of the same
idea is the more native of the two. This remains the strongest fallback if `/` proves
awkward somewhere not yet examined.

**OCI-style with a registry host — `ghcr.io/thales/agent:1.0`.** Rejected: the registry
host is meaningful for an image because that is where the bytes live. An agent definition
is not fetched from a registry, so the host would be decoration.

**Keep dotted names, fix only the second segment.** Rejected: it leaves the identifier with
no uniqueness guarantee and no reservation rule, which are the two things a third-party
vendor actually needs. It also keeps the separator inconsistency.

**Do nothing, document the habit.** Rejected: the habit is already seven habits, and the
first external vendor is the forcing function.

## 4. Impact on existing contracts

**Breaking for every existing agent.** All the ids listed in §1 change. `agent_id` is not
merely internal:

- it is `template_agent_id` in `PROMETHEUS_ALLOWED_LABELS`, so dashboards and any alerting
  rule that matches on it break at cutover;
- it appears in `kpi-index` documents already written, which are not rewritten;
- control-plane capability records and team agent-instances reference it.

It is **not** in any URL path — `agent_instance_id` is what routes — so no API path changes,
and `/` inside the value is safe. Prometheus label *values* accept `/` and `.` without
escaping. Both facts were verified against the running stack, not assumed.

A migration needs its own decision and is deliberately out of scope here: the options are a
hard cutover, or accepting both forms for one release with the old form logged as
deprecated. §1's defects are not urgent enough to justify breaking dashboards without that
decision being taken explicitly.

## 5. `runtime_id` stays a bare slug — deliberately

The obvious objection to §2 is that it leaves two identity conventions on one platform: an
agent qualified by domain, a pod named `fred-agents`. That asymmetry is the correct one,
because the two name different kinds of thing.

| | names | uniqueness needed |
|---|---|---|
| `agent_id` | a **publishable artifact** — Thales' agent can be installed into someone else's Fred | global |
| `runtime_id` | a **deployed service** running in one cluster | within that installation |

Kubernetes draws exactly this line and spells the two sides differently, which is why
following it is still not a Fred invention:

- an **API group**, extensible by anyone, is domain-qualified — `widgets.example.com`;
- a **Service**, deployed in your cluster, is a short slug — `my-api`, scoped by namespace.

The recommended-label set makes the same split inside a single string: in
`app.kubernetes.io/name: mysql`, the **key** is domain-qualified and the **value** is a
bare slug. OpenTelemetry's semantic conventions — the industry standard for telemetry
identity across many services — say the same thing: `service.name` is a plain slug, and it
is explicitly *not* required to be globally unique; `service.namespace` carries the scope.

The decisive practical argument is local. `runtime_id` becomes the `service` dimension, and
Fred's other backends already publish bare slugs there: `control-plane`, `knowledge-flow`,
`rags-services`. A domain-qualified pod would be the only irregular value **inside the same
label**, forcing every Grafana query and alert rule to handle two shapes.

**At scale, add a dimension — never lengthen the name.** This is the answer to "what about
a large cluster running many microservices": Kubernetes scopes with namespaces, OpenTelemetry
with `service.namespace`, and neither ever pushes that scope into the service name.
`PROMETHEUS_ALLOWED_LABELS` already carries `env` and `cluster` alongside `service`, so the
mechanism exists here too. If two installations ever need to be told apart, that is the
dimension to populate — not a longer `runtime_id`.

So: `runtime_id` stays `fred-agents`, `rags-agents`, `adp-baggage-agents`. Lowercase and
dashes, as the validated slug added this week already enforces.

## 6. Versioning — descriptive first, coexistence deferred

The field already exists and is a placeholder. `CapabilityCatalogEntry` carries a `version`,
and control-plane writes a literal into it for both projections
(`product/service.py:775` for `kind="agent"`, `:875` for `kind="model"`):

```python
CapabilityCatalogEntry(
    id=template_capability_id(runtime_id, template.template_agent_id),
    version="1",          # hardcoded
    kind="agent",
```

So this is not a new concept to introduce — it is an existing contract field to give meaning
to.

### The decision that governs everything else

**Do two versions of one agent coexist in a running Fred?**

- **Descriptive (recommended now).** One version of `fredlab.dev/assistant` exists per
  installation. The field records *what is running*; deploying the pod moves everyone.
- **Coexistent.** One team stays on 1.x while another moves to 2.0. This needs a resolver
  (which version does this team get?), storage for several definitions of one id, and a
  pinning surface in the UI.

Start descriptive. An agent definition ships **inside a pod**, and a pod deploys as a unit —
so making two versions coexist means the pod contains both, which is a packaging decision
rather than an identity one. OCI and Maven support coexistence because they have a registry
and a resolver behind them; Fred has no agent registry.

Crucially, deferring costs nothing later: because the version is not part of `agent_id`,
coexistence can be added without touching the identifier scheme. That is the whole reason
§2 keeps them separate.

### What to do

1. **Stop hardcoding `version="1"`** — populate it from the definition. On its own this
   answers "which version of the agent produced this answer" in telemetry, and it is
   reversible.
2. **SemVer for the value**, with an honest caveat: for a prompt, the *minor* / *patch*
   distinction is fuzzy. **Major** is the segment that will carry real meaning — "behaviour
   changed in a way that can surprise a team that depended on it". Do not over-invest in the
   other two initially.
3. **The version never enters `agent_id`.** If pinning is ever needed, the *reference* form
   is the one every ecosystem already uses — `fredlab.dev/assistant:1.2.0`, exactly like an
   OCI tag. A reference is not an identity.

This also matches the two conventions §5 already leans on: Kubernetes keeps the version in
`app.kubernetes.io/version`, beside the name and never inside it, and OpenTelemetry keeps it
in `service.version`, beside `service.name`.

## 7. Open question

**Migration shape** (see §4). The identifier change is breaking for every existing agent, and
the options — hard cutover, or accepting both forms for one release with the old form logged
as deprecated — need a decision before any code moves.
