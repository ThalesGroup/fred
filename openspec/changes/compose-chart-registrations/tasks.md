## 1. Chart

- [x] 1.1 Add the `registrations` block (empty `applications` and `knowledgeBasePublishers`, with one commented example each) to `deploy/charts/fred/values.yaml`. Remove the frontend's default `FRONTEND_APPLICATIONS_JSON` entry, and the registration examples under the frontend's `env` and the control plane's `platform`. Verify `helm template` with the default values renders `application_sources: []`, `publishers: []` and `FRONTEND_APPLICATIONS_JSON: '[]'`
- [x] 1.2 Add the helper that derives the catalog entries, the gateway entries and the publishers from `registrations`. Merge the first and the last into the control plane's resolved application in `main.yaml`, and emit `FRONTEND_APPLICATIONS_JSON` after `env`/`extraEnvVars` in the frontend's Deployment. Verify with a render that the ConfigMap, the checksum annotation and the frontend's environment change together
- [x] 1.3 Add `fred.validate-registrations`, which refuses the control plane's `application_sources` and `publishers` and the frontend's `FRONTEND_APPLICATIONS_JSON`, with messages naming the `registrations` key. Verify each refusal with a render

## 2. Schema

- [x] 2.1 Extend `scripts/generate_chart_schema.py` to add the strict `registrations` schema, built from `ApplicationSourceConfig` without `app_id`, `KnowledgeBasePublisher` without `client_id`, and the `gateway` object. Regenerate `values.schema.json`. Verify `make check-chart-schema-drift` and `make check-chart-values` pass

## 3. Tests

- [x] 3.1 Add a render test of the fred chart (`scripts/check_chart_registrations.py`, a uv script like `check_chart_ingestion_workers.py` since it parses YAML; `make check-chart-registrations`, a step of the chart CI job), covering every `chart-registrations` scenario: two files compose, `null` removes an entry, default is empty, catalog and gateway agree, stable order, publisher, misspelled field, missing gateway, and each former value refused. Verify it passes, and fails if the derivation is removed

## 4. Docs and migration

- [x] 4.1 Update the registration guidance for chart deployments: `docs/swift/platform/FORKING_GUIDE.md` (example and checklist), `docs/swift/platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md` (how the chart composes registrations) and the `values.yaml` comments. Verify that no doc tells a chart operator to set `FRONTEND_APPLICATIONS_JSON` or `application_sources` in chart values
- [x] 4.2 In the in-flight `publish-pod-helm-charts` change, have the application chart's notes print one `registrations.applications.<app_id>` block. Verify `openspec validate publish-pod-helm-charts`
- [x] 4.3 Add the migration note (`impact: minor`: move each entry into `registrations` before upgrading; validation; rollback) and verify `make migration-check`

## 5. Close-out

- [x] 5.1 Run `helm lint`, the chart CI renders from `Check-pending-requests.yml`, `make pod-chart-tests` and `make check-chart-schema-drift`. Record the results here
  - 2026-10-21, on `53d9b0422` plus this change: `helm lint deploy/charts/fred` (0 failed); the CI render with the six image tags; `make pod-chart-tests` OK; `make check-chart-schema-drift` passed; `make check-chart-values` valid; `make check-chart-ingestion-workers` passed; `make check-chart-registrations` 7 tests OK, 4 of them failing on a copy of the chart without the derivation; `make migration-check` valid. `values-entra.example.yaml` renders. `values-gcp.yaml` fails the values schema on its storage blocks, identically on `53d9b0422` without this change; it is not rendered by CI
- [x] 5.2 Apply the branch audit procedure and obtain an independent read-only review. Record base/head, findings and dispositions in the PR
- [ ] 5.3 Open the draft PR `feat(#3211): compose chart registrations by id`, linking #3211, then reconcile, sync and archive this change once verified
