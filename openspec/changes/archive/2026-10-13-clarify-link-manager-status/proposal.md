## Why

The link manager hides the Suspended status visually and relies on faded rows when a team's Link access is disabled. Administrators can mistake those links for usable invitations. Links without an optional note also show the awkward placeholder "No note" in the table and joiner title.

## What Changes

- Show a clear disabled Link access notice in the invitation manager and a visible Suspended status on affected links, while keeping the existing lifecycle filters and actions.
- Leave an absent note cell empty and use a generic joiner-dialog title for links without a note.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: Clarify the administrator-facing state of suspended links and the presentation of optional link notes.

## Impact

Frontend link manager, its English and French translations, focused UI tests, and the platform access spec. The backend already returns Suspended for unrevoked, unexpired links when Link access is disabled; no API or data change is needed.
