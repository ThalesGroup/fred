## MODIFIED Requirements

### Requirement: Activation and migration are explicit

An absent admission authority SHALL initialize with filtering inactive until explicit administrator activation. Activation SHALL require a saved valid rule or at least one independent individual/team source and SHALL be refused if the acting administrator would lose their last admission source. Saving a policy or changing access exceptions while filtering is active SHALL apply the same actor safeguard atomically. Existing root bootstrap safeguards SHALL remain intact. Activation concurrent with a nonempty legacy-file gate SHALL be rejected; readers SHALL refuse an active conflicting gate. Policy, imported entries and membership SHALL survive restarts and temporary filtering disablement.

#### Scenario: Upgrade does not silently activate filtering

- **WHEN** operators deploy the required migration with empty admission state
- **THEN** filtering SHALL remain inactive until an admission source is prepared and an administrator explicitly activates it

#### Scenario: Administrator would lock themselves out

- **WHEN** activation, a policy save or an exception mutation would withdraw the actor's last admission source
- **THEN** the operation SHALL be refused with an actionable explanation and leave prior state intact

#### Scenario: Rule is not configured

- **WHEN** an administrator attempts activation without any saved rule or independent admission source
- **THEN** activation SHALL be refused without changing the filtering state

#### Scenario: Conflicting whitelist modes

- **WHEN** an administrator attempts activation while a nonempty legacy file gate is active
- **THEN** activation SHALL be refused without changing state, and readers SHALL fail closed if conflicting active state exists

The page SHALL offer a top-right filtering action in the page header across every tab with explicit confirmation. Before activation, a read-only population review SHALL show identifiable allowed, blocked and uncertain users under the saved rule and current independent sources, with counts and observation time. Stale/missing/conflicted evidence SHALL be uncertain rather than declared blocked. A preview SHALL NOT grant access or save drafts. Activation confirmation SHALL reject a changed policy revision and retain the actor safeguard.

#### Scenario: Review before activating

- **WHEN** an administrator requests activation with prepared saved admission sources
- **THEN** a confirmation dialog SHALL display the population dry run before any activation mutation
- **WHEN** they cancel
- **THEN** filtering SHALL remain unchanged

#### Scenario: Whitelist-only activation

- **WHEN** no rule is saved but the actor has an independent current exception
- **THEN** activation SHALL be allowed and other people without independent sources SHALL be refused

#### Scenario: Evidence cannot establish an outcome

- **WHEN** selected claim evidence is missing, expired or conflicted and no independent source applies
- **THEN** the preview SHALL mark that person uncertain without inventing token values or granting access

Before enabling through the UI, the initial-import status SHALL be known. If existing-user import has not completed, the activation confirmation SHALL explicitly warn that existing users have not been imported and offer Continue without importing or Go to whitelist. Continuing SHALL remain subject to the saved-policy population review and existing activation safeguards. Choosing Go to whitelist SHALL send no activation mutation and open Whitelist > Users. A completed import SHALL use normal activation confirmation. Loading or failed import status SHALL prevent enabling confirmation until retried successfully; disabling SHALL NOT depend on import completion.

#### Scenario: Continue without initial import

- **WHEN** an administrator reviews activation with an incomplete initial import
- **THEN** the modal SHALL explicitly present the missing-import warning and both choices
- **WHEN** they choose Continue without importing with valid fresh preview and admission sources
- **THEN** the UI SHALL request activation using the reviewed revision without importing users

#### Scenario: Navigate to import instead of activating

- **WHEN** an administrator chooses Go to whitelist in the missing-import confirmation
- **THEN** filtering SHALL remain unchanged, no activation mutation SHALL be sent and Whitelist > Users SHALL open

#### Scenario: Import already completed

- **WHEN** the initial import has completed and an administrator requests activation
- **THEN** normal population-review confirmation SHALL appear without the missing-import warning

#### Scenario: Import status unavailable

- **WHEN** initial-import status is loading or fails while enabling is being reviewed
- **THEN** activation confirmation SHALL remain unavailable with loading or retry feedback
- **AND** unavailable import status SHALL NOT prevent disabling filtering

### Requirement: Access administration has readable section navigation

The page SHALL provide localized Rules and Whitelist tabs using the shared Fred navigation presentation. Only the active panel SHALL be exposed visually or to keyboard and assistive navigation. The rule draft, user selection and paging SHALL survive tab changes without implicit saving or admission mutations. Whitelist SHALL retain its heading and provide localized Users and Teams sub-tabs. Import existing users and individual exceptions SHALL appear in Users; independent team authorization SHALL appear in Teams, without a separate top-level Teams tab. A top-right filtering action in the page header SHALL remain available across all tabs, without a separate Activation tab. Ordinary content, secondary explanations and section headings SHALL use a consistent readable typography scale across the page and its dialogs. Repeated explanations SHALL be removed while authorization exceptions, revocation consequences, validation and errors remain understandable.

#### Scenario: Return to an unsaved rule or selected users

- **WHEN** an administrator changes a draft or selects users, navigates to another tab and returns
- **THEN** those local changes SHALL remain and no save or authorization mutation SHALL have been sent by navigation

#### Scenario: Navigate sections using the keyboard

- **WHEN** an administrator uses arrow keys on the section strip
- **THEN** focus and selection SHALL move using the shared tab behavior and only the associated panel SHALL be exposed

#### Scenario: Read page and modal content

- **WHEN** an administrator reads conditions, selection dialogs or invitation history
- **THEN** ordinary text and secondary help SHALL use consistent readable sizes, with errors and revocation guidance retained

#### Scenario: Separate whitelist management

- **WHEN** an administrator opens Whitelist
- **THEN** its heading and Users/Teams sub-tabs SHALL be displayed
- **AND** only the selected sub-panel SHALL be exposed, with import/individual controls in Users and live team authorization in Teams

#### Scenario: Filtering action available in the header

- **WHEN** an administrator changes top-level or whitelist sub-tabs
- **THEN** the filtering action SHALL remain at the top right of the page header with the same activation guards
