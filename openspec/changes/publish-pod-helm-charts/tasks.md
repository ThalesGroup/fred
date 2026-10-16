## 1. Configuration schemas

- [x] 1.1 Generate the strict schemas of `fred_runtime.app.AgentPodConfig` and `fred_sdk.knowledge_base.configuration.PodConfiguration` with `scripts/generate_config_schema.py`, wired into `chart-schema.mk` next to the `fred` chart's; verify `make generate-chart-schema` writes both and a second run leaves `git diff` empty
- [x] 1.2 Extend the drift check to the two pod charts' `values.schema.json`; verify `make check-chart-schema-drift` fails after a hand edit of either and passes after regeneration

## 2. agent-pod chart

- [x] 2.1 Create `deploy/charts/agent-pod` from dt-agents' chart: Deployment, Service, optional Ingress, ConfigMap with `configuration` and `extraConfigFiles`, metrics port from `configuration.observability.kpi.prometheus`, `secret`/`extraEnvVars`, required `image.repository`/`image.tag`, no pod-specific name; verify `helm lint` and a `helm template` with a minimal values file
- [x] 2.2 Write its `values.schema.json` around the generated `AgentPodConfig` schema; verify a misspelled `configuration` key and a misspelled top-level key are both refused
- [x] 2.3 Write `NOTES.txt` printing the `runtime_catalog_sources` entry (runtime id, Service base URL, ingress prefix); verify the rendered notes for a sample release
- [x] 2.4 Write its README (install from OCI, what Fred must provide, required values, credentials, addresses, registration, k3d); verify `helm show readme` on the packaged chart

## 3. knowledge-base chart

- [x] 3.1 Create `deploy/charts/knowledge-base` from webdav-knowledge-base's chart: `run` Deployment, `publish` Job hook (install, upgrade, rollback; `publish.enabled`), metrics Service and optional ServiceMonitor, `secret`/`extraEnvVars`, `extraVolumes`/`extraVolumeMounts` replacing the WebDAV CA block, required image; verify `helm lint` and `helm template`
- [x] 3.2 Write its `values.schema.json` around the generated `PodConfiguration` schema; verify the same two refusals as 2.2
- [x] 3.3 Write its README and `NOTES.txt` on the same outline as 2.4; verify `helm show readme`

## 4. Release and checks

- [x] 4.1 Add both charts to the `Package-and-push-charts.yml` matrix and to the release body; verify the workflow YAML parses and each matrix entry packages locally with `helm package`
- [x] 4.2 Set each chart's `appVersion` to the libraries' version in `make set-version`/`make libs-version`; verify `make libs-version-tests` and a dry run of both targets
- [x] 4.3 Add offline render tests (required image, credentials refusal, schema refusal, registration notes, publish Job) in the style of `deploy/k3d/test_*.py`, and render both charts in the PR chart check; verify the tests pass locally

## 5. Documentation and close-out

- [x] 5.1 Describe the two charts in `deploy/charts/fred/README.md` and replace the FORKING_GUIDE pod section's manual wiring with them; verify no doc still tells a pod author to write a chart
- [x] 5.2 Add the application chart contract as a "Package it as a chart" subsection after step 3 of the FORKING_GUIDE's "Your own applications", pointing at fred-agent-evaluator's chart; verify each requirement of `specs/application-chart-contract` is stated there and that the evaluator chart meets every point
- [x] 5.3 Add the migration note (`impact: none`, additive charts) and run `make migration-check`
- [ ] 5.4 Record verification evidence in this change, open the PR linking the GitHub issue, and list the satellite follow-ups (dt-agents, webdav-knowledge-base, fred-samples agents, Knowledge Bases and applications, rags-agents and the RAGS chart) on the issue
