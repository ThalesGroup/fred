## MODIFIED Requirements

### Requirement: Announcement content model

An announcement SHALL carry a type, which is either `banner` or `patch_note`
and SHALL NOT change after creation. An announcement created without a type
SHALL be a `banner`, and every announcement that existed before types were
introduced SHALL be a `banner`.

A `banner` SHALL carry a severity, localized text, and two independent flags
controlling whether it is shown and whether a user may dismiss it.

Severity SHALL be one of `info`, `warning`, `error`, `success`. Each severity
SHALL determine the banner's colour and icon; neither is separately authorable.

`title`, `description_short` and `description_long` SHALL each be a map from
locale code to text, supporting at least `fr` and `en`. Text SHALL be resolved
against the viewer's active locale, falling back to `en` when that locale has
no entry.

`description_short` and `description_long` SHALL be interpreted as markdown.

A `patch_note` SHALL carry one markdown body per locale, supporting at least
`fr` and `en` and resolved with the same `en` fallback. It SHALL carry a
plain-text title per locale (at most 200 characters, no markdown), and the
locales with a non-empty title SHALL be exactly the locales with a non-empty
body. It SHALL NOT carry an authored short description or severity, and SHALL
always be dismissible by the user.

An announcement SHALL carry a content version. A banner's content version
SHALL change whenever any of its text, severity, or `dismissible` flag changes,
and whenever a disabled banner is enabled again. A patch note's content version
SHALL change only when it is enabled again after its title or body was changed
while it was disabled. Disabling an announcement SHALL NOT change it.

Replacing an announcement's content SHALL NOT change whether it is delivered.
Enabling and disabling SHALL be a distinct operation.

#### Scenario: Locale resolution with fallback

- **WHEN** an announcement has a `fr` and an `en` title and the viewer's locale is `fr`
- **THEN** the `fr` title is displayed

#### Scenario: Missing locale falls back to English

- **WHEN** an announcement has only an `en` title and the viewer's locale is `fr`
- **THEN** the `en` title is displayed

#### Scenario: Severity fixes the icon

- **WHEN** a banner has severity `warning`
- **THEN** the banner renders the warning icon and warning colour
- **AND** no authored icon or colour can override them

#### Scenario: Rejecting an unknown severity

- **WHEN** an administrator submits a banner whose severity is not one of the four allowed values
- **THEN** the request is rejected with a validation error and nothing is persisted

#### Scenario: Existing announcements become banners

- **GIVEN** announcements created before types existed
- **WHEN** the deployment is upgraded
- **THEN** each of them is a `banner` and renders exactly as before

#### Scenario: Patch note requires a title

- **WHEN** an administrator submits a patch note whose title is blank in every locale
- **THEN** the request is rejected with a validation error and nothing is persisted

#### Scenario: Patch-note title and body cover the same locales

- **WHEN** an administrator submits a patch note with a `fr` and an `en` body but only an `en` title
- **THEN** the request is rejected with a validation error and nothing is persisted

#### Scenario: Patch-note title heads the user dialog

- **GIVEN** an active patch note titled `Nouveautés 3.4` in `fr`
- **WHEN** a user whose locale is `fr` sees the patch-note dialog
- **THEN** the dialog's header reads `Nouveautés 3.4`

#### Scenario: Type cannot change

- **GIVEN** an existing banner
- **WHEN** an administrator submits an update that sets its type to `patch_note`
- **THEN** the request is rejected with a validation error and the banner is unchanged

### Requirement: Administering announcements

The system SHALL let a platform administrator list, create, update, delete, and
enable or disable announcements of both types. Every one of those operations
SHALL require platform-administration authority.

Creating or updating a banner SHALL require a non-empty `title` and
`description_short` for at least one locale. A banner's `description_long`
SHALL be optional. Creating or updating a patch note SHALL require a non-empty
body for at least one locale.

Each administrative mutation SHALL emit an audit record naming the acting user
and the affected announcement.

#### Scenario: Administrator creates an announcement

- **WHEN** a platform administrator submits a valid announcement
- **THEN** it is persisted, returned with its identifier, type and content version, and an audit record is emitted

#### Scenario: Non-administrator is refused

