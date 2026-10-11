## Why

The default claim picker shows token metadata and nested structures before account attributes. Administrators need a short list of useful text fields.

## What Changes

- Default both current-session and observed-name views to root text attributes, excluding token protocol metadata.
- Keep the complete bounded tree and catalog behind an explicit advanced-fields action.
- Clear selection and copied values when changing display mode; preserve draft-only editing and all saved rules.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: simplify the default claim-selection presentation.

## Impact

Issue #2965 and PR #2966. Frontend picker, English/French wording and regression tests only. No API, authorization, deployment or migration changes. This is the user's requested refinement of the implemented picker.
