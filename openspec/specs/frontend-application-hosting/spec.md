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

### Requirement: Evaluation is provided by a hosted application

Fred SHALL expose evaluation functionality through a registered hosted application. Fred MUST NOT render built-in evaluation screens in team settings or issue evaluator-specific requests from Activity, task rehydration or task event subscriptions. The removal MUST preserve application admission, permissions, reusable shared UI components and evaluation data.

#### Scenario: Team settings navigation
- **WHEN** a user opens team settings
- **THEN** the navigation contains no built-in Evaluations entry and the remaining sections retain their existing access rules

#### Scenario: Old settings URL
- **WHEN** a team member follows a legacy settings/evaluations URL
- **THEN** Fred applies the existing unknown-section redirect to that team's Members settings without loading evaluator screens

#### Scenario: Activity is independent of evaluator availability
- **WHEN** a user opens team Activity
- **THEN** Fred queries its control-plane and knowledge-flow task services without querying the external evaluator

#### Scenario: External evaluator remains usable
- **WHEN** the evaluator is registered and admitted for a team
- **THEN** users can open it through Apps under the existing host protocol and permission checks

#### Scenario: Reload does not reconnect to evaluator tasks
- **WHEN** a user reloads Fred
- **THEN** task rehydration only queries Fred's own task services and does not subscribe to evaluator task events
