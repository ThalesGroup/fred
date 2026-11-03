## Why

Registering an application or a Knowledge Base publisher with Fred's chart means editing three values that do not compose: `application_sources` and `knowledge_bases.publishers` in the control plane's configuration (lists), and `FRONTEND_APPLICATIONS_JSON` (a JSON string inside the frontend's `env` list). Helm replaces lists. So every values file that adds one entry must restate all the others. Two applications' files cannot be combined. Redeploying without one file silently unregisters its application. The two halves of an application's registration share only `app_id`, and are kept in sync by hand.

Tracking: https://github.com/ThalesGroup/fred/issues/3211

## What Changes

- Add a top-level `registrations` value to the fred chart. `registrations.applications.<app_id>` holds the catalog entry together with its `gateway` upstreams. `registrations.knowledgeBasePublishers.<client_id>` holds a publisher's `prefix`. Helm merges maps, so any number of values files compose, and `null` removes an entry.
- The chart derives the three registrations from it: the control plane's `platform.application_sources` and `knowledge_bases.publishers`, and the frontend's `FRONTEND_APPLICATIONS_JSON`. Rendering is deterministic, ordered by key.
- **BREAKING**: the chart refuses to render if values still set the control plane's `application_sources` or `knowledge_bases.publishers`, or set `FRONTEND_APPLICATIONS_JSON` in the frontend's `env` or `extraEnvVars`. The message names the `registrations` key to use instead. The chart's default `FRONTEND_APPLICATIONS_JSON: "[]"` entry is removed.
- The values schema validates `registrations` strictly: the entry fields of the control plane's own models (without the map key), plus the gateway fields the frontend accepts.
- Docker Compose, the backends' configuration models and the frontend container are unchanged: the control plane still reads its lists, and the container still reads `FRONTEND_APPLICATIONS_JSON`.

## Capabilities

### New Capabilities

- `chart-registrations`: how the fred chart takes the applications and Knowledge Base publishers a deployment serves, and derives the control plane's and the frontend gateway's registrations from them.

### Modified Capabilities

None. `frontend-application-hosting` and the in-flight `knowledge-base-publication` capability keep their requirements. What they consume is unchanged.

## Impact

- `deploy/charts/fred`: `values.yaml` (the new `registrations` block and its documentation; the frontend's default `FRONTEND_APPLICATIONS_JSON` entry and the registration examples removed), the control plane's ConfigMap and the frontend's Deployment templates, and a guard template.
- `scripts/generate_chart_schema.py` and the regenerated `values.schema.json`.
- A render test of the fred chart, run with the existing chart tests.
- Docs that tell an operator to register through `FRONTEND_APPLICATIONS_JSON` or `application_sources` in chart values. The in-flight `publish-pod-helm-charts` requirement, which has an application chart print both registration blocks, becomes one `registrations.applications.<app_id>` block.
- A migration note (`impact: minor`): operators move their entries into `registrations` before upgrading. Customer overlays are affected, the Thales one included.
- fred-deployment-factory can then drop its workaround, which rebuilds these lists from ConfigMaps: each application's entry becomes a values file. That follow-up lands once a chart with this change is published.
