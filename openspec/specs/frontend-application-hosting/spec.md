# frontend-application-hosting Specification

## Purpose

Defines browser capabilities and containment guarantees for team applications admitted into FRED's hosted application iframe.

## Requirements

### Requirement: Hosted application local downloads

FRED SHALL permit an admitted hosted application to initiate a browser file download of application-owned local content from its iframe. This permission MUST preserve the established application admission, host-owned authentication and request routing, parent navigation authority, and protocol boundaries; it MUST NOT grant unrelated top-navigation or sandbox-escape permissions.

#### Scenario: Application downloads generated content

- **WHEN** an authorized hosted application initiates a download of a locally created Blob from its iframe
- **THEN** the browser completes a download with the requested filename and bytes without an upstream file URL or access to FRED credentials

#### Scenario: Frame is not admitted

- **WHEN** an application is not authorized for the collaborative team or the selected space is personal
- **THEN** FRED creates no hosted application iframe and grants no download capability through that host

#### Scenario: Existing containment remains

- **WHEN** FRED enables downloads for an admitted application frame
- **THEN** the frame retains its existing reviewed sandbox permissions and gains no top-navigation, popup sandbox-escape, parent routing, or host authentication authority

#### Scenario: Existing application protocol stays compatible

- **WHEN** an existing protocol-`"1"` application initiates a local file download
- **THEN** it uses browser behavior without a new host message, SDK API, protocol version, or npm package release

#### Scenario: Production host works in a real browser

- **WHEN** an admitted application's user action creates known local content and initiates a download inside FRED's production application host iframe in a real browser
- **THEN** the browser download has the expected filename and bytes
