## Verified locally (helm v3, no cluster)

- `make generate-chart-schema` writes `deploy/charts/{agent-pod,knowledge-base}/values.schema.json`
  and leaves `deploy/charts/fred/values.schema.json` unchanged; a second run leaves no diff.
- `make check-chart-schema-drift` passes, and fails (exit 2) after a hand edit of
  `deploy/charts/agent-pod/values.schema.json`. `make check-config-schema-drift` passes in
  `libs/fred-sdk`.
- `make pod-chart-tests`: 9 tests pass — both charts render; a missing image tag, missing
  credentials, a misspelled configuration key (`runtim_id`, `prefx`) and a misspelled chart
  key (`replicas`) are refused with the offending name; an agent pod with M2M disabled needs
  no Secret; the agent-pod notes print the `runtime_catalog_sources` entry; `extraConfigFiles`
  are mounted under `/app/config/`; the knowledge-base `publish` Job is a post-install,
  post-upgrade, post-rollback hook and disappears with `publish.enabled: false`.
- `helm lint` passes on both charts with example values; each README's own example renders.
- `helm package` of both charts includes `README.md`, `values.schema.json` and `NOTES.txt`;
  with `--version 3.5.0` the package keeps `appVersion: 4.5.0`.
- Existing pod configurations validate against the strict schemas unchanged: dt-agents
  (chart defaults merged with its k3d values), webdav-knowledge-base (same), fred-samples'
  agents (`configuration_prod.yaml`), rags-agents (`configuration.yaml`,
  `configuration_prod.yaml`), fred-samples' git-repository and local-folder Knowledge Bases.
- fred-agent-evaluator's `deploy/charts/fred-evaluator` meets every point of the application
  chart contract (ClusterIP Services only, no Ingress, required and checked `ui.hostOrigin`,
  credentials refused when absent, notes printing both registration blocks with fully
  qualified addresses, strict values schema, README, `deploy/k3d/`).
- `make migration-check`: the note is valid. Workflows parse as YAML.

## Not verified

- The `Package-and-push-charts` workflow itself (runs on a `chart/v*` tag only).
- A real install on a cluster: the satellite moves, one per repository, deploy the charts on
  k3d with `make k3d-app` and are the first live evidence.
