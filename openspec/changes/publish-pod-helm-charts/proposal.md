## Why

A pod built on Fred's libraries has one shape, defined by those libraries: an agent pod
reads `fred_runtime`'s `AgentPodConfig`, a Knowledge Base pod runs `fred-sdk`'s `run` and
`publish` commands and reads its `PodConfiguration`. Yet each satellite repository writes
its own chart for that shape (dt-agents, webdav-knowledge-base), or has none at all
(fred-samples' agents and Knowledge Bases, rags-agents inside the RAGS chart). Someone
deploying a pod on their own cluster has no official chart, no install command and no
statement of what must be configured. Applications (a UI image, an optional service) have the
same gap: Fred documents how to register one, not how to package it, so each provider
invents its chart (the evaluator) or ships raw manifests to edit by hand (fred-samples).

Tracking: https://github.com/ThalesGroup/fred/issues/3083
Gateway API follow-up: https://github.com/ThalesGroup/fred/issues/3187

## What Changes

- Fred publishes two generic charts next to `fred`, from `deploy/charts/agent-pod` and
  `deploy/charts/knowledge-base`, through the existing `Package-and-push-charts` workflow:
  `oci://ghcr.io/thalesgroup/fred-helm/{agent-pod,knowledge-base}`, released with Fred's
  `chart/v*` tags.
- A pod is deployed from them with its image and values only. The chart has no default
  image; `configuration` is the pod's configuration file, rendered verbatim.
- Each chart ships a `values.schema.json` that embeds the pod configuration schema
  generated from the library model (`AgentPodConfig`, `PodConfiguration`), so a wrong key
  in a pod's configuration fails at `helm install`, not at pod start.
- Each chart ships an install README (`helm show readme`): what it deploys, what Fred must
  provide, the required values, the credentials, the addresses, and how the pod is
  registered. `NOTES.txt` prints the registration to add to Fred's values.
- The agent-pod chart optionally renders a Gateway API HTTPRoute for the pod base URL, so
  operators can expose a pod through a shared Gateway without a separate manifest.
- The agent-pod chart starts from dt-agents' chart and the knowledge-base chart from
  webdav-knowledge-base's, the two most complete, with their repository-specific parts
  generalized or removed.
- Fred states the **application chart contract** in the FORKING_GUIDE: what an
  application's own chart must contain (UI and optional service, required `ui.hostOrigin`,
  credentials by reference, notes printing its `registrations` entry, values schema, README,
  `deploy/k3d/`), with fred-agent-evaluator's chart as the reference. Fred publishes no
  generic application chart: an application's service is arbitrary code.
- Out of this change: moving each satellite onto the charts or the contract (one change per
  repository, after the first publish), and Fred's own `fred-agents` (stays in the `fred`
  chart).

## Capabilities

### New Capabilities

- `pod-helm-charts`: the published, generic Helm charts for pods built on Fred's
  libraries — what they deploy, what they validate, how they are documented and released.
- `application-chart-contract`: what a Fred application's own Helm chart must provide so
  that any cluster can install and register it the same way.

### Modified Capabilities

None.

## Impact

- Fred: two new charts under `deploy/charts/`, the chart workflow matrix, the
  schema generation (`scripts/generate_chart_schema.py` or a sibling, `chart-schema.mk`),
  `deploy/charts/fred/README.md`, the FORKING_GUIDE's pod and application sections, an English
  migration note.
  No code, API or existing chart changes.
- Operators: optional. Nothing changes until a pod is deployed from the new charts.
- Satellites, afterwards: dt-agents and webdav-knowledge-base delete their charts;
  fred-samples' agents and Knowledge Bases, and rags-agents, gain one; fred-samples' three
  applications replace their raw `deploy.yaml` with charts that follow the contract, and the
  RAGS chart is checked against it. Each repository keeps its `deploy/k3d/` helmfile,
  pointing at its published chart.
