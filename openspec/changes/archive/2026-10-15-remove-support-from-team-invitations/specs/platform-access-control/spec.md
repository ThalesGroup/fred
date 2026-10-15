## REMOVED Requirements

### Requirement: Refusal and enrollment screens remain reachable

**Reason:** Replaced by a requirement that distinguishes support on platform refusal from the invitation route.

**Migration:** Keep the configured request-access action on refusal and remove contact support from Free enrollment.

## ADDED Requirements

### Requirement: Refusal and enrollment routes keep distinct support actions

The frontend SHALL display a standalone localized refusal page for `platform_access_denied`, with contact-support wording and the existing `contactSupportLink` when configured. Refusal and other support consumers SHALL use that frontend property, available before protected bootstrap; the Free enrollment route SHALL NOT present a contact-support action. The removed backend/public `supportLink` SHALL NOT override it. Other authentication, CGU, resource-permission and transient errors SHALL retain their handling. The valid Free route and narrow own-credential status/legal/enrollment operations SHALL remain reachable to authenticated denied people without admitting normal product access.

#### Scenario: Denied bootstrap displays support

- **WHEN** a protected request returns `platform_access_denied`
- **THEN** refusal SHALL render without successful protected bootstrap or a redirect loop and its request-access destination SHALL equal configured `contactSupportLink`

#### Scenario: Free enrollment omits support

- **WHEN** an otherwise denied person opens a Free enrollment route with `contactSupportLink` configured
- **THEN** the route SHALL show no contact-support action while preserving its invitation, legal, join and retry actions as applicable

#### Scenario: Different error remains distinct

- **WHEN** a request returns 401, a CGU refusal, another resource 403 or an admission-authority 503
- **THEN** the frontend SHALL NOT convert it into platform refusal

## MODIFIED Requirements

### Requirement: Admission feedback uses one welcoming card family

Admission denial, every state of the Free enrollment route and transient admission-verification failures SHALL be presented in one compact card showing the deployment's configured site display name, a single page heading that labels the card, a body and an optional footer. These states SHALL NOT use the generic error page or an error icon. The platform name SHALL always come from the configured site display name. These screens SHALL remain reachable without protected bootstrap or team/resource loading; ordinary error pages SHALL retain their existing action.

The denial screen SHALL greet the signed-in person by first name, falling back to a greeting without a name, SHALL show the signed-in account (name and email, whichever is known) and SHALL list two numbered steps: request access from support, then come back and check access. It SHALL offer sign-out, an access re-check, and a request-access action that opens `contactSupportLink` in a new tab. When `contactSupportLink` is not configured the request-access action SHALL be hidden and no alternative contact SHALL be invented. When no email is known, the steps SHALL NOT refer to a displayed address, and an account block with neither name nor email SHALL NOT be rendered.

The enrollment screen SHALL announce an invitation, show the team in its own surface and offer a single join action; it SHALL NOT display a contact-support action in any state. A preview refused as `404 free_enrollment_link_invalid` SHALL be reported as a link that is no longer valid, with guidance to ask the inviter for a new link, without a retry action and without a team name. A terms acceptance or a join refused with that same answer (a link revoked or expired while the page was open) SHALL be reported the same way. Any other failure of the preview, of the terms acceptance or of the join SHALL be reported as a temporary problem with a retry action and SHALL NOT be reported as an invalid link. Sign-out SHALL NOT appear on the enrollment route in any state.

#### Scenario: Denied or invalid enrollment route

- **WHEN** a denied person opens the refusal route or an invalid Free link
- **THEN** the screen SHALL use the shared card without normal protected product loading; the refusal SHALL offer configured support while the invalid-link card SHALL offer none

#### Scenario: Denied person is greeted and guided

- **WHEN** a denied person whose session carries a first name, a full name and an email opens the refusal route with `contactSupportLink` configured
- **THEN** the card SHALL greet them by first name, show their name and email, list the two steps, and offer sign-out, an access re-check and a request-access action targeting `contactSupportLink`

#### Scenario: Denied session lacks identity details

- **WHEN** the session carries no first name or no email
- **THEN** the greeting SHALL omit the name, the first step SHALL NOT mention a displayed address, and no empty account block SHALL be rendered

#### Scenario: Support link is not configured

- **WHEN** a denied person opens the refusal route and `contactSupportLink` is empty
- **THEN** the request-access action SHALL be absent while sign-out and the access re-check remain

#### Scenario: Invitation link is no longer valid

- **WHEN** the enrollment preview is refused with `404 free_enrollment_link_invalid`
- **THEN** the card SHALL say the link is no longer valid and to ask the inviter for a new one
- **AND** it SHALL offer no retry, join, sign-out or support action and SHALL have no footer

#### Scenario: Invitation link stops being valid while the page is open

- **WHEN** the invitation was shown and accepting the terms or joining is then refused as `404 free_enrollment_link_invalid`
- **THEN** the card SHALL say the link is no longer valid, as for a preview refused that way, without a retry, join or support action

#### Scenario: Invitation cannot be checked or joined right now

- **WHEN** the enrollment preview, the terms acceptance or the join fails for any reason other than `404 free_enrollment_link_invalid`
- **THEN** the card SHALL report a temporary problem with a retry action, no support action, and SHALL NOT state that the link is invalid

#### Scenario: Transient verification failure

- **WHEN** admission verification fails transiently
- **THEN** the same card SHALL offer a retry and configured support without falsely reporting definitive denial

#### Scenario: Invitation checking and valid states omit support

- **WHEN** a person opens a Free invitation that is still checking or is valid
- **THEN** the card SHALL show no contact-support action while retaining the join action for a valid invitation
