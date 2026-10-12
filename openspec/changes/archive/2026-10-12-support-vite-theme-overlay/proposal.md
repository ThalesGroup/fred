# Proposal

## Why

The deployment ZIP loader works in Docker, but the local Vite frontend used by
"All Services PROD" ignores `FRONTEND_THEME_URL`. Developers cannot test the
same SeaweedFS theme locally without copying assets into tracked `public/` files.

## What Changes

- Load the same optional theme ZIP at Vite startup using the existing URL,
  S3 credentials, validation and required/optional failure behavior.
- Serve validated overlay files ahead of stock public files without modifying
  the checkout; restart Vite and reload the browser to activate a replacement ZIP.
- Document `apps/frontend/config/.env` as the local configuration entrypoint.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-ui-themes`: apply the existing theme ZIP contract to local Vite startup.

## Impact

Issue: #3027. Frontend Vite configuration, Makefile environment forwarding,
shared shell theme installer, Docker entrypoint/image packaging, focused tests
and frontend README. No backend or database changes. Reuse curl, unzip and jq.