- **WHEN** an authenticated user without platform-administration authority calls any announcement administration operation
- **THEN** the request is refused and no announcement is created, changed, or deleted

#### Scenario: Announcement without a short description is rejected

- **WHEN** an administrator submits a banner whose `description_short` is empty for every locale
- **THEN** the request is rejected with a validation error

#### Scenario: Patch note without a body is rejected

- **WHEN** an administrator submits a patch note whose body is empty for every locale
- **THEN** the request is rejected with a validation error and nothing is persisted

#### Scenario: Editing bumps the content version

- **WHEN** an administrator changes the text of an existing banner
- **THEN** its content version changes

#### Scenario: Toggling does not require a full resubmission

- **WHEN** an administrator disables an enabled announcement
- **THEN** the announcement is retained with its content intact and stops being delivered to users
- **AND** its content version is unchanged

#### Scenario: Re-enabling relaunches the announcement for everyone

- **WHEN** an administrator enables a banner that was disabled
- **THEN** its content version changes, so the banner appears again for users who had dismissed the previous run

### Requirement: Delivering active announcements

The system SHALL expose the set of enabled banners to any authenticated user.
That set SHALL NOT include patch notes. Announcements SHALL NOT be readable
without authentication.

The delivered set SHALL reflect an administrator's change within approximately
one minute for a user who leaves the application open, and immediately when the
application regains window focus or is loaded.

#### Scenario: Enabled announcements are delivered

- **WHEN** an authenticated user's client requests the active announcements and two banners are enabled
- **THEN** both are returned, and disabled ones are not

#### Scenario: Active patch note is not in the banner set

- **GIVEN** one enabled banner and one enabled patch note
- **WHEN** an authenticated user's client requests the active announcements
- **THEN** only the banner is returned

#### Scenario: Unauthenticated access is refused

- **WHEN** an unauthenticated client requests the active announcements
- **THEN** the request is refused

#### Scenario: A newly enabled announcement reaches an open session

- **WHEN** an administrator enables a banner while a user has the application open and idle
- **THEN** that user's client displays the banner without a manual reload, within about a minute

#### Scenario: Returning to the tab refreshes immediately

- **WHEN** a user switches back to the application's browser tab
- **THEN** the client re-reads the active announcements before the next polling interval elapses

### Requirement: Rendering the banner stack

Enabled banners SHALL render as full-width banners at the top of the
application, above the routed content and pushing it down rather than
overlaying it. They SHALL only render for an authenticated user, and SHALL NOT
render on pre-authentication screens. Patch notes SHALL NOT render as banners.

When several banners are enabled, all of them SHALL render, stacked and
ordered by severity — `error`, then `warning`, then `success`, then `info` —
and, within one severity, by creation date, oldest first.

Each banner SHALL show its severity icon, its title, and its rendered
`description_short`, followed by an actions toolbar.

#### Scenario: Multiple announcements stack in severity order

- **WHEN** an `info` and an `error` banner are both enabled
- **THEN** both banners render, with the `error` banner above the `info` one

#### Scenario: Content is pushed down, not covered

- **WHEN** one or more banners render
- **THEN** the routed page content starts below them and remains fully reachable

#### Scenario: Nothing renders before authentication

- **WHEN** an unauthenticated visitor reaches a pre-authentication screen and banners are enabled
- **THEN** no banner renders

#### Scenario: No enabled announcements renders nothing

- **WHEN** no banner is enabled
- **THEN** no banner area renders and the page content occupies the full height

## ADDED Requirements

### Requirement: One active patch note at a time

At most one patch note SHALL be enabled at any time. Enabling a patch note
SHALL disable the patch note that was enabled, if any, as part of the same
operation, so that no reader can observe two enabled patch notes or none in
between. Enabling a patch note SHALL NOT change any banner. Creating a patch
note directly in the enabled state SHALL follow the same rule.

#### Scenario: Activating a patch note replaces the active one

- **GIVEN** patch note A is enabled and patch note B is disabled
- **WHEN** an administrator enables B
- **THEN** B is enabled and A is disabled
- **AND** the admin listing shows exactly one enabled patch note

#### Scenario: Banners are not affected

