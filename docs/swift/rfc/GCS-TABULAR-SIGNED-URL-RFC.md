# RFC — GCS Signed URLs For Tabular Parquet Reads

**Status**: Draft
**Author**: Dimitri
**Date**: 2026-06-23
**Backlog**: `docs/swift/backlog/BACKLOG.md §Phase STORAGE` (`FILES-06`)
**Related**:
- `docs/swift/platform/DEPLOYMENT_GUIDE_GKE.md`
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

## 1bis. Pre-Implementation Spike (gate)

Before any production signing code is written, run a throwaway spike against a
real GCS bucket under Workload Identity. The spike exists because the binding
risk here is not the signing code but the DuckDB↔GCS-auth integration, and that
integration cannot be proven by offline mocks.

The spike must:

- Generate one V4 signed URL via the IAM `signBlob` path (no SA JSON key), and
  read it with `duckdb.from_parquet(url)`. This resolves the two unknowns mocks
  cannot: whether `httpfs`'s metadata probe (HEAD / ranged GET) survives a
  method-scoped V4 signature, and whether the Workload Identity signing path
  works end to end.
- In the same session, also test the §3.3 bearer-token / DuckDB HTTP-secret
  path against the same object, so the choice between V4 signing and bearer
  tokens is made on observed behaviour, not on paper.

Do not implement §2 until the spike is green. A red spike on the V4 path
re-opens §3.3 as the primary, and vice versa. Capture the working approach and
the DuckDB/`httpfs` behaviour in the backlog before proceeding.

---

## 2. Proposed Solution

Restore signed URL support for GCS, but scope it explicitly to backend-internal
tabular reads:

- Keep browser-facing document and VFS sharing on application-level HMAC tokens.
- Implement `GcsContentStore.get_presigned_url_internal(...)` as a short-lived
  GCS V4 signed URL for read-only object access.
- Use Workload Identity with IAM signing, not JSON service-account keys.
- Require the signing service account to have:
  - object read permission on the tabular object bucket;
  - `iam.serviceAccounts.signBlob`, typically through
    `roles/iam.serviceAccountTokenCreator` on itself.
- Add explicit GCS config for the signing service account email when automatic
  discovery is not reliable.
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

Rejected as the default.

This works with existing GCS Workload Identity permissions and avoids signed
URLs entirely, but it forces Knowledge Flow to download full Parquet files for
each query. That defeats DuckDB's efficient HTTP range reads for Parquet and
creates avoidable backend bandwidth, disk, and latency costs for large datasets.

It remains acceptable as an emergency fallback or local-only implementation.

### 3.2 Plain Public GCS URLs

Rejected.

Plain unauthenticated `https://storage.googleapis.com/...` URLs would require
public object or bucket access. That is incompatible with Fred's document-level
authorization model.

### 3.3 Plain URLs With DuckDB HTTP Authorization Headers

Spike-candidate — decided empirically in §1bis, not deferred on paper.

DuckDB can authenticate HTTP reads with bearer-token headers, so Knowledge Flow
could mint a Google access token (`credentials.token` from ADC) and create a
scoped DuckDB HTTP secret per connection. This avoids signed URLs and, notably,
sidesteps the two sharpest Workload Identity gotchas of the V4 path: it needs
neither `iam.serviceAccounts.signBlob` / `roles/iam.serviceAccountTokenCreator`
nor reliable signing-SA-email discovery. Its cost is token refresh and
secret-scoping complexity on the query-engine path, and its own
DuckDB-version-dependent support for HTTP/bearer secrets.

Both this path and the V4 path hinge on the *same* unverified question — how
DuckDB `httpfs` authenticates to GCS — so neither can be ranked ahead of the
other before the §1bis spike. V4 signing remains the presumed choice because it
keeps the authorization decision in Knowledge Flow and the object read in GCS
with a simple single-object TTL boundary; the spike result confirms or
overturns that presumption.

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
- Deployment documentation must include the IAM requirement for GCS tabular
  reads.
- Helm/GCP values may need an optional signing service account email setting if
  the runtime cannot infer it reliably from ADC.

---

## 5. Acceptance Criteria

- Tabular reads on unsupported object stores fail with an explicit unsupported
  operation error.
- GCS tabular reads can mount Parquet artifacts through short-lived internal V4
  signed URLs under Workload Identity.
- No JSON service-account key is required.
- Signed URLs are never exposed to frontend responses, MCP tool responses, or
  logs.
- DuckDB read failures must not propagate signed URLs into logs or error
  responses: object URLs are redacted from caught `duckdb` / `httpfs`
  exceptions before they are logged or surfaced. (A failed Parquet read
  otherwise echoes the full signed URL in the exception string, defeating the
  criterion above.)
- Offline tests cover unsupported-store failure and signed URL generation with a
  mocked GCS client/credentials path. These are smoke tests asserting call
  shape, not behaviour — a green offline suite is not "shippable". The real gate
  is the §1bis spike and a live GKE validation run, where the signing-SA-email,
  `signBlob` permission, and `httpfs` HEAD/range issues actually surface.
- GKE deployment docs list the required IAM permissions and config knobs.
