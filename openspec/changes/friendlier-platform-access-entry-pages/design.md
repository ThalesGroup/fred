## Context

See proposal.md for motivation. `FreeEnrollmentPage` already draws a card (brand line, title, body, footer behind a divider) in its own stylesheet; `PlatformAccessDeniedPage` and the enrollment error state go through `PlatformAccessError`, which wraps the generic `PageError`. `PlatformAdmissionGuard` uses `PlatformAccessError` too. The layout, hierarchy and French copy were validated by the owner on a mock before this change was written.

The enrollment preview answers `404` with detail `free_enrollment_link_invalid` whenever the token is malformed, unknown, expired, revoked, or its team no longer allows link access (`require_link` in `platform_access/service.py`, lookup in `fred_core/security/platform_access/store.py`). The answer never says which case applies, nor which team.

## Goals / Non-Goals

**Goals:**

- One page-local card component and one stylesheet for the denied page, the four enrollment states and the guard's verification failure.
- Only existing design tokens, shared components and their existing props.

**Non-Goals:**

- No change to shared components, to the backend, or to the admin "Platform access" screens.
- No new reason codes: an invalid link stays undifferentiated.

## Decisions

- **`PlatformAccessCard` (page-local) replaces both stylesheets.** It owns the page wrapper, the brand line (`siteDisplayName`), the `h1` that labels the card, the body and a footer with a left group and a right group; the footer is omitted when both are empty. `FreeEnrollmentPage.module.css` and `PlatformAccessPage.module.css` are folded into `PlatformAccessCard.module.css`. Alternative: keep `PageError` for errors. Rejected: it carries the red icon and centred layout the issue removes.
- **`PlatformAccessError` keeps its props and becomes the "temporary problem, retry" card.** The enrollment page uses it for a failed preview or join, and the guard gets the new card without being edited. Its message keeps `role="alert"`. Alternative: leave the guard on `PageError`. Rejected: it would keep a second presentation alive for one caller at no saving.
- **Invalid link = exactly status 404 with detail `free_enrollment_link_invalid`,** read with the existing `normalizeApiError`. The same test is applied to a failed terms acceptance or join, so a link revoked while the page is open is also reported as no longer valid instead of offering a pointless retry.
- **Identity comes from the session token** through the existing `KeyCloakService` getters (given name, full name, email) and the shared `UserAvatar`; no user request is made, since the protected user endpoint is not reachable for a denied person. The first name is only the token's given name: it is not guessed from the full name.
- **"Request access" is a shared `Button` opening the link with `window.open(..., "_blank", "noopener,noreferrer")`,** as the profile menu already does, because `Button` has no link form and gains no prop here.
- **Footer left items are plain text links** (support anchor, sign-out button) sharing one class with no horizontal padding, so they sit on the card's content edge. A shared text `Button` would be indented by its own padding.
- **Without a support link** the denied page keeps both steps (step 1 still says to ask support), sign-out and "Check my access" as an outlined button; nothing replaces "Request access".

## Risks / Trade-offs

- [The invitation title must fit one line at desktop width] → `--font-title-medium-emphasized` in a 28rem card, as in the mock; not verifiable in unit tests, to be checked on screen in both languages.
- [A deployment whose token has no `given_name`/`email` claim] → greeting, account block and step 1 each degrade independently; covered by tests.
- [The guard's failure screen changes look without being the subject of the issue] → same title, message, actions and roles; its existing test is unchanged.

## Open Questions

- Without a support link the denied page has no filled button ("Check my access" stays outlined). Should it become the filled action in that case?
- Sign-out on the denied page and on the guard's failure card is a text link rather than a shared `Button` so it aligns with the card content. Is a link-styled button acceptable there, or should the shared text `Button` be used despite its indent?
- Temporary-problem wording on the enrollment route is new and was not on the validated mock (see tasks 3.3); to confirm.
