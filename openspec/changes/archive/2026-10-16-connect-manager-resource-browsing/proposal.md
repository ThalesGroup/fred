## Why

Priya can open her entitled personal space and her teams, but the mounted Rust journey has no Resources destination. The historical Resources page still calls Python services. Complete read-only browsing using control-plane while preserving the existing visual components (#3092).

## What Changes

- Mount the existing Resources destination and scoped navigation for personal, team and project spaces.
- Read folders and document metadata through generated control-plane queries; navigate folders and document cursor pages with existing explorer and pagination controls.
- Distinguish loading, successful emptiness, denied access and service errors; discard previous scope/page data while revalidating.
- Reject nonexistent or cross-space folder filters instead of returning misleading empty lists.
- Verify the journey with real browser and API regressions, and document implemented behavior in arc42.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `control-plane-provisioning`: Extend the provisioned person's UI journey to authorized resource browsing.

## Impact

Frontend routing, scoped sidebar, Resources page and shared pagination presentation; manager read routes and generated OpenAPI; disposable integration fixtures and architecture dossier. No new content grants, upload, ingestion, preview, search, conversation, organization selector or visual redesign. Existing list response shapes and keyset cursor semantics remain unchanged.
