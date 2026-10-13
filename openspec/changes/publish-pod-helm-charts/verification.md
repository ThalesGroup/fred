## Verified locally (helm v3, no cluster)

- `make generate-chart-schema` writes `deploy/charts/{agent-pod,knowledge-base}/values.schema.json`
  and leaves `deploy/charts/fred/values.schema.json` unchanged; a second run leaves no diff.
- `make check-chart-schema-drift` passes, and fails (exit 2) after a hand edit of
  `deploy/charts/agent-pod/values.schema.json`. `make check-config-schema-drift` passes in
  `libs/fred-sdk`.
- `make pod-chart-tests`: 14 tests pass with no reachable cluster (`KUBECONFIG=/nonexistent`) — both charts render; a missing image tag, missing
  credentials, a misspelled configuration key (`runtim_id`, `prefx`) and a misspelled chart
  key (`replicas`) are refused with the offending name; an agent pod with M2M disabled needs
  no Secret; the agent-pod notes print the `runtime_catalog_sources` entry; `extraConfigFiles`
  are mounted under `/app/config/`; the knowledge-base `publish` Job is a post-install,
  post-upgrade, post-rollback hook and disappears with `publish.enabled: false`; a metrics
  port on a loopback address (the libraries' default) is refused, and the port defaults to 9000;
  `extraEnvVars` without the variable `security.m2m.secret_env_var` names is refused; a
  non-canonical agent `base_url` (`foo`, `/foo/`, `/a//b`, `/a/../b`) is refused; a 64-character
  image tag renders (no version label); a Knowledge Base's own top-level section passes.
- `helm lint` passes on both charts with example values; each README's own example renders.
- `helm package` of both charts includes `README.md`, `values.schema.json` and `NOTES.txt`;
  with `--version 3.5.0` the package keeps `appVersion: 4.5.0`.
- Existing pod configurations validate against the schemas: dt-agents and
  webdav-knowledge-base (each chart's defaults merged with its k3d values; dt-agents also with
  its k3d `extraEnvVars` as the only credential source), webdav's full `configuration.yaml`
  with its `webdav:` section, rags-agents'
  `configuration.yaml`, fred-samples' git-repository and local-folder Knowledge Bases.
  fred-samples' agents and rags-agents' `configuration_prod.yaml` are refused only for their
  host-run metrics address (127.0.0.1); their chart values set 0.0.0.0.
- fred-agent-evaluator's `deploy/charts/fred-evaluator` meets every point of the application
  chart contract (ClusterIP Services only, no Ingress, required and checked `ui.hostOrigin`,
  credentials refused when absent, notes printing both registration blocks with fully
  qualified addresses, strict values schema, README, `deploy/k3d/`).
- `make migration-check`: the note is valid. Workflows parse as YAML.

## Not verified

- The `Package-and-push-charts` workflow itself (runs on a `chart/v*` tag only).
- A real install on a cluster: the satellite moves, one per repository, deploy the charts on
  k3d with `make k3d-app` and are the first live evidence.
