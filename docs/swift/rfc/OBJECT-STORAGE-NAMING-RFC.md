# RFC — Object Storage Naming Cleanup

**Status**: Draft
**Author**: Simon
**Date**: 2026-06-05
**Backlog**: `docs/swift/backlog/BACKLOG.md §OPS-05`
**Related**:
- `docs/swift/design/FILESYSTEM.md`
- `docs/swift/platform/DEPLOYMENT_GUIDE.md`
- `docs/swift/platform/ENV_VARIABLES.md`

---

## 1. Problem

Several file names, comments, and docs still describe Fred storage as if MinIO
were the platform contract. That wording is too narrow. The actual integration
contract is usually S3-compatible object storage or generic object storage:
endpoint, credentials, bucket/prefix layout, and presigned URL behavior.

MinIO remains a valid implementation, especially for local or simple
deployments, but it should not be used as the generic architecture name.
SeaweedFS has already been wired by changing ports/endpoints only, which
confirms that the platform boundary is provider-neutral for this path.

---

## 2. Proposed Solution

Run a documentation and naming cleanup tracked by `OPS-05`:

- Use `S3-compatible object storage` when the S3 API compatibility is material.
- Use `S3` for concise operator-facing configuration where the S3 API is the
  concrete protocol being configured.
- Use `object storage` when the statement is about generic storage semantics.
- Keep `MinIO` only where it names an actual MinIO implementation detail:
  adapter, dependency, local service, env var, chart value, or compatibility
  boundary that cannot be renamed without a migration.

The cleanup should cover docs, comments, file names, Helm/config naming, and
references to presigned URLs. It should not change runtime behavior by default.

---

## 3. Alternatives Considered

### 3.1 Keep Calling The Storage Layer "MinIO" Everywhere

Rejected.

This makes operators think Fred requires MinIO-specific behavior even when an
S3-compatible backend such as SeaweedFS works with endpoint and port changes
only. It also makes future GCS/S3-compatible deployment docs harder to read.

### 3.2 Rename Every MinIO Symbol Immediately

Rejected.

Some names are compatibility-bound or identify the concrete MinIO Python client,
local service, or environment variable. Renaming those in one pass would create
unnecessary migration work. The cleanup should distinguish provider-neutral
contract names from concrete implementation names.

---

## 4. Impact On Existing Contracts

No API or storage behavior changes are required by this RFC. The expected impact
is naming and documentation alignment.

Implementation must preserve existing MinIO-backed deployments unless a
separate migration RFC explicitly changes configuration keys or runtime adapter
behavior.

---

## 5. Acceptance Criteria

- Docs and comments use S3/object-storage wording where the contract is
  provider-neutral.
- MinIO wording remains only for concrete implementations, dependencies, env
  vars, local services, chart values, or compatibility-bound names.
- SeaweedFS-compatible deployment is described as a normal S3/object-storage
  configuration with endpoint/port differences only.
- Any file rename is limited to names that expose a generic storage abstraction
  and are not tied to MinIO-only behavior.
