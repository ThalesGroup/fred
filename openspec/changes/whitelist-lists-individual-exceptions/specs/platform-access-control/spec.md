## MODIFIED Requirements

### Requirement: Platform administrators manage live exceptions

Only people holding the existing platform-management permission SHALL read or modify the platform access administration surface. It SHALL provide paginated individual exception management using Fred's local users, team authorization and Free-team controls, filtering state, effective admission sources displayed by type and team name without team UIDs, own-session claim selection, rule editing and draft preview. Team administrators and team managers SHALL NOT obtain this authority through their existing roles. Removing an individual exception SHALL NOT remove an identity or revoke independent team sources. Rule updates SHALL be explicit, atomic and versioned; stale concurrent saves SHALL return a conflict without overwriting another administrator's changes. Preview SHALL NOT change filtering, policy, T0, membership or evidence selected only by the proposed rule.

#### Scenario: Administrator authorizes a Fred user or team

- **WHEN** an administrator adds an existing Fred user or authorizes an existing team
- **THEN** eligible users SHALL be admitted on their next request without restart or JWT renewal

#### Scenario: Administrator authorizes a selected user list

- **WHEN** a platform administrator selects any nonempty list of existing Fred users and grants admission
- **THEN** the operation SHALL atomically add removable manual exceptions without overwriting existing sources
- **WHEN** the list includes an unknown user or is submitted by a non-platform administrator
- **THEN** no exceptions SHALL be granted

#### Scenario: Leaving an allowed or Free team revokes its global source

- **WHEN** a person leaves or is removed from an allowed or Free team
- **THEN** the next direct, cached-token or delegated request on any participating reader SHALL no longer use that team for platform admission
- **AND** the person SHALL be refused when no independent source remains, while other grants and ordinary membership of other teams remain unchanged

#### Scenario: Unauthorized administrative call

- **WHEN** an ordinary person, team administrator or team manager requests claim discovery, preview, policy updates or exception administration
- **THEN** the call SHALL be refused and admission state SHALL remain unchanged

#### Scenario: Administrator sees provenance

- **WHEN** an administrator lists allowed users
- **THEN** individual entries SHALL identify manual or T0 origin and derived entries SHALL identify each authorized or Free team

#### Scenario: Preview explains an unsaved rule

- **WHEN** an administrator tests a draft against their verified token
- **THEN** the UI SHALL show per-condition results, missing or incompatible claim explanations, the aggregate rule result and whether they would be admitted with filtering active including independent sources, without saving the draft

#### Scenario: Two administrators save concurrently

- **WHEN** a save uses an older revision than the active policy
- **THEN** the system SHALL return HTTP 409 and retain the newer policy, while the UI preserves the unsaved draft and explains the conflict

The paginated user listing SHALL accept an optional restriction to people holding an individual exception (manual or T0). With the restriction, both the returned page and its total SHALL cover only those people; without it, every known user SHALL be listed as before. Without the restriction, with or without a search, rows SHALL be returned in a stable alphabetical order: by username without regard to case, people without a username after all others, the user identifier breaking ties. With the restriction, the most recently granted exceptions SHALL come first, that alphabetical order breaking ties between exceptions granted at the same time. Each row's admission sources SHALL be reported identically in both modes, the individual source carrying its grant time.

User rows SHALL show identifier, first name and last name using the team-member table presentation, then when the individual access was added in the administrator's locale, its origin (manual or initial import), and, when the person has other admission sources (rule, platform administration, authorized teams, link-access teams), one compact "other access" indicator whose detail lists those sources grouped by kind with team names, without repeating the individual access. That detail SHALL be reachable by pointer and by keyboard and SHALL be exposed to assistive technology. A row with no other source SHALL leave that cell empty, so that it is visible that removing the person withdraws their access. The Users block SHALL carry a heading naming the whitelisted users, placed above its search and actions. The Users list SHALL show, by default and without any search, only the people holding an individual exception, paginated by the server with the real total and never loading the full directory. Its search SHALL narrow that list and SHALL be sent after a pause in typing, restarting at the first page. Only the current response SHALL provide rows; a loading or failed request SHALL hide previous rows. Each listed row SHALL offer removal of the individual exception and SHALL confirm a successful removal. A list with no individual exception SHALL say so and point to the add action, and SHALL be distinguishable from a search without match.

Adding people SHALL go through a dialog that searches all known users on the server, a bounded page of matches at a time, and that states when more people match than are shown. The selection SHALL survive successive searches without a fixed total cap. People who already hold an individual exception SHALL be shown as such and SHALL NOT be selectable. One confirmation SHALL grant the whole selection; SQL batches SHALL remain bounded and grants atomic. A successful grant SHALL be confirmed, close the dialog and refresh the list; a failed grant SHALL keep the dialog and its selection.

