## Why

Creating a team invitation currently leaves its URL in the result dialog but requires another click to copy it. Administrators usually create the link to share it immediately.

## What Changes

- Attempt to copy a newly created invitation URL to the clipboard as soon as generation succeeds.
- Confirm the copy only after the browser accepts it. Keep the URL and manual Copy URL action available if clipboard access fails.
- Preserve the existing behavior for copying links from history.
- Display the generated invitation URL in Fred's existing monospace font.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: Update the administrator's link-creation result and clipboard feedback.

## Impact

The frontend invitation manager and its styles, focused tests, the platform access spec, and the compact component UX guide. No API or data migration is needed.
