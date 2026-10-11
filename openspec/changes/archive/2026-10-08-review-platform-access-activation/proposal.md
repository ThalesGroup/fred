## Why

Administrators need identifiable users, unrestricted bulk exception selection and an explicit population review before activation. The current 100-person cap and immediate switch prevent this workflow. Follow-up to issue #2965 and PR #2966.

## What Changes

- Display identifiers, first/last names using the same DataTable columns as team members; retain email and provenance. Remove T0 jargon from visible import wording.
- Remove the 100-person selection/request cap. Deduplicate, validate and insert exceptions in bounded SQL batches within one atomic transaction, preserving existing sources.
- Offer a bottom-right floating filtering action across all tabs. Enable activation only after a saved predicate or independent user/team admission source exists, including whitelist-only policies.
- Require a Fred confirmation dialog with a read-only population dry run under saved policy and live exceptions/membership. Show allowed, blocked and uncertain identities and counts; missing/stale evidence is uncertain rather than a fabricated refusal.
- Retain actor lockout, suspension, CGU, legacy-gate and live revocation safeguards. Preview does not activate, persist token values or grant access.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: identifiable unlimited bulk selection and reviewed explicit activation.

## Impact

Existing control-plane admission routes/models/service, shared admission state validation, generated frontend client, page and translations, focused tests and current UX/operator/product docs. No new database revision or configuration. Commit user-selection logic separately from activation logic.
