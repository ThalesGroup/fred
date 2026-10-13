## RENAMED Requirements

- FROM: `### Requirement: Admission feedback uses the shared Fred error presentation`
- TO: `### Requirement: Admission feedback uses one welcoming card family`

## MODIFIED Requirements

### Requirement: Admission feedback uses one welcoming card family

Admission denial, every state of the Free enrollment route and transient admission-verification failures SHALL be presented in one compact card showing the deployment's configured site display name, a single page heading that labels the card, a body and an optional footer. These states SHALL NOT use the generic error page or an error icon. The platform name SHALL always come from the configured site display name. These screens SHALL remain reachable without protected bootstrap or team/resource loading; ordinary error pages SHALL retain their existing action.

The denial screen SHALL greet the signed-in person by first name, falling back to a greeting without a name, SHALL show the signed-in account (name and email, whichever is known) and SHALL list two numbered steps: request access from support, then come back and check access. It SHALL offer sign-out, an access re-check, and a request-access action that opens `contactSupportLink` in a new tab. When `contactSupportLink` is not configured the request-access action SHALL be hidden and no alternative contact SHALL be invented. When no email is known, the steps SHALL NOT refer to a displayed address, and an account block with neither name nor email SHALL NOT be rendered.

The enrollment screen SHALL announce an invitation, show the team in its own surface and offer a single join action; support SHALL use `contactSupportLink` when configured. A preview refused as `404 free_enrollment_link_invalid` SHALL be reported as a link that is no longer valid, with guidance to ask the inviter for a new link, without a retry action and without a team name. Any other preview failure, and a failed enrollment, SHALL be reported as a temporary problem with a retry action and SHALL NOT be reported as an invalid link. Sign-out SHALL NOT appear on the enrollment route in any state.

#### Scenario: Denied or invalid enrollment route

- **WHEN** a denied person opens the refusal route or an invalid Free link
- **THEN** the screen SHALL use the shared card, without the generic error page, and its configured support destination without normal protected product loading

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
- **AND** it SHALL offer no retry, join or sign-out action and SHALL show a footer only when a support link is configured

#### Scenario: Invitation cannot be checked or joined right now

- **WHEN** the enrollment preview fails for any other reason, or accepting the terms or joining fails
- **THEN** the card SHALL report a temporary problem with a retry action and SHALL NOT state that the link is invalid

#### Scenario: Transient verification failure

- **WHEN** admission verification fails transiently
- **THEN** the same card SHALL offer a retry without falsely reporting definitive denial
