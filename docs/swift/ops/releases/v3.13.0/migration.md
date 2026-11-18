# Migration guide - v3.13.0

Upgrade from: `code/v3.12.0`
Operational impact: **minor** (minimum version: `3.13.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Keep tabular trace details responsive

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.13.0/docs/swift/ops/migrations/3527-responsive-tabular-trace-details.md)

Existing JSON history remains readable; normal SDK/runtime/frontend deployment requires no schema migration or re-ingestion.

See the source note for applicability, validation and rollback.

## Bound tabular query output by characters and make row limits optional

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.13.0/docs/swift/ops/migrations/3537-bound-read-query-output.md)

### Applicability

Fred deployments exposing Knowledge Flow tabular tools, including API and worker
configuration sharing the tabular storage block.

### Prerequisites

Review deployment overlays and custom callers of read_query before upgrading.
No data migration or re-ingestion is required.

### Configuration

Remove `storage.tabular_store.query.max_rows` from backend configuration and chart
overlays. Replace it with `max_output_chars: 50000` to bound the compact JSON rows
array. Metadata and explanation text are additional. Set `default_max_rows: 500`
or another positive default. The character budget must be at least 2 characters.
The bundled chart values and GCP example contain the replacement settings.

### Upgrade

Update configuration and Knowledge Flow images together, then restart affected
pods using the normal deployment procedure. Keep settings consistent across API
replicas. Explicit `max_rows: null` now disables the tool-added row limit; callers
wanting the configured default must omit that argument. Positive integer requests
have no fixed row ceiling. SQL-authored LIMIT and execution guards still apply.

### Validation

Confirm startup accepts the new configuration. Query a dataset containing more
than 500 small rows: omission returns at most 500 with a possible-additional-rows
notice; explicit null can return more while respecting the character budget.
Query wide rows and check that only complete rows fit, with the tool-owned English
explanation after row data. An oversized first row must produce a truncation
explanation rather than a no-matches message. Check recorded chat details too.

### Rollback

Roll back images and configuration together. Restore the previous `max_rows`
ceiling and default if rolling back to an image requiring those settings. No
persisted tabular data changes need reversal.

### Limitations

The budget counts JSON characters, not tokens or bytes. Disabling the row limit
does not disable the character or engine execution budgets. Messages do not claim
a complete table count: without a row limit, reading stops on character overflow.
Existing recorded responses retain their historical contents.

## Configure the positional predict reranker provider

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.13.0/docs/swift/ops/migrations/3574-predict-reranker-provider.md)

### Applicability

Knowledge Flow deployments that want to use a model `:predict` endpoint for document reranking. Existing `rerank` and local CrossEncoder configurations continue to work without changes.

### Prerequisites

Use a Fred chart and Knowledge Flow image containing the `predict` provider. Confirm that the model endpoint accepts `POST /models/<name>:predict` with a `query` string and `documents` array and returns one positional numeric score per document.

### Configuration

Set `reranker_model` in both Knowledge Flow API and worker configuration:

```yaml
reranker_model:
  provider: predict
  name: example-model
  settings:
    base_url: https://models.example/v1
```

The adapter calls `POST https://models.example/v1/models/example-model:predict`, sends the selected reranker key in the `apikey` header, and maps `predictions` to the input documents by position. Supply `KNOWLEDGE_FLOW_RERANKER_API_KEY` or its `OPENAI_API_KEY` fallback through the existing environment secret. Keep keys out of model YAML. The existing `rerank` provider continues to use `POST {base_url}/rerank`, a bearer token, and indexed `results`.

### Upgrade

Deploy the compatible chart and image, set the model configuration, then restart the Knowledge Flow API and worker pods. The per-agent document access reranking switch remains off by default.

### Validation

From each environment, verify an authenticated predict request and a reranked document search with the switch enabled on a test agent. Check that the returned hits remain tied to their original documents, and that a remote failure returns `503 reranker_unavailable`. Do not log credentials or document content during validation.

### Rollback

Remove `reranker_model` from API and worker configuration and restart the affected pods to resume the local CrossEncoder. No data migration is needed.

### Limitations

The remote model is selected globally for Knowledge Flow. A remote failure does not fall back to local inference.

## Use neutral branding in Help Center articles

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.13.0/docs/swift/ops/migrations/3578-help-center-neutral-branding.md)

