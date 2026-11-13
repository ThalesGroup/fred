## ADDED Requirements

### Requirement: Administrators pre-authorize people by email

A platform administrator SHALL be able to whitelist an email address that matches no identity in the configured directory. The address SHALL be stored normalized (trimmed, lowercased) as a removable pending entry. When a person whose request would otherwise be refused presents a token whose email claim matches a pending entry, and the token does not carry `email_verified: false`, the system SHALL atomically replace the pending entry with a manual individual exception for that person and admit the request. Requests already admitted SHALL NOT read pending entries.

#### Scenario: Unknown person is whitelisted before first sign-in

- **GIVEN** filtering is enabled and `jane@example.org` matches no known identity
- **WHEN** an administrator adds `Jane@Example.org` and Jane later signs in with that verified email
- **THEN** Jane SHALL be admitted and SHALL appear in the whitelist as a manual exception, and the pending entry SHALL be gone

#### Scenario: Unverified email does not claim an entry

- **WHEN** the token carries the matching email with `email_verified: false`
- **THEN** the pending entry SHALL remain and the request SHALL be refused unless another admission source exists

#### Scenario: Email of a known identity

- **WHEN** an administrator adds an email that belongs to a known identity
- **THEN** the system SHALL return HTTP 409 `platform_access_email_known` and add nothing

#### Scenario: Removal and authority

- **WHEN** an administrator removes a pending entry, or a non-platform administrator calls any pending-email operation
- **THEN** the entry SHALL be deleted, respectively the call SHALL be refused without change

### Requirement: Administrators clean up redundant exceptions

The whitelist SHALL offer a filter with three exclusive choices: all exceptions, exceptions of people also admitted by the saved rule, and exceptions of people with no admission source other than that exception. The filter SHALL apply server-side, before pagination, and the total SHALL count the filtered set. Rule overlap SHALL use the stored verified evidence and the saved rule. Team overlap SHALL be resolved without one authorization check per person. Each row SHALL be selectable, and a header control SHALL select every exception matching the current search and filter across all pages, after which individual rows MAY be deselected. Removing the selection SHALL be one atomic operation. When filtering is active and the acting administrator would lose their last admission source, the whole removal SHALL be refused.

#### Scenario: Rule widened

- **GIVEN** a saved rule that now matches people who also hold an individual exception
- **WHEN** an administrator selects "Admitted by the rule"
- **THEN** only those exceptions SHALL be listed and the total SHALL equal their count

#### Scenario: Whitelist only

- **WHEN** an administrator selects "Whitelist only"
- **THEN** only exceptions of people with no rule, team, Free or administrator source SHALL be listed

#### Scenario: Remove every filtered row except one

- **GIVEN** the "Admitted by the rule" filter lists 240 people over several pages
- **WHEN** the administrator checks the header box, unchecks one row and confirms removal
- **THEN** 239 exceptions SHALL be removed in one transaction and the unchecked one SHALL remain

#### Scenario: Removal would lock the administrator out

- **WHEN** the selection includes the acting administrator's last admission source while filtering is active
- **THEN** no exception SHALL be removed and the existing safeguard error SHALL be returned

#### Scenario: Rule uses a claim not yet observed

- **GIVEN** the saved rule now uses a claim path that a whitelisted person's stored evidence does not contain
- **WHEN** an administrator selects either filter
- **THEN** that person SHALL be listed in neither, and the response SHALL report the count of such people
- **WHEN** that person makes a new request carrying the claim
- **THEN** a later read SHALL classify them by the rule
