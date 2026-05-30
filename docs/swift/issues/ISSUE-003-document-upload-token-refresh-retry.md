# ISSUE-003 - Document upload can fail on stale Keycloak token (missing refresh/retry)

Status: open
Owner: TBD
Target window: next frontend hardening slice (pre-production)

## Problem
`streamUploadOrProcessDocument` performs upload with a token snapshot and a single request attempt. If the token is stale, first upload can fail with 401 and generic "Upload failed", even though retry succeeds after token refresh happens elsewhere.

## Why it matters
- Creates flaky first-attempt upload UX in Document Library.
- Diverges from established auth behavior already used by RTK `dynamicBaseQuery`.
- Likely to appear in real usage near token expiry windows.

## Current evidence
- `apps/frontend/src/slices/streamDocumentUpload.tsx`: `streamUploadOrProcessDocument` exists and takes token from `KeyCloakService.GetToken()`.
- `apps/frontend/src/slices/streamDocumentUpload.tsx`: throws on non-OK (`Upload failed: ...`) with no token refresh/retry branch.
- `apps/frontend/src/common/dynamicBaseQuery.tsx`: proactively calls `ensureFreshToken(30)` and retries once on 401 with `ensureFreshToken(0)`.

## Scope
- Active paths:
  - Document upload/process streaming path in frontend (`streamDocumentUpload.tsx`).
- Not in scope:
  - Non-upload RTK API calls already covered by `dynamicBaseQuery` token-refresh flow.

## Proposed fix
- Before request: call `await KeyCloakService.ensureFreshToken(30)`.
- On `response.status === 401`: call `await KeyCloakService.ensureFreshToken(0)` and retry once.
- Preserve current behavior for non-auth failures.

## Acceptance checks
- [ ] First upload attempt does not fail when token is near expiry.
- [ ] Exactly one retry occurs on 401, then fails cleanly if second call is still unauthorized.
- [ ] Non-401 errors keep current error behavior.
- [ ] Behavior aligns with `dynamicBaseQuery` auth strategy.

## Promotion
Promoted to: none
Notes: Candidate to promote under frontend production-readiness hardening.
