# RFC — GCS Signed URLs For Tabular Parquet Reads

**Status**: Draft
**Author**: Dimitri
**Date**: 2026-06-23
**Backlog**: `docs/swift/backlog/BACKLOG.md §Phase STORAGE` (`FILES-06`)
**Related**:
- `docs/swift/rfc/OBJECT-STORAGE-NAMING-RFC.md`
- `apps/knowledge-flow-backend/knowledge_flow_backend/features/tabular/service.py`
- `apps/knowledge-flow-backend/knowledge_flow_backend/core/stores/content/gcs_content_store.py`

---

## 1. Problem

The native GCS content store intentionally disabled provider signed URLs on the
default Workload Identity path. That is correct for browser-facing sharing,
which uses application-level HMAC download tokens and keeps object-store details
behind Knowledge Flow.

The tabular runtime is different. CSV ingestion writes one Parquet artifact per
document into the content store, and `/tabular/query`, dataset schema reads, and
CSV markdown previews mount those Parquet files in DuckDB. DuckDB needs a
DuckDB-readable location. Today that location is resolved through
`BaseContentStore.get_presigned_url_internal(...)`, with a local filesystem
fallback for development.

With `content_storage.type: gcs`, `GcsContentStore.get_presigned_url(...)`
raises `NotImplementedError`, and the tabular service can only fall back for
`FileSystemContentStore`. GCS deployments therefore cannot use the tabular MCP
surface even though ingestion can successfully write the Parquet artifacts.

---

## 1bis. Pre-Implementation Validation Gate

Before merge, validate the chosen signed URL path against a real GCS bucket
under Workload Identity. The validation exists because the binding risk here is
not the Python signing call alone, but the full DuckDB `httpfs` read path against
a GCS V4 signed URL. Offline mocks cannot prove that path.

The validation must:

- Generate one V4 signed URL via the IAM `signBlob` path (no SA JSON key), and
  read it with `duckdb.from_parquet(url)`.
- Confirm DuckDB can inspect Parquet metadata and execute a selective query
  through the signed URL.
- Confirm the signed URL uses a short TTL and does not require public bucket
  access.
- Confirm failed DuckDB reads do not leak the signed URL into logs or API error
  responses.

If this validation fails, the implementation is not shippable. Fix the signed
URL implementation, IAM binding, DuckDB invocation, or runtime image until this
path is green. This RFC deliberately does not authorize a bearer-token,
plain-URL, or proxy-download replacement path.

---

## 2. Proposed Solution

Restore signed URL support for GCS, but scope it explicitly to backend-internal
tabular reads:

- Keep browser-facing document and VFS sharing on application-level HMAC tokens.
- Implement `GcsContentStore.get_presigned_url_internal(...)` as a short-lived
  GCS V4 signed URL for read-only object access.
- Use Workload Identity with IAM signing, not JSON service-account keys.
- Add explicit GCS config:
  - `content_storage.signing_service_account_email: str | None`
  - Required when `content_storage.type: gcs` and tabular internal signed URLs
    are enabled.
  - If omitted, startup must fail clearly instead of guessing.
- Require IAM as follows:
  - The signing service account has `storage.objects.get` on the GCS objects
    bucket that stores tabular Parquet artifacts.
  - The Workload Identity Google service account used by Knowledge Flow has
    `iam.serviceAccounts.signBlob` on the signing service account, typically via
    `roles/iam.serviceAccountTokenCreator`.
- Never return backend-internal signed URLs in API responses, logs, or MCP tool
  payloads.
- Keep TTL bounded by `storage.tabular_store.query.internal_presigned_ttl_seconds`.

As an immediate guardrail before signing is implemented, tabular reads on
content stores that provide neither backend-internal signed URLs nor local file
paths must fail as an explicit unsupported operation rather than a generic
runtime error.

---

## 3. Alternatives Considered

### 3.1 Download Every Parquet Artifact Through Knowledge Flow

Rejected.

This works with existing GCS Workload Identity permissions and avoids signed
URLs entirely, but it forces Knowledge Flow to download full Parquet files for
each query. That defeats DuckDB's efficient HTTP range reads for Parquet and
creates avoidable backend bandwidth, disk, and latency costs for large datasets.

### 3.2 Plain Public GCS URLs

Rejected.

Plain unauthenticated `https://storage.googleapis.com/...` URLs would require
public object or bucket access. That is incompatible with Fred's document-level
authorization model.

### 3.3 Plain URLs With DuckDB HTTP Authorization Headers

Rejected for this RFC.

DuckDB can authenticate HTTP reads with bearer-token headers, so Knowledge Flow
could mint a Google access token (`credentials.token` from ADC) and create a
scoped DuckDB HTTP secret per connection. That is a different design: it adds
Google token refresh, token lifetime handling, and per-connection secret cleanup
to the query engine path. It also makes DuckDB credential state part of Fred's
runtime contract. This RFC chooses GCS V4 signed URLs instead.

### 3.4 Disable Tabular On GCS Profiles

Rejected as the final state.

This is a safe temporary mitigation, but it breaks the Tessa/tabular agent MCP
surface for GCS deployments and leaves the indexed Parquet artifacts unusable.

---

## 4. Impact On Existing Contracts

- No public API field changes are required.
- No generated OpenAPI contract change is expected for the signed URL
  implementation.
- `get_presigned_url_internal(...)` becomes a real backend-internal capability
  for GCS, while `get_presigned_url(...)` may remain disabled for
  browser-facing use until a separate browser direct-download decision is made.
- `GcsStorageConfig` gains `signing_service_account_email`.
- Deployment documentation and Helm/GCP values must include the IAM requirement
  and signing service account setting for GCS tabular reads.
- Cross-backend invariant:
  - MinIO/S3-compatible content stores must continue to serve tabular Parquet
    reads through their existing backend-internal presigned URL path.
  - Local content storage must continue to use the local filesystem fallback.
  - The GCS implementation is additive and must not change MinIO/S3-compatible
    or local tabular access semantics.

---

## 5. Acceptance Criteria

- Tabular reads on unsupported object stores fail with an explicit unsupported
  operation error.
- GCS tabular reads can mount Parquet artifacts through short-lived internal V4
  signed URLs under Workload Identity.
- No JSON service-account key is required.
- Startup fails clearly when GCS tabular signed URLs are required but
  `content_storage.signing_service_account_email` is missing.
- Signed URLs are never exposed to frontend responses, MCP tool responses, or
  logs.
- DuckDB read failures must not propagate signed URLs into logs or error
  responses: object URLs are redacted from caught `duckdb` / `httpfs`
  exceptions before they are logged or surfaced. (A failed Parquet read
  otherwise echoes the full signed URL in the exception string, defeating the
  criterion above.)
- Offline tests cover unsupported-store failure and signed URL generation with a
  mocked GCS client/credentials path. These are smoke tests asserting call
  shape, not behaviour.
- Existing MinIO/S3-compatible and local tabular tests continue to pass; GCS
  signing support is additive and does not alter their access paths.
- A live GKE validation run proves DuckDB can query a Parquet artifact through
  the generated V4 signed URL.
- GKE deployment docs list the required IAM permissions and config knobs.
