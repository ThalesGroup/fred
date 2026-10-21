## Context

See proposal.md. The four mutation handlers have no UI consumer or compatible worker. The API's ingestion client is the only reason `serve` connects to Temporal. The space-deletion worker uses its own lifecycle configuration and client. Two API state types differ only by ingestion.

## Goals / Non-Goals

Goals: remove unsupported callable operations and unnecessary startup dependencies; preserve the existing Resources read/folder journey and its authority checks.
Non-goals: document upload/processing, admission reconstruction, SQL migration, changes to lifecycle workflows or retention.

## Decisions

- Remove routes and schemas rather than disabled stubs: unknown paths return 404; removed methods on the retained document GET path return 405. No mutation or workflow dispatch occurs.
- Share one API state after removing ingestion. Keep existing route grouping and middleware semantics; no authority/model changes or extra FGA calls.
- Delete the ingestion configuration and optional-body codegen workaround. Lifecycle retains its own Temporal configuration and dedicated `control-plane-` queue. Remove only the comparison to the now-absent manager ingestion queue.
- Retain SQL document metadata and fixture helpers, metadata reads and authorization probes. Existing data is not purged. Delete unused production mutation/storage helpers when no retained consumer needs them.
- Keep k3d reset preflight aligned with lifecycle-only manager configuration while preserving host/namespace restrictions for every backend.
- Regenerate OpenAPI/client and assert the removed operations are absent. Exercise the real API with Temporal unreachable, as well as the existing worker restart test.

## Risks / Trade-offs

External callers of provisional mutations lose those operations. This is the explicitly approved breaking removal; do not redirect them silently to Python. Existing document rows remain readable and continue to block unsupported space purges.

## Migration Plan

Deploy the API and regenerated frontend together; remove `scheduler.temporal` from manager configuration, preserving `scheduler.lifecycle`. There is no data migration. Rollback restores the prior API/client/configuration together and would re-expose the provisional surface.