- **GIVEN** two enabled banners and an enabled patch note A
- **WHEN** an administrator enables patch note B
- **THEN** both banners stay enabled

#### Scenario: Concurrent activations leave one active patch note

- **WHEN** two administrators enable two different patch notes at the same moment
- **THEN** exactly one patch note is enabled afterwards, and the other request either wins or is refused without leaving two enabled

### Requirement: Patch-note dialog at application load

When an authenticated user loads the application, the system SHALL deliver the
enabled patch note together with whether that user dismissed its current
content version, and the client SHALL open a large dialog, unless it is
dismissed, showing the note's title and its body rendered as markdown in the
viewer's locale, with a "Don't show again" checkbox and a Close button at the
bottom. The dialog SHALL open with focus on the dialog itself, at the top of
the note, and its links SHALL open in a new tab. The dialog SHALL NOT open on
pre-authentication screens, and SHALL NOT reopen on in-app navigation or in
another tab during the same sign-in.

A dismissal SHALL hold for the content version it was recorded on. Re-enabling
a disabled patch note SHALL show it again to every user, including those who
dismissed it; editing it while it stays enabled SHALL NOT.

Closing the dialog without the checkbox SHALL only be remembered for the
current user and the current sign-in, so the dialog opens again after the next
sign-in, for another user of the same browser, and for a new content version
of the same note. Closing it with the checkbox,
whether through Close, Escape or a click outside, SHALL record a dismissal for
that user and that patch note on the server.

When browser storage is unavailable, the dialog SHALL still open and
close normally; the only consequence SHALL be that it may open again on the
next load.

#### Scenario: Dialog opens at load

- **GIVEN** an enabled patch note that the user has not dismissed
- **WHEN** the user signs in and the application loads
- **THEN** the patch-note dialog opens with the note's body rendered as markdown, a "Don't show again" checkbox and a Close button

#### Scenario: No enabled patch note, no dialog

- **GIVEN** no patch note is enabled
- **WHEN** the user loads the application
- **THEN** no patch-note dialog opens

#### Scenario: Closed without the checkbox, shown at the next sign-in

- **GIVEN** the patch-note dialog is open
- **WHEN** the user closes it without ticking "Don't show again"
- **THEN** no dismissal is recorded on the server
- **AND** the dialog does not reopen while the user navigates within the application or opens another tab during the same sign-in
- **AND** the dialog opens again at the next application load after a new sign-in
- **AND** the dialog opens for another user signing in on the same browser

#### Scenario: Escape with the checkbox ticked records the dismissal

- **GIVEN** the patch-note dialog is open and "Don't show again" is ticked
- **WHEN** the user closes it with Escape or by clicking outside it
- **THEN** a dismissal for that user and that patch note is stored on the server

#### Scenario: Dismissed for good, not shown again on any device

- **GIVEN** the patch-note dialog is open
- **WHEN** the user ticks "Don't show again" and closes it
- **THEN** a dismissal for that user and that patch note is stored on the server
- **AND** the dialog does not open at later loads, including from another browser or device

#### Scenario: A new patch note is shown again

- **GIVEN** the user dismissed patch note A for good
- **WHEN** an administrator enables patch note B and the user loads the application
- **THEN** the dialog opens with patch note B

#### Scenario: Editing the active patch note does not re-show it

- **GIVEN** the user dismissed the enabled patch note A for good
- **WHEN** an administrator edits A's body while it stays enabled
- **THEN** the dialog does not open for that user at the next load

#### Scenario: Re-enabled, shown again

- **GIVEN** the user dismissed patch note A for good, and an administrator disabled A
- **WHEN** the administrator enables A again, whether or not A's title or body changed meanwhile
- **THEN** the dialog opens with A at the user's next load, even if the user closed A's previous version during the current sign-in

#### Scenario: The dialog opens at the top of the note

- **GIVEN** a patch note whose body contains a link and a code block below the first screen
- **WHEN** the dialog opens
- **THEN** focus is on the dialog itself, the note is shown from its top, and the link opens in a new tab

### Requirement: Reopening the active patch note