The updated articles are included in the frontend and require no action beyond normal deployment.

See the source note for applicability, validation and rollback.

## Attribute generated PowerPoint files to the acting user

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.13.0/docs/swift/ops/migrations/3580-powerpoint-author.md)

New downloads use the existing authenticated identity without changing stored templates, APIs, permissions, or existing files. Normal deployment is sufficient.

See the source note for applicability, validation and rollback.

## Preserve icons and carousel styles during browser translation

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.13.0/docs/swift/ops/migrations/3584-browser-translation-ui.md)

### Applicability

Deployments with custom themes targeting the featured carousel by ARIA role description.

### Prerequisites

Access to the custom theme source and its normal deployment procedure.

### Configuration

No application configuration changes are required.

### Upgrade

In custom theme CSS, replace `section[aria-roledescription="carousel"]` with
`section[data-featured-carousel]` and `article[aria-roledescription="slide"]`
with `article[data-featured-slide]`. Deploy the updated theme with the frontend.
Themes that do not use those selectors need no changes.

### Validation

Enable browser page translation and verify carousel backgrounds, colors, and icons.

### Rollback

Roll back the frontend and theme together; restore the previous selectors in the
theme when returning to a frontend that does not expose the data attributes.

### Limitations

Custom themes are maintained outside Fred and are not automatically rewritten.

## Advanced home page with admin-chosen featured agents

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.13.0/docs/swift/ops/migrations/home-featured-agents.md)

### Applicability
Existing deployments upgrading the control-plane and frontend.

### Prerequisites
Normal control-plane database migration privileges.

### Configuration
No configuration changes are required. Themes may optionally set the
`--home-*` CSS variables documented in the frontend README.

### Upgrade
Use the normal deployment procedure and control-plane Alembic upgrade.
Revision `e3a9c41f7b62` adds `platform_ui_settings.home_layout` (default
`classic`), `platform_ui_settings.home_ask_agent_instance_id` (nullable) and
the `platform_home_featured_agent` table. The home page is
unchanged until a platform admin selects the advanced home.

### Validation
In Administration > Interface, choose the advanced home and add a default-team
agent and a question field agent, then save. Home shows the featured banner
and the question field; a question opens a new conversation with the question
field agent and is sent once.

### Rollback
Roll back application code normally; old code ignores the new column and
table. If explicitly downgrading the schema, stop the new application first,
then run the ordinary Alembic downgrade. Featured agents, the question field
agent and the chosen mode will be lost.

### Limitations
Only agents of the platform default teams can be featured or receive the home
question. Such an agent that becomes disabled, suspended or leaves the default
teams is hidden from users until it is usable again.

## Set the page language from the displayed language from first load

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.13.0/docs/swift/ops/migrations/html-lang-follows-displayed-language.md)

The fix ships in the frontend bundle and its static boot script; no data, API or deployment step changes.

See the source note for applicability, validation and rollback.

## Show Alembic migration heads in Fred release descriptions

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.13.0/docs/swift/ops/migrations/release-alembic-head-inventory.md)

The section is generated from the tagged source in GitHub release descriptions; existing deployments upgrade normally without extra actions.

See the source note for applicability, validation and rollback.

## Prepare Fred v3.13.0 release and account for maintenance updates

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.13.0/docs/swift/ops/migrations/release-v3-13-0-preparation.md)

The mail-parser update is installed with the normal Knowledge Flow image, and the README and release metadata changes require no deployment action.

See the source note for applicability, validation and rollback.

## Show featured agent highlights on the advanced home

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.13.0/docs/swift/ops/migrations/3586-featured-highlights.md)

Existing highlights are already stored and served; the fix takes effect with a normal frontend deployment.

See the source note for applicability, validation and rollback.
