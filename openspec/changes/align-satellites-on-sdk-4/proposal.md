# Align the satellite repositories on fred-* 4.0.0

## Why

Three repositories build on Fred's published libraries — `fred-samples`,
`fred-rags`, `fred-agent-evaluator` — and each was frozen on a different PyPI
version, months behind the monorepo. `fred-core` ranged from 1.5.0 to 3.10.1
across seven consumers. Nothing forced them forward, so an SDK change was
untestable outside `fred` and drift accumulated silently.

Running all four repositories together exposed what the drift was hiding: every
`fred-runtime` pod reported the same KPI `service` label, so three pods collapsed
into one Grafana series and a log line could not be joined to its own KPI.

## What

`fred-core`, `fred-sdk` and `fred-runtime` move to **4.0.0 in lockstep**, and
every consumer floors on `>=4.0.0`. Each satellite gains a `[tool.uv.sources]`
override onto the monorepo checkout, so a library change is testable everywhere
without publishing first.

The major bump is earned, not cosmetic: `fred-runtime` now requires
`app.runtime_id`, and `fred-sdk` had already removed `GuardrailDefinition` — a
public symbol dropped between two *minor* versions, which this corrects.

**4.1.0 extends the same lockstep to a fourth library.** `fred-pod` holds the
pod floor — configuration, identity, naming — that every component needs just
to start, and `fred-core` moves out of `fred-sdk`'s base dependencies into a
new `agents` extra. A Knowledge Base pod then installs `fred-sdk[knowledge-base]`
and none of the agents platform; anything on the agent authoring surface
declares `fred-sdk[agents]>=4.1.0`.

## Impact

**Breaking at deploy time.** `app.runtime_id` is required with no default, so any
agent pod whose configuration lacks it fails to boot. The two configmap templates
in `fred-deployment-factory` (`gcp-c1/argocd/fred-apps/` and `gcp-c1/helm/`) do
not set it today. This blocks integration and production until fixed — see
`tasks.md`.

**Already incompatible, now visible.** `fred-rags/apps/rags-agents` cannot start
on the current SDK: `rags_agents/tessa/agent.py` imports `GuardrailDefinition`.
The override did not break it; it revealed it.

Out of scope: the `agent_id` naming convention, which is still an open design
question in `docs/swift/rfc/AGENT-ID-NAMING-RFC.md`.
