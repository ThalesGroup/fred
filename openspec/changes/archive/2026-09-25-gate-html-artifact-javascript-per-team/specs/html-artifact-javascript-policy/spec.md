## Purpose

Governs whether model-authored JavaScript may execute inside a rendered HTML
artifact. Execution is a per-team posture decision an operator takes
explicitly; every team keeps HTML/CSS generation regardless.

## ADDED Requirements

### Requirement: JavaScript execution is denied unless a team is opted in

The platform SHALL treat JavaScript execution in a rendered HTML artifact as
denied for a team unless an administrator has explicitly enabled it for that
team. Enabling the HTML artifact capability for a team SHALL NOT by itself
grant JavaScript execution.

#### Scenario: Team enabled without the JavaScript option

- **WHEN** an administrator enables the HTML artifact capability for a team and
  leaves the JavaScript option unset
- **THEN** members of that team can generate and view HTML/CSS artifacts
- **AND** no script in those artifacts executes

#### Scenario: Team explicitly opted in

- **WHEN** an administrator enables the HTML artifact capability for a team and
  turns the JavaScript option on
- **THEN** members of that team can generate artifacts whose script executes

#### Scenario: Two teams, different postures

- **WHEN** one team is opted in and another is not
- **THEN** an artifact viewed by a member of the opted-in team executes its
  script
- **AND** the same capability used from the other team produces an artifact
  whose script does not execute

### Requirement: Restricted mode denies execution by capability, not by filtering

When a team is not opted in, the platform SHALL render the artifact in a way
that makes script execution impossible, rather than attempting to detect and
remove script from the content. Inline script elements, inline event handler
attributes, and `javascript:` URLs SHALL all be inert.

#### Scenario: Script element present in a restricted artifact

- **WHEN** an artifact containing a script element is displayed for a team that
  is not opted in
- **THEN** the script does not run
- **AND** the rest of the page renders normally

#### Scenario: Inline event handler in a restricted artifact

- **WHEN** an artifact containing an inline event handler attribute is
  displayed for a team that is not opted in
- **AND** the user triggers the corresponding interaction
- **THEN** no handler code runs

### Requirement: Network egress stays blocked in both modes

The platform SHALL block subresource fetches and network egress from a rendered
artifact whether or not the team is opted in. Denying script execution SHALL
NOT be treated as sufficient, because markup alone can initiate a request that
carries data in its URL.

#### Scenario: Remote image reference in a restricted artifact

- **WHEN** an artifact referencing a remote image URL is displayed for a team
  that is not opted in
- **THEN** no request is made to that remote host

#### Scenario: Remote image reference in a permissive artifact

- **WHEN** an artifact referencing a remote image URL is displayed for an
  opted-in team
- **THEN** no request is made to that remote host

### Requirement: The model is told which mode applies

The platform SHALL tell the model whether JavaScript is available for the
current team before it authors an artifact, so that a restricted team does not
receive a page whose interactive parts silently do nothing.

#### Scenario: Restricted team

- **WHEN** an agent belonging to a team that is not opted in is about to author
  an artifact
- **THEN** the instructions it receives do not offer JavaScript

#### Scenario: Opted-in team

- **WHEN** an agent belonging to an opted-in team is about to author an
  artifact
- **THEN** the instructions it receives state that JavaScript is available and
  describe the constraints that still apply

### Requirement: Script a team may not run is never persisted

When a team is not opted in, the render request SHALL be rejected if the
submitted page contains script, and the rejection SHALL be reported back to the
model as a recoverable error so it can re-render without script. The rejected
page SHALL NOT be stored or displayed.

#### Scenario: Model submits script for a restricted team

- **WHEN** an agent belonging to a team that is not opted in submits a page
  containing script
- **THEN** the render is refused
- **AND** the model receives an error explaining that JavaScript is not
  available for this team
- **AND** no artifact is created from the refused page

#### Scenario: Model retries without script

- **WHEN** the model re-submits the same page with the script removed
- **THEN** the artifact is created and displayed

### Requirement: Revoking the right takes effect immediately, including on existing artifacts

The viewer SHALL resolve the team's current right at display time rather than
relying on a value recorded when the artifact was created. Withdrawing the
JavaScript option from a team SHALL make previously generated artifacts of that
team inert, including artifacts already present in conversation history.

#### Scenario: Right withdrawn after interactive artifacts were produced

- **GIVEN** a team was opted in and produced artifacts containing working
  script
- **WHEN** an administrator turns the JavaScript option off for that team
- **AND** a member of that team reopens one of those earlier artifacts
- **THEN** its script does not run

#### Scenario: Right granted after restricted artifacts were produced

- **GIVEN** a team was not opted in and produced artifacts whose script never ran
- **WHEN** an administrator turns the JavaScript option on for that team
- **AND** a member reopens one of those earlier artifacts
- **THEN** its script runs

### Requirement: An administrator can change a team's setting after enabling

The platform SHALL let an administrator read and change a team's JavaScript
option for an already-enabled capability, without having to disable and
re-enable the capability for that team.

#### Scenario: Changing the option for an enabled team

- **WHEN** an administrator opens the settings of a team for which the
  capability is already enabled
- **THEN** the current value of the JavaScript option is shown
- **AND** changing it and saving updates the team's setting

#### Scenario: Disable and re-enable preserves the prior value

- **WHEN** an administrator disables the capability for a team and later
  re-enables it
- **THEN** the JavaScript option returns to the value it had before the disable
