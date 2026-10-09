## Context

See proposal.md for scope. PlatformAccessPage already owns initial-import status, rule/selection state and filtering confirmation. PlatformAccessActivationDialog fetches the saved-policy population dry run and checks its revision. PageHeader supports right-aligned actions; ButtonGroup supports accessible tabs; Dialog supplies confirmation actions.

## Goals / Non-Goals

**Goals:** Reuse these components and existing server status to make import consent explicit while preserving draft state, current safeguards and live team authorization.

**Non-Goals:** Changing admission evaluation, making import mandatory at the API, adding deployment configuration or moving Free/link administration out of the platform Teams registry.

## Decisions

- Render the filtering action through PageHeader.actions, replacing the fixed bottom action. Keep its configured-source and busy guards across both top-level tabs.
- Add a separate nested tab selection under one Whitelist heading. Keep import and individual exceptions in Users and independent team authorization in Teams. Preserve mounted panel state and hide inactive panels from focus and assistive navigation.
- Extend the current confirmation instead of opening two consecutive modals. With a known incomplete import, show an explicit warning and label choices Continue without importing and Go to whitelist. The second choice closes the dialog, selects Whitelist > Users and performs no mutation. Ordinary dismissal also performs no mutation.
- Require successful, current import-status loading before enabling confirmation. Keep the dry-run revision check and saved-source requirements. A completed import uses normal activation confirmation; disabling filtering does not require import status.

## Risks / Trade-offs

- Import-status failure could otherwise bypass consent: keep confirmation unavailable with actionable retry feedback until status is known.
- Nested tabs could hide the wrong focus targets or lose selections: reuse shared tab semantics and test navigation with retained drafts and user selections.
- UI consent is not a transactional import requirement: the backend continues enforcing its existing authorization, source and actor safeguards.

## Migration Plan

Ship as a frontend update with English/French labels. No data migration or operator configuration is required. Update the existing migration guide and UX documentation; rollback restores the previous layout without changing stored policies or exceptions.