While a patch note is enabled, the user's profile menu SHALL offer a "What's
new" entry that opens it in the same dialog, whether or not the user dismissed
it or closed it during this sign-in, without the "Don't show again" checkbox.
The entry SHALL NOT appear when no patch note is enabled.

#### Scenario: Reading a dismissed patch note again

- **GIVEN** the user dismissed the enabled patch note A for good
- **WHEN** the user picks "What's new" in the profile menu
- **THEN** the dialog opens with A and no "Don't show again" checkbox

#### Scenario: No enabled patch note, no entry

- **WHEN** no patch note is enabled
- **THEN** the profile menu offers no "What's new" entry

#### Scenario: Unavailable browser storage degrades safely

- **WHEN** the browser's storage cannot be read or written
- **THEN** the dialog opens and closes normally, and may open again at the next load

### Requirement: Recording a patch-note dismissal

Any authenticated user SHALL be able to record a dismissal of a patch note for
themselves only. Recording a dismissal SHALL be idempotent. Enabling a
disabled patch note SHALL delete every user's dismissal of it, atomically with
the enable. A dismissal
request for an identifier that is not an existing patch note SHALL be refused
as not found. A user's dismissals SHALL be removed when the patch note is
deleted and when the user is deleted.

#### Scenario: Repeated dismissal is accepted

- **WHEN** a user records a dismissal for a patch note they already dismissed
- **THEN** the request succeeds and a single dismissal remains stored

#### Scenario: Dismissing a banner is refused

- **WHEN** a user records a dismissal for the identifier of a banner
- **THEN** the request is refused as not found and nothing is stored

#### Scenario: Re-enabling clears every user's Don't show again

- **GIVEN** users dismissed patch note A, a user dismissed patch note B, and A is disabled
- **WHEN** an administrator enables A
- **THEN** no dismissal for A remains stored and A's dismissal count is 0
- **AND** the dismissal for B is kept

#### Scenario: Deleting the patch note removes its dismissals

- **GIVEN** users dismissed patch note A
- **WHEN** an administrator deletes A
- **THEN** no dismissal for A remains stored

### Requirement: Patch-note preview matches the user dialog

The administration page SHALL let an administrator open, for any patch note in
the list and for the content being edited, the same dialog users see, with the
same layout, rendering and controls. A preview SHALL NOT record any dismissal
and SHALL NOT change whether the patch note is shown to the administrator at
load.

The patch-note editor SHALL also show an inline rendered preview of the body
being edited, updated as the administrator types.

#### Scenario: Preview from the list

- **WHEN** an administrator activates Preview on a patch note in the list
- **THEN** the dialog that users see at load opens with that patch note's body in the administrator's locale

#### Scenario: Preview from the editor uses unsaved content

- **GIVEN** an administrator has typed a body that is not saved yet
- **WHEN** the administrator opens the user-dialog preview from the editor
- **THEN** the dialog shows the typed body, rendered exactly as users would see it

#### Scenario: Preview records nothing

- **WHEN** an administrator ticks "Don't show again" in a preview and closes it
- **THEN** no dismissal is stored on the server

### Requirement: Patch notes in the admin list

Patch notes SHALL appear in the same administration list as banners, visually
distinct from them in a neutral style. Each patch-note row SHALL show the
patch note's title in the administrator's locale, its type, how many users
dismissed its current content version, the same activation control as
banners, and Preview, Edit and Delete actions. Enabling a patch note while
another one is enabled, from the list or from the editor, SHALL first ask the
administrator to confirm, naming the patch note that will be disabled.

#### Scenario: Patch-note row content

- **GIVEN** a patch note titled `What's new in 3.4` in `en`, dismissed by 12 users
- **WHEN** an administrator whose locale is `en` opens the announcements page
- **THEN** its row shows `What's new in 3.4`, a patch-note type label, that 12 users chose to hide it, an activation switch, and Preview, Edit and Delete actions

#### Scenario: Enabling names the patch note it replaces

- **GIVEN** patch note A titled `Version 3.3` is enabled
- **WHEN** an administrator enables patch note B
- **THEN** a confirmation names `Version 3.3` as the patch note that will be disabled, and nothing changes until it is confirmed

### Requirement: Patch-note editor safeguards

