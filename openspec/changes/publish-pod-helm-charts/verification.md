## Verified locally (helm v3, no cluster)

- `make generate-chart-schema` writes `deploy/charts/{agent-pod,knowledge-base}/values.schema.json`
  and leaves `deploy/charts/fred/values.schema.json` unchanged; a second run leaves no diff.
- `make check-chart-schema-drift` passes, and fails (exit 2) after a hand edit of
  `deploy/charts/agent-pod/values.schema.json`. `make check-config-schema-drift` passes in
  `libs/fred-sdk`.
- `make pod-chart-tests`: 10 tests pass with no reachable cluster (`KUBECONFIG=/nonexistent`) — both charts render; a missing image tag, missing
  credentials, a misspelled configuration key (`runtim_id`, `prefx`) and a misspelled chart
  key (`replicas`) are refused with the offending name; an agent pod with M2M disabled needs
  no Secret; the agent-pod notes print the `runtime_catalog_sources` entry; `extraConfigFiles`
  are mounted under `/app/config/`; the knowledge-base `publish` Job is a post-install,
  post-upgrade, post-rollback hook and disappears with `publish.enabled: false`; a metrics
  port on a loopback address (the libraries' default) is refused, and the port defaults to 9000.
- `helm lint` passes on both charts with example values; each README's own example renders.
- `helm package` of both charts includes `README.md`, `values.schema.json` and `NOTES.txt`;
  with `--version 3.5.0` the package keeps `appVersion: 4.5.0`.
- Existing pod configurations validate against the strict schemas: dt-agents and
  webdav-knowledge-base (each chart's defaults merged with its k3d values), rags-agents'
  `configuration.yaml`, fred-samples' git-repository and local-folder Knowledge Bases.
  fred-samples' agents and rags-agents' `configuration_prod.yaml` are refused only for their
  host-run metrics address (127.0.0.1); their chart values set 0.0.0.0.
- fred-agent-evaluator's `deploy/charts/fred-evaluator` meets every point of the application
  chart contract (ClusterIP Services only, no Ingress, required and checked `ui.hostOrigin`,
  credentials refused when absent, notes printing both registration blocks with fully
  qualified addresses, strict values schema, README, `deploy/k3d/`).
- `make migration-check`: the note is valid. Workflows parse as YAML.

## Open

- webdav-knowledge-base extends `PodConfiguration` with a `webdav:` section, which the SDK's
  `PodConfiguration.load()` supports; the strict knowledge-base schema refuses it. To decide
  on the PR: open the top level of `configuration` for pod-owned sections (SDK sections stay
  strict), or keep it strict and move webdav's settings out of the file.

## Not verified

- The `Package-and-push-charts` workflow itself (runs on a `chart/v*` tag only).
- A real install on a cluster: the satellite moves, one per repository, deploy the charts on
  k3d with `make k3d-app` and are the first live evidence.
