# Migration guide - v3.9.0

Upgrade from: `code/v3.8.0`
Operational impact: **minor** (minimum version: `3.9.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Delegate Platform Access administration

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.0/docs/swift/ops/migrations/delegate-platform-access-and-team-management.md)

### Applicability

Existing Fred deployments upgrading to this release. The default
`sync_schema_on_init: true` publishes the updated model at control-plane startup.
Deployments with `sync_schema_on_init: false` and a pinned
`authorization_model_id` must update their model and pinned ID manually.

### Prerequisites

For pinned-model deployments, publish this release's
`libs/fred-core/fred_core/security/rebac/schema.fga.json` to OpenFGA and capture
the new model ID before deploying the new control plane and frontend.

### Configuration

No chart key or default changes. For pinned-model deployments, set the existing
`authorization_model_id` to the new model ID before deploying the new services.

### Upgrade

For pinned-model deployments, publish and pin the new model before the coordinated
rollout. With the default automatic synchronization, the new control plane writes
the model at startup; start it before relying on the delegated permissions in the
frontend. Complete the other release prerequisites before rolling out services.
Existing role tuples and Free links remain valid. No delegated role is assigned automatically.
A platform administrator may grant `platform_access_manager` after deployment.

### Validation

Grant `platform_access_manager` to a test user and confirm they can manage
filtering, the whitelist and a Free link while being denied unrelated admin
routes. Grant `team_manager` to another test user and confirm they can create
and list teams while registry editing and Free links are denied.

### Rollback

Roll back the application before reverting the OpenFGA model. Pinned-model
deployments can then restore the previous `authorization_model_id`. The added
model relations are inert to the older application, and no data migration is needed.

### Limitations

The new role does not grant team content or member administration.

## Stable local k3d image tags

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.0/docs/swift/ops/migrations/k3d-runtime-content-tags.md)

The normal local deployment command generates and imports the new tags automatically.

See the source note for applicability, validation and rollback.

## Fred chart: register applications and Knowledge Base publishers by id, under registrations

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.0/docs/swift/ops/migrations/3211-compose-chart-registrations.md)

### Applicability

Deployments of the fred chart whose values register an application (`applications.control-plane-backend.configuration.platform.application_sources`, or `FRONTEND_APPLICATIONS_JSON` in `applications.frontend.env` or `extraEnvVars`) or a Knowledge Base publisher (`applications.control-plane-backend.configuration.knowledge_bases.publishers`). Docker Compose configuration is unchanged. The knowledge-base chart's install notes and README now print the `registrations.knowledgeBasePublishers` entry to add.

### Prerequisites

The overlay values that register applications and publishers, to rewrite before the upgrade.

### Configuration

Move each `application_sources` item to `registrations.applications.<app_id>`: the item without its `app_id`, plus a `gateway` holding that application's `FRONTEND_APPLICATIONS_JSON` entry without its `app_id` (`ui_upstream`, and `service_upstream`, `service_required` when set). Move each publisher to `registrations.knowledgeBasePublishers.<client_id>: {prefix: <prefix>}`. Then delete the former keys, and the `FRONTEND_APPLICATIONS_JSON` entry of the frontend's env:

```yaml
registrations:
  applications:
    acme-forecast:
      ui_prefix: /apps/acme-forecast
      version: 1.0.0
      display_name: { en: "Forecast" }
      description: { en: "Demand forecasting." }
      gateway:
        ui_upstream: http://acme-forecast-ui.acme-apps.svc.cluster.local:80
        service_upstream: http://acme-forecast-api.acme-apps.svc.cluster.local:8000
        service_required: true
  knowledgeBasePublishers:
    kb-acme: { prefix: acme.kb }
```

These are maps, so each application's entry can live in its own values file. A later file sets an entry to `null` to remove it.

### Upgrade

Rewrite the values as above, then deploy Fred normally. A chart render that still finds a former key fails and names its `registrations` replacement, before any resource changes.

### Validation

Render the chart with the rewritten values (`helm template`). The control plane's ConfigMap lists the same `application_sources` and `publishers` as before the upgrade, and the frontend's `FRONTEND_APPLICATIONS_JSON` the same gateway entries, ordered by id. After deployment, each team's Apps page shows the same applications.

### Rollback

Restore the previous chart with the previous values. The rendered configuration is the same, so no data or state is involved.

### Limitations

The chart validates each entry's fields. Their consumers still check at start what the schema does not: the control plane refuses a reserved `app_id` and overlapping publisher prefixes, and the frontend container refuses an upstream that is not an origin and `service_required: true` without `service_upstream`. `null` in a later values file removes a whole entry, not one of its fields.

## Restore correlated exception tracebacks and separate duplicate filtering

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.0/docs/swift/ops/migrations/3190-correlated-exception-logging.md)

### Applicability

Fred Python APIs and workers using the updated shared `fred-core` library, including external library consumers. Request-boundary diagnostics apply to APIs using `RequestLoggingFastAPI`.

### Prerequisites

Review deployment log rules that match the former fixed server diagnostic message or assume request exception traces use the `uvicorn.error` logger.

### Configuration

No configuration changes are required. Existing `app.log_format` selects JSON or readable stdout. Exception visibility is independent of either delegation switch.

### Upgrade

Deploy the updated backend/worker images normally. Update affected log rules to match `fred_core.logs.http` for uncaught request exception diagnostics and `http` for HTTP completion. Both retain the same available admitted user/session/agent/team and request/correlation references. Unreported server failures still use their server logger.

Ordinary exception text and traceback frames now appear in stdout. Known token query values and free-access/join-link secrets are redacted, including in exception causes. This replaces blanket suppression with targeted redaction; it does not guarantee removal of arbitrary sensitive text embedded in exceptions. Apply the deployment's log access and retention policy to that diagnostic output. Audit and dependency restrictions are unchanged.

### Validation

Trigger an uncaught synthetic request failure in a non-production environment. Filter by its response's request/correlation IDs and admitted business references: one ERROR from `fred_core.logs.http` must contain the traceback, and one ERROR from `http` must contain status 500, route, duration and outcome. There must be no duplicate Uvicorn exception event for that failure. Verify that an unreported server error remains visible and a known URL token is redacted even when present only in an exception cause.

The local regression suite exercises the actual Knowledge Flow factory and Uvicorn over a Unix socket in all three delegation settings. Live GKE collection remains a deployment validation step.

### Rollback

Deploy the previous shared-library/backend/worker images and restore any rules changed for the new logger/messages. No data migration is involved. Rollback restores the previous traceback suppression and its diagnostic limitations.

### Limitations

This change does not recover old tracebacks, change the optional generic log store, deduplicate arbitrary application log-and-rethrow code, or add HTTP business context to startup, shutdown or WebSocket failures. Identity that has not been admitted/resolved is not invented. Existing runtime support-reference diagnostics remain separate.

## Relay binary bodies between hosted applications and their services

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.0/docs/swift/ops/migrations/3195-hosted-application-binary-bodies.md)

The host announces the new capability by itself and applications without the matching SDK keep the text transport, so a normal frontend deployment is enough.

See the source note for applicability, validation and rollback.

## Refresh Free link management when opened

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.0/docs/swift/ops/migrations/3227-free-link-management-refresh.md)

APIs, data and permissions are unchanged; normal frontend deployment applies the fix.

See the source note for applicability, validation and rollback.

## Recover the UI from stale code chunks after a deploy

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.0/docs/swift/ops/migrations/frontend-stale-chunk-reload.md)

The new cache headers and the one-time reload ship inside the frontend image and take effect with a normal rollout; no data, API or configuration changes.

See the source note for applicability, validation and rollback.

## Prepare Fred v3.9.0 and audit dependency updates

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.0/docs/swift/ops/migrations/prepare-v3-9-0-release.md)

The covered dependency updates need no configuration or data migration; normal deployment includes them.

See the source note for applicability, validation and rollback.

## Keep the slash-command menu open while a command is typed

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.9.0/docs/swift/ops/migrations/ui-slash-menu-flicker.md)

The chat composer's command menu no longer remounts on each keystroke; nothing to configure or migrate.

See the source note for applicability, validation and rollback.
