# Migration guide - v3.7.0

Upgrade from: `code/v3.6.1`
Operational impact: **minor** (minimum version: `3.7.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Discover corpus spreadsheets and conversation attachments together

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.7.0/docs/swift/ops/migrations/3007-tabular-conversation-discovery.md)

Deploy the matching Knowledge Flow and runtime images normally; no stored-data migration or new setting is required.

See the source note for applicability, validation and rollback.

## Align agent form tests with model reads and required usage

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.7.0/docs/swift/ops/migrations/3044-agent-form-test-fixtures.md)

No shipped application code or data changes; the correction only restores isolated test setup.

See the source note for applicability, validation and rollback.

## Restore accent-insensitive user search on SQLite

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.7.0/docs/swift/ops/migrations/3086-sqlite-accent-search.md)

Existing data, APIs and search semantics are preserved; normal deployment applies the SQLite query fix.

See the source note for applicability, validation and rollback.

## Explicit whitelist refresh with durable removal history

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.7.0/docs/swift/ops/migrations/3140-t0-refresh.md)

### Applicability

Authenticated deployments using platform admission administration. Normal admission and the initial import retain their behavior; administrators can explicitly refresh completed T0 imports with filtering on or off.

### Prerequisites

Use the shared PostgreSQL authority and the normal control-plane migration credentials. Schedule the schema upgrade before deploying new admission readers or writers.

### Configuration

No configuration changes. The existing administrator permission controls both refresh modes. No import runs at startup, on upgrade or on activation.

### Upgrade

1. Run the normal control-plane `make db-upgrade`. Revision `d4e8b2a6f091` creates `platform_access_removals` and adds `platform_access_settings.t0_removal_history_complete`.
2. Upgrade participating services and the frontend. New readers require the migrated settings column; control-plane administration requires the history table.
3. Optional feature use: with filtering on or off, open Users and select the small refresh icon beside the completed import status. With reliable history, choose preservation or inclusion and confirm.

A completed import from an older version has no reliable removal history. Its next refresh requires inclusion and explicitly warns that the entire T0 whitelist is recalculated and manually removed people can regain access. Confirming that full import establishes the new baseline and enables preservation for future refreshes. Existing grants and provenance are retained. No historical reconstruction is required for legacy test data.

### Validation

After a normal initial import, remove a test exception and introduce a new test identity in the configured directory. Preservation must add the newcomer without restoring the recorded removal. Inclusion must warn before allowing that removed candidate to be re-added. Verify that refresh remains available with filtering active and leaves the switch active. In a legacy test environment, verify the missing-history warning and forced inclusion, then the availability of both modes after success. Each committed refresh emits one audit summary with mode and actual additions.

### Rollback

Roll back application code while retaining the additive schema and existing grants. Old code does not record removals. If any revocation occurs under old code, before returning to the new version set `t0_removal_history_complete = false` for settings row `id = 1` using the normal operator database procedure; the next explicit refresh must establish a new baseline. Do not drop history if preserving recorded removals is required. Downgrading the migration drops that protection and cannot undo access granted by a refresh.

### Limitations

Preservation protects recorded individual removals, not suspension or independent rule/team sources. Inclusion adds missing T0 candidates rather than deleting other grants. Directory changes between preview and confirmation can change the final added count. An unavailable directory or stale policy/completion fails without partial additions. Identities not known to the configured directory are not imported.

## The fred chart documents app.gcu_version (terms of use)

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.7.0/docs/swift/ops/migrations/3147-chart-gcu-version.md)

The default stays null, so the rendered configuration behaves as before; deployments that already set gcu_version keep their value.

See the source note for applicability, validation and rollback.

## Honor saved document source settings in tabular tools

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.7.0/docs/swift/ops/migrations/3151-tabular-document-source-settings.md)

Existing agent settings take effect after normal deployment; no data migration, re-ingestion or manual update is needed.

See the source note for applicability, validation and rollback.

## Make Chroma an optional Knowledge Flow dependency

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.7.0/docs/swift/ops/migrations/3157-optional-chroma.md)

### Applicability

Knowledge Flow API and worker deployments. The standard production image no
longer includes Chroma or dependencies used exclusively by it.

### Prerequisites

Check `storage.vector_store.type` before upgrading. Deployments using OpenSearch,
pgvector or another non-Chroma backend can use the standard image as before.

### Configuration

No YAML keys, secrets or chart schemas change. For Chroma, retain the existing
`local_path`, `collection_name` and persistent volume mounts.

### Upgrade

Deploy normally for non-Chroma backends. Deployments using Chroma must install
the `chroma` extra or build the `INSTALL_CHROMA=true` image variant for their API
and workers, following the [installation instructions](https://github.com/ThalesGroup/fred/blob/code/v3.7.0/apps/knowledge-flow-backend/README.md#optional-chroma-storage).
The default developer workflow continues to include Chroma. No reindexing or
data migration is required.

### Validation

Check the installed packages in the final image. The default image must not
contain `chromadb`; non-Chroma API and workers must start normally. In the
opt-in variant, search an existing local document, ingest a document, restart
and verify its chunks remain searchable, then delete it.

### Rollback

Restore the previous image and keep the existing configuration and volumes.
This can reintroduce Chroma-related vulnerabilities into the production image.

### Limitations

This removes an unused dependency from the default image, not vulnerabilities
from Chroma itself. Optional installations and lockfile scans can still report
them. Unrelated shared dependencies and OS vulnerabilities remain visible.

## Make PyMuPDF explicitly optional for PDF processing

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.7.0/docs/swift/ops/migrations/3159-optional-pymupdf.md)

### Applicability

Knowledge Flow API and all ingestion workers, including separate fast, medium
and rich extraction deployments. No database or stored-document migration.

### Prerequisites

Inspect all `processing.profiles.*.input_processors` and `pdf.extractor` values,
including profiles not selected by `default_profile`. Decide whether to use
the standard distribution or retain the explicit PyMuPDF family.

### Configuration

Follow the [installation guide](https://github.com/ThalesGroup/fred/blob/code/v3.7.0/apps/knowledge-flow-backend/README.md#optional-pymupdf-processing).
For the standard path, replace the fast `.pdf` class module `lite2_pdf_to_md_processor`
with `lite_pdf_to_md_processor`, retaining `LitePdfMarkdownProcessor`. Use
`docling` for the advanced processor's `pdf.extractor`. Bundled YAML and Helm
values already contain these defaults; existing overrides must be updated.
No new application configuration key is introduced.

For opt-in, select the `knowledge-flow-backend-pymupdf` image repository with
the same release tag and retain/select the PyMuPDF class or extractor. Apply
compatible images and configuration to the API, common worker and extraction
workers. Inspect explicit overrides that bypass Helm worker inheritance.
The Chroma build option remains independent.

### Upgrade

Drain in-flight ingestion before restarting workers, then deploy the matching
API/worker images and configuration together. Do not install dependencies into
running pods. Standard deployments need no custom image build; combining
optional Chroma and PyMuPDF requires a custom build with both arguments.

Existing indexed text and embeddings remain unchanged. Newly ingested PDFs can
have different text ordering, whitespace, Markdown and chunk boundaries.
Re-ingest only documents for which that new extraction is desired. Fast mode
does not OCR scanned PDFs; choose medium/rich Docling for those documents.

### Validation

Check startup succeeds for all enabled API/worker deployments. Ingest a
multipage PDF, a scanned PDF using Docling, and a PPTX with visual enrichment;
check previews, text, page references and retrieval. Inspect final-image
inventories: the standard image excludes all three PyMuPDF family packages,
while the optional image includes them. Selecting an optional processor in the
standard image must fail during configuration validation with a clear remedy.

### Rollback

Restore the previous images and matching configuration for API and workers
after draining current ingestion. Keep storage and database volumes. Documents
already re-ingested retain their new chunks until explicitly re-ingested again.
The previous image may reintroduce the optional family's license obligations.

### Limitations

Selecting an image does not select an engine. The optional family's licenses
include both AGPL/commercial and PolyForm Noncommercial terms. Removing that
family does not certify every other dependency or model license. Fast text
extraction preserves table values but does not promise Markdown table layout.

## Prepare Fred v3.7.0 and account for dependency lock refresh

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.7.0/docs/swift/ops/migrations/3165-release-3.7.0.md)

Release preparation and the covered dependency refresh need no action beyond deployment; follow the separate in-range notes for the database upgrade and optional image choices.

See the source note for applicability, validation and rollback.

## Request local Keycloak login from a Fred entry URL

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.7.0/docs/swift/ops/migrations/keycloak-local-login-link.md)

### Applicability

Authenticated Fred deployments using Keycloak, including through generic OIDC,
with an upstream SSO configured as the default identity provider.

### Prerequisites

Normal upgrade has no new prerequisites. Optional local-login usage requires a
usable account credential in Fred's Keycloak realm and a Browser flow that allows
local authentication. The URL flag does not bypass MFA or Fred permissions.

### Configuration

Fred YAML, Helm values and generated schemas are unchanged. For optional use,
check the client's effective Browser flow in Keycloak. Duplicate a shared flow,
make the default Identity Provider Redirector and Forms alternatives, keep the
username/password execution required inside Forms, and retain required MFA and
membership checks. Preserve the default SSO alias and select the copied flow on
the intended client. See [the Keycloak guide](https://github.com/ThalesGroup/fred/blob/code/v3.7.0/docs/swift/platform/KEYCLOAK.md#121-optional-local-login-when-sso-is-the-default)
for the standard Organization branch and client override location.

### Upgrade

Deploy the frontend normally. No data migration or special restart order is
needed. Optional activation can involve the Keycloak flow adjustment above,
which is why this note declares minor operational impact.

### Validation

In a private browser window, verify an ordinary Fred URL still redirects to SSO.
Open the same URL with `keycloak-login=true` and confirm Keycloak offers its
configured local authentication path. Verify the same path with a stored Fred
session and with Keycloak configured as `provider: oidc`. After successful login,
check the requested page/query/fragment, the removed flag and normal reload.

### Rollback

Restore the previous frontend. No data rollback is required. If a Keycloak flow
override was changed for optional activation, restore the previous override
separately; reverting Fred does not change Keycloak configuration.

### Limitations

Real Keycloak login depends on the server's authentication and organization
policy. Other issuers receive the explicit request but need not support
Keycloak-specific parameters. Security-disabled deployments ignore the flag.
Reopen the explicit link to retry a failed attempt; it is a one-time request.

## Refresh runtime images and shared dependency security floors

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.7.0/docs/swift/ops/migrations/runtime-image-security-refresh.md)

The refreshed Fred images take effect through normal deployment, with no data migration or special restart order.

See the source note for applicability, validation and rollback.
