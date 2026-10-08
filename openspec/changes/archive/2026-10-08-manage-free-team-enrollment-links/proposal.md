## Why

The current single team token rotates previous invitations and gives administrators no history, expiry or opening metrics. Multiple independent invitations need a manageable lifecycle while retaining live membership-based admission.

## What Changes

- Generate multiple independent links per Free team, with an optional note and expiration instant.
- List link metadata and authenticated opening counts; revoke individual links irreversibly.
- Keep links valid indefinitely unless expired or revoked. Generating another link does not invalidate existing ones.
- Suspend usable links when Free is removed and resume them when Free is restored. Membership-derived admission still disappears immediately when its only source is removed.
- Count authenticated enrollment-page opening totals on each link, without tracking anonymous visitors or personal identity.
- Allow copying an existing URL through a dedicated platform-administrator action; history otherwise lists only notes, dates, status and counts. Fred does not send messages or assert delivery.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: independent Free-link lifecycle and authenticated opening history.

## Impact

Shared admission SQL models/store, the single pending control-plane migration, admin and own-credential enrollment APIs, generated frontend clients, Free-team administration/enrollment UI, regression tests and existing product/UX/operator documentation. No deployment setting or dependency is added. Issue #2965 and PR #2966 retain tracking; delivery is a separate commit from the filter UI. The developer selected suspension on Free removal and counting only openings after authentication.
