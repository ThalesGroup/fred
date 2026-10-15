## Why

The two pages that greet people at the edge of the platform read as hard rejections (GitHub issue #3085). The access-denied page reuses the generic error page with a red icon and three equal actions, names neither the platform nor the account in use, and the team invitation page drops its card for that same error page as soon as a link is unusable, listing four possible causes without saying what to do.

## What Changes

- One compact card family (brand line, title, body, optional footer) for every state of `/platform-access-denied` and `/join/:token`, replacing the generic error page there. No red error icon.
- Access denied: greeting by first name with a fallback, the signed-in account (avatar, name, email) in its own surface, two numbered steps, a discreet sign-out, "Check my access" and "Request access". "Request access" opens the configured support link and is hidden when none is configured.
- Valid invitation: title "You have been invited to join a team", the team in its own inner surface, no repeated sentence, button "Join the team" without icon.
- Link no longer valid: the backend's `404 free_enrollment_link_invalid` answer gets its own state, one sentence telling the person to ask whoever invited them for a new link, no retry and no sign-out.
- Any other preview failure and a failed enrollment keep a separate state with a retry, so a working link is never reported as invalid.
- The transient admission-verification failure shown by the admission guard moves to the same card family (same title, message, retry, sign-out and support link as today).
- French and English strings rewritten under `rework.platformAccess`; strings no longer used are deleted.

Frontend only. No backend, contract or generated-client change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: the requirement "Admission feedback uses the shared Fred error presentation" is renamed and rewritten: these screens use one card family instead of the generic error presentation, the denied page identifies the account and lists next steps, and an invalid link is distinguished from a transient failure.

## Impact

- `apps/frontend/src/rework/components/pages/PlatformAccessPage/` (denied page, enrollment page, shared card, styles, tests).
- `apps/frontend/src/locales/{fr,en}/translation.json` (`rework.platformAccess`).
- `docs/swift/ux/COMPONENT-UX.md` (platform access entry), one migration note (impact: none).
- `PlatformAdmissionGuard` is not edited; it renders the restyled `PlatformAccessError`.
- The admin "Platform access" screens are out of scope.