The patch-note editor SHALL NOT discard unsaved changes silently: closing it
with Escape, a click outside or Cancel while title or body differ from what
was saved SHALL ask the administrator to confirm. On a patch note that is not
enabled, the editor SHALL offer to save and enable it in one action, and a
plain save SHALL tell the administrator that the patch note is not active.

#### Scenario: Closing with unsaved changes asks first

- **GIVEN** an administrator changed a patch note's title in the editor
- **WHEN** they press Escape
- **THEN** a confirmation asks whether to discard the changes, and the editor keeps them if they decline

#### Scenario: Save and activate

- **GIVEN** a disabled patch note open in the editor and no other enabled patch note
- **WHEN** the administrator picks "Save and activate"
- **THEN** the patch note is saved and enabled

### Requirement: Announcement activation history

The system SHALL record an event every time any announcement, of either type,
goes from disabled to enabled or from enabled to disabled. This includes an
announcement created already enabled, a patch note disabled because another
was enabled, and an enabled announcement that is deleted. A request that does
not change the enabled state SHALL NOT record an event.

Each event SHALL carry the announcement's identifier, its type, a snapshot of
its title per locale taken at the time of the
event, the action (`activated` or `deactivated`), the time, and the identifier
of the acting user. Events SHALL be written in the same transaction as the
state change they describe, SHALL never be updated or deleted by the
application, and SHALL remain readable after the announcement is deleted.

Platform administrators SHALL be able to read the 100 most recent events,
newest first, and the administration page SHALL show them with the acting
user's display name. The page SHALL let them narrow the table to activations
or to deactivations, and SHALL remember that choice in the browser.

#### Scenario: Showing only activations

- **GIVEN** the history holds activations and deactivations
- **WHEN** an administrator picks the "Activations" filter and later reopens the history
- **THEN** only `activated` events are listed, both times

#### Scenario: Activation and deactivation are recorded with the author

- **WHEN** administrator Alice enables banner X and later administrator Bob disables it
- **THEN** the history lists, newest first, a `deactivated` event for X by Bob and an `activated` event for X by Alice, each with its time and X's title

#### Scenario: Automatic deactivation is recorded

- **GIVEN** patch note A is enabled
- **WHEN** administrator Alice enables patch note B
- **THEN** the history records a `deactivated` event for A and an `activated` event for B, both by Alice

#### Scenario: History survives deletion

- **GIVEN** banner X was enabled then disabled
- **WHEN** an administrator deletes X
- **THEN** the history still lists both events for X with its title and type

#### Scenario: Deleting an enabled announcement is recorded

- **WHEN** an administrator deletes an enabled patch note
- **THEN** the history records a `deactivated` event for it by that administrator

#### Scenario: No-op toggle records nothing

- **WHEN** an administrator enables an announcement that is already enabled
- **THEN** no event is recorded

#### Scenario: Concurrent toggles record one event

- **WHEN** two administrators disable the same enabled announcement at the same moment
- **THEN** exactly one `deactivated` event is recorded

#### Scenario: A failed change records nothing

- **WHEN** an activation fails and its transaction is rolled back
- **THEN** no event for it is stored

### Requirement: Authorization for patch notes and history

Creating, editing, deleting, enabling and disabling patch notes, and reading
the activation history, SHALL require the same platform-administration
authority as banners. Reading the active patch note with the caller's
dismissal state and recording the caller's own dismissal SHALL require
authentication only. A patch note's dismissal count SHALL only be returned to
platform administrators. No
request SHALL record or read another user's dismissal.

#### Scenario: Non-administrator cannot read the history

- **WHEN** an authenticated user without platform-administration authority requests the activation history
- **THEN** the request is refused and no event is returned

#### Scenario: Non-administrator cannot manage patch notes

- **WHEN** an authenticated user without platform-administration authority tries to create, edit, delete, enable or disable a patch note
- **THEN** the request is refused and nothing changes

#### Scenario: Unauthenticated client cannot read or dismiss

- **WHEN** an unauthenticated client requests the active patch note or records a dismissal
- **THEN** the request is refused

#### Scenario: A dismissal only applies to the caller

- **WHEN** user Alice records a dismissal of patch note A
- **THEN** user Bob still receives patch note A at his next load
