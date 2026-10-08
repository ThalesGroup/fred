## Why

The current account-field dropdown hides the verified JSON view users prefer, and a fabricated first condition makes creation unclear. The existing save action sits below the conditions, so administrators cannot easily tell when changes become effective. Follow-up to issue #2965 and PR #2966.

## What Changes

- Start an unconfigured rule with no draft conditions and an explicit add-condition invitation; retain existing saved conditions on load.
- Open the existing own-account JSON picker directly on add or field edit, with a question title, selectable blue keys and root text fields by default. Remove the account-field dropdown.
- Append a condition only after field confirmation; cancellation preserves the draft. Retain the separate optional current-value prompt, operators, case handling and global AND/OR.
- Show a prominent localized save-rule action near the editor title, unsaved/saving/saved feedback and clear persistence wording. Preview remains unsaved and empty drafts cannot be saved or activated.
- Split the page into Rules, Users, Teams and links, and Activation using the home page's shared navigation control. Preserve local drafts and selections between views, standardize typography and remove repeated help text.
- Update UI regressions, real-account screenshots, existing UX/operator documentation and capability specs. Keep this UI refinement in its own commit.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: picker-first condition creation, empty local drafts, explicit visible versioned saving and readable section navigation.

## Impact

Frontend editor, existing claim-picker title, editor styles, English/French translations and focused tests. Reuse the generated preview/save hooks and existing backend bounds, revisions and lockout safeguards. No backend API, database migration, Helm or runtime configuration changes. Update the existing PR and issue rather than opening parallel tracking.
