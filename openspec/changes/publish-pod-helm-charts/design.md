## Context

See proposal.md for the motivation. What exists:

- `deploy/charts/fred` is published by `Package-and-push-charts.yml` on `chart/v*` tags to
  `oci://ghcr.io/thalesgroup/fred-helm/fred`; the workflow already iterates a matrix of charts.
- `scripts/generate_config_schema.py` turns a Pydantic model into a strict JSON schema
  (`additionalProperties: false` everywhere); `scripts/generate_chart_schema.py` embeds the
  backends' schemas into the `fred` chart's `values.schema.json`, and CI fails on drift
  (`Check-config-schema.yml`). `Check-pending-requests.yml` already runs `helm template` on
  the `fred` chart for every PR.
- The two most complete pod charts live outside Fred: dt-agents' (Deployment, Service,
  optional Ingress, configuration ConfigMap, metrics port, catalog files) and
  webdav-knowledge-base's `knowledge-base` (the `run` Deployment, a `publish` Job hook,
  metrics Service and ServiceMonitor, M2M Secret, an extra CA bundle).
- An agent pod reads `fred_runtime.app.AgentPodConfig`; a Knowledge Base pod reads
  `fred_sdk.knowledge_base.configuration.PodConfiguration` and offers exactly two commands,
  `run` and `publish`. Agent pods are registered in Fred through the Control Plane's
  `runtime_catalog_sources`; a Knowledge Base registers itself with `publish`.

## Goals / Non-Goals

**Goals:** one official chart per kind of pod, validated against the library's own
configuration model, documented for an operator who has never seen Fred's repositories.

**Non-Goals:** deploying Fred's own `fred-agents` from `agent-pod` (it stays in the `fred`
chart); Kubernetes-label discovery of pods (`AGENTIC-POD-RFC.md` proposes it,
the code registers pods through `runtime_catalog_sources`, and the charts follow the code).

## Decisions

**Two charts, one per kind of pod.** An agent pod is a server behind a Service; a Knowledge
Base pod is a worker plus a publish Job. One chart for both would be mostly conditionals.
A Helm library chart was considered: every pod would still publish its own wrapper chart, so
the number of charts to keep uniform would not drop.

**In Fred, released with Fred's chart tags.** The schemas the charts embed come from Fred's
libraries, so they change together; one tag, one pipeline (a matrix entry each). The
chart's `appVersion` records the version of Fred's libraries whose configuration model the
schema embeds (4.5.0 today), which is the compatibility a pod author needs: a pod built on
libraries of that version validates. `make set-version` and `make libs-version` keep them
current.

**The schema embeds the library model, strictly.** The values schema's `configuration` is the
generated schema of `AgentPodConfig` or `PodConfiguration`, generated with the existing
script and checked for drift by the existing workflow. One exception follows the SDK's own
contract: `PodConfiguration.load()` builds the subclass it is called on, and a Knowledge Base
adds its own section to the same file (webdav's `webdav:`), so the knowledge-base schema
leaves the top level of `configuration` open while every SDK section stays strict. No agent
pod extends `AgentPodConfig`; agent-pod stays strict throughout, and a pod's other files go
in `extraConfigFiles`.

**No default image.** The chart deploys someone else's image: `image.repository` and
`image.tag` are `required`, which also keeps the chart free of any pod's name.

**Credentials as in the other Fred charts.** `secret.existingSecret` (mounted with
`envFrom`) and `extraEnvVars` (`valueFrom.secretKeyRef`), the pattern of the `fred` and
`fred-evaluator` charts. `secret.create` is kept for tests. webdav's `m2mSecret.key` form and
its CA bundle become `extraEnvVars`, `extraVolumes` and `extraVolumeMounts`.

**What becomes generic.** dt-agents' `modelsCatalog` and `mcpCatalog` become
`extraConfigFiles` (a map of file name to content, mounted under `/app/config/`); the
container command is the image's own (agent pods) or `run`/`publish` (Knowledge Bases);
the metrics port is read from `configuration.observability.kpi.prometheus`.

**Gateway API exposure is opt-in.** The agent-pod chart keeps Ingress support and adds an
HTTPRoute using the existing canonical base path and Service. Operators supply Gateway
parent references and hostnames, with an optional request timeout for streaming. The
route is absent by default, so current releases are unchanged.

**Applications get a contract, not a chart.** Only the UI half of an application has a fixed
shape; the service is the provider's code, with its own workers, migrations, databases or
agents (the evaluator has a Temporal worker and migrations, review-board its own agents). A
generic `application` chart would have to expose every Kubernetes knob, carry nothing
Fred-specific beyond the registration notes, and be outgrown by the first worker. What is
Fred's to state is the contract the provider's chart meets, written as a subsection of the
FORKING_GUIDE's "Your own applications" after step 3, pointing at fred-agent-evaluator's chart
as the worked example (its README, schema and notes already follow it).

**Tests.** Offline, in the style of `deploy/k3d/test_*.py`: render each chart with
`helm template` for the required-value failures, a schema rejection, the registration notes
and the publish Job; run them where the `fred` chart is already rendered in CI.

## Risks / Trade-offs

- [A breaking change to a configuration model breaks the chart for older pods] → the chart's
  `appVersion` names the library version; a pod stays on the chart release matching its
  libraries until it moves.
- [The strict schema refuses a key a pod reads but the model does not declare] → by design for
  agent pods (the error names the key; `extraConfigFiles` holds pod-specific files). For a
  Knowledge Base, a misspelled optional SDK section name at the top level (`observabilty`)
  passes; a misspelled required one is still refused, and keys inside SDK sections are checked.
- [ghcr.io is public; Thales-internal pods use internal registries] → the charts hold no
  registry: `image.repository` and `imagePullSecrets` are the operator's.

## Migration Plan

Additive: nothing changes for existing releases. After the first `chart/v*` release carrying
the charts, each satellite moves in its own change: its `deploy/k3d/helmfile.yaml.gotmpl`
points at the published chart, its values move under the generic keys, its own chart is
deleted (dt-agents, webdav-knowledge-base) or never written (fred-samples, rags-agents).
Applications move to the contract the same way: fred-samples' `deploy.yaml` files become
charts, the RAGS chart is checked against it.
Rollback: keep the satellite's previous chart until its move is verified on k3d.
