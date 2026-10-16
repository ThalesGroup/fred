## Why

Priya can browse manager resources but cannot create folders from that journey.
Complete this bounded write operation before the first end-to-end product review (#3092).

## What Changes

- Connect the existing new-folder control and dialog to the generated manager client.
- Expose folder creation on the Temporal-independent router and validate folder names and depth server-side.
- Use OpenFGA write permission for the action, enforce it again on mutation, and refresh the current folder after success.
- Cover duplicate names, invalid/missing/foreign parents, revoked rights, repeated submission and navigation while pending.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fred-manager-provisioning`: extend the authenticated resource journey with folder creation.

## Impact

Manager folder API/service, generated frontend client, Resources page and existing
folder dialog, focused backend/UI/browser tests, and arc42. No upload, ingestion,
rename/delete controls, organization selection or visual redesign. One local commit;
no push. Scope approved by the user's request to proceed after the proposed lot.