#### Scenario: Grant more than 100 people

- **WHEN** an administrator submits more than 100 known identities
- **THEN** all missing exceptions SHALL be added atomically, duplicate identities ignored and existing origins preserved
- **WHEN** an identity in a later batch is unknown
- **THEN** the complete operation SHALL roll back

#### Scenario: Default list shows individual exceptions only

- **WHEN** an administrator opens the Users tab on a platform where some people hold an individual exception and others are admitted only by the rule, a team or administration
- **THEN** only the people holding an individual exception SHALL be listed, most recent grant first, with a total counting them alone

#### Scenario: Exceptions granted together stay alphabetical

- **WHEN** several people received their individual exception in one operation and the listing is requested with the restriction
- **THEN** they SHALL appear together, in alphabetical order among themselves, after any exception granted later

#### Scenario: Row shows date, origin and other access

- **WHEN** a listed person holds a manual exception and belongs to an authorized team, and another holds only an exception from the initial import
- **THEN** the first row SHALL show its grant date, a manual origin and an other-access indicator whose detail names the team
- **AND** the second row SHALL show its grant date, an initial-import origin and an empty other-access cell

#### Scenario: Other access grouped by kind

- **WHEN** a listed person is also accepted by the rule, administers the platform, belongs to two authorized teams and to one link-access team
- **THEN** the row SHALL show a single other-access indicator
- **AND** its detail SHALL list the rule, the administrator role, the two authorized teams together by name, and the link-access team by name

#### Scenario: Listing restricted to exceptions combined with a search

- **WHEN** the listing is requested with the restriction and a search text
- **THEN** only people who hold an individual exception and match the search SHALL be returned and counted

#### Scenario: Listing without the restriction

- **WHEN** the listing is requested without the restriction
- **THEN** every known user SHALL be listed and counted, in alphabetical order

#### Scenario: Nobody holds an individual exception

- **WHEN** an administrator opens the Users tab and no individual exception exists
- **THEN** the page SHALL state that the list is empty and point to the add action, with wording different from a search without match

#### Scenario: Add people from the dialog

- **WHEN** an administrator opens the add dialog, searches twice, picks one person from each search and confirms
- **THEN** both people SHALL receive a manual exception in one operation, a confirmation SHALL be shown, the dialog SHALL close and the list SHALL show them

#### Scenario: Person already on the whitelist

- **WHEN** a search in the add dialog matches a person who already holds an individual exception
- **THEN** that person SHALL be shown as already having individual access and SHALL NOT be selectable

### Requirement: Access administration has readable section navigation

The page SHALL provide one level of navigation with localized Rules, Users and Teams tabs using the shared Fred navigation presentation, without sub-tabs. Only the active panel SHALL be exposed visually or to keyboard and assistive navigation, and no listing SHALL be requested for a tab that is not shown. The rule draft, the user search, page and page size SHALL survive tab changes without implicit saving or admission mutations. Users and Teams are the two halves of the whitelist: each SHALL open with a heading naming it and a short description stating that its entries always have access whatever the rule, placed above its controls. Import existing users and individual exceptions SHALL appear in Users; independent team authorization SHALL appear in Teams. A top-right filtering action in the page header SHALL remain available across all tabs, without a separate Activation tab. Ordinary content, secondary explanations and section headings SHALL use a consistent readable typography scale across the page and its dialogs. Repeated explanations SHALL be removed while authorization exceptions, revocation consequences, validation and errors remain understandable.

#### Scenario: Return to an unsaved rule or selected users

- **WHEN** an administrator changes a draft or searches the user list, navigates to another tab and returns
- **THEN** those local changes SHALL remain and no save or authorization mutation SHALL have been sent by navigation

#### Scenario: Navigate sections using the keyboard

- **WHEN** an administrator uses arrow keys on the section strip
- **THEN** focus and selection SHALL move using the shared tab behavior and only the associated panel SHALL be exposed

#### Scenario: Read page and modal content

- **WHEN** an administrator reads conditions, selection dialogs or invitation history
- **THEN** ordinary text and secondary help SHALL use consistent readable sizes, with errors and revocation guidance retained

#### Scenario: Separate whitelist management

- **WHEN** an administrator opens Users, then Teams
- **THEN** each SHALL show its own heading and description
- **AND** only the selected panel SHALL be exposed, with import/individual controls in Users and live team authorization in Teams

#### Scenario: Filtering action available in the header

- **WHEN** an administrator changes tabs
- **THEN** the filtering action SHALL remain at the top right of the page header with the same activation guards
