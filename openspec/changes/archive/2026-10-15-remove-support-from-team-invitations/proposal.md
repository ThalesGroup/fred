## Why

The team invitation route offers "Contact support" even though its valid and invalid-link states should direct the visitor through the invitation itself or back to the inviter. Platform admission refusal already offers "Request access" through the configured support destination when a signed-in person is not admitted (#3119).

## What Changes

- Remove the contact-support action from every `/join/:token` state: checking, valid invitation, invalid link and temporary error.
- Keep the refusal page's existing request-access action and the admission-verification error's support action.
- Preserve invitation joining, retry behavior, invalid-link guidance and the no-sign-out rule.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: Limit support actions to platform admission refusal and admission-verification failure, while keeping the Free invitation route reachable without a support action.

## Impact

- Frontend-only presentation and focused tests in `apps/frontend/src/rework/components/pages/PlatformAccessPage/`.
- Update the platform access entry in `docs/swift/ux/COMPONENT-UX.md` and add one `impact: none` migration note.
- No backend, API, generated client, stored data, configuration or permission change.

The earlier `friendlier-platform-access-entry-pages` change covers the same screens but its issue and PR are already closed and merged. Its shipped behavior was synchronized and archived before this delta was applied to the current capability spec.
