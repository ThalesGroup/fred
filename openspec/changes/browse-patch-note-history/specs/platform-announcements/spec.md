## ADDED Requirements

### Requirement: Patch-note working area

The patch notes an administrator manages SHALL be a working area that users
never read directly. Creating, editing, reordering, deleting a patch note or
changing its toggle SHALL NOT change what any user reads and SHALL NOT make
the dialog open for any user; only announcing or withdrawing does.

Each patch note SHALL carry a toggle, independent of every other patch note,
that decides whether it is included in the next announcement. Any number of
patch notes SHALL be included at once. A patch note SHALL be created with the
toggle off. Editing a patch note's title or body SHALL NOT change its toggle
and SHALL be possible whatever its age. Changing a toggle SHALL NOT change any
banner or any other patch note.

#### Scenario: A new patch note is not included

- **WHEN** an administrator creates a patch note
- **THEN** it is listed with its toggle off

#### Scenario: Several patch notes included at once

- **GIVEN** patch note A is included
- **WHEN** an administrator turns on the toggle of patch note B
- **THEN** A and B are both included, with no confirmation and no change to A

#### Scenario: Toggling reaches no user

- **GIVEN** an announced package holding A and B
- **WHEN** an administrator turns off A's toggle and turns on C's
- **THEN** users still read A and B, and no dialog opens on its own

#### Scenario: Editing reaches no user

- **GIVEN** an announced package holding patch note A
- **WHEN** an administrator corrects A's body and saves
- **THEN** the change is stored in the working area and users still read the announced text

#### Scenario: Deleting reaches no user

- **GIVEN** an announced package holding patch note A
- **WHEN** an administrator deletes A
- **THEN** users still read A in the package

### Requirement: Ordering patch notes

Patch notes SHALL have an order chosen by the administrator. The Patch notes
tab SHALL list them in that order and SHALL let the administrator change it by
drag and drop and, equivalently, with the keyboard alone. The order SHALL be
stored on the server and SHALL be the same for every administrator. It SHALL
NOT depend on any date. A newly created patch note SHALL be placed at the top
of the list.

An announcement SHALL take the included patch notes in that order. Reordering
SHALL NOT change any toggle nor the order of a package already announced. A
reorder request that does not name exactly the existing patch notes SHALL be
refused and SHALL change nothing.

#### Scenario: Reordering by drag and drop

- **GIVEN** the list holds A, B, C in that order
- **WHEN** an administrator drags C above A
- **THEN** the list holds C, A, B, and still does after the page is reloaded

#### Scenario: Reordering with the keyboard

- **GIVEN** the list holds A, B, C in that order
- **WHEN** an administrator moves B up one place using the keyboard only
- **THEN** the list holds B, A, C and the new place is announced to assistive technology

#### Scenario: A new patch note goes to the top

- **GIVEN** the list holds A, B
- **WHEN** an administrator creates patch note C
- **THEN** the list holds C, A, B

#### Scenario: A stale reorder is refused

- **GIVEN** an administrator's page lists A, B while another administrator has just deleted B
- **WHEN** the first administrator submits the order B, A
- **THEN** the request is refused and the stored order is unchanged

#### Scenario: Reordering after an announcement reaches no user

- **GIVEN** an announced package holding A then B
- **WHEN** an administrator moves B above A
- **THEN** users still read A at position 1 and B at position 2

### Requirement: Announcing a package of patch notes

The Patch notes tab SHALL offer an action, labelled "Announce the update"
("Annoncer la mise à jour" in French), that announces the included patch
notes. The action SHALL show the included patch notes in their order and ask
the administrator to confirm before anything happens.

Once confirmed, the system SHALL freeze the included patch notes, in list
order, with their title and body in every language they hold, as a package
recorded with its time and the acting administrator. That package, and only
it, SHALL be what users read until the next announcement or a withdrawal.
Every announcement SHALL create a new package and SHALL make the dialog open
for every user at their next application load, once per user for that
announcement, including users who had seen the previous one. There SHALL be no
way to change a package once announced.

The action SHALL be unavailable while no patch note is included, and a request
to announce in that state SHALL be refused. Next to the action, the page SHALL
show the date and time of the announcement in effect and the display name of
the administrator who made it, or nothing when none is in effect. Each
announcement SHALL emit an audit record.

#### Scenario: Announcing asks for confirmation

- **GIVEN** patch notes A and B are included, in that order
- **WHEN** an administrator activates the announce action
- **THEN** a confirmation lists A then B, and nothing is recorded until it is confirmed

#### Scenario: Cancelling the confirmation announces nothing

- **WHEN** an administrator activates the announce action and cancels the confirmation
- **THEN** no package is recorded and no user gets the dialog

#### Scenario: The package is what users read

- **GIVEN** the list holds A (included), B (not included), C (included) in that order
- **WHEN** an administrator confirms an announcement
- **THEN** users read A at position 1 and C at position 2, out of 2

#### Scenario: Every user gets the dialog once

- **GIVEN** an administrator confirmed an announcement
- **WHEN** users Alice and Bob each load the application afterwards
- **THEN** the dialog opens for each of them
- **AND** it does not open on its own again for a user who closed it, until another announcement is made

#### Scenario: Correcting a typo means announcing again

- **GIVEN** an announced package holding A, seen by Alice
- **WHEN** an administrator corrects A, confirms a new announcement, and Alice loads the application
- **THEN** Alice reads the corrected text and the dialog opens for her once more

#### Scenario: Last use is shown next to the action

- **GIVEN** administrator Alice announced on 12 October at 10:30
- **WHEN** an administrator opens the Patch notes tab
- **THEN** the page shows, next to the action, that date and time and Alice's display name

#### Scenario: Nothing included, no announcement

- **GIVEN** no patch note is included
- **WHEN** an administrator opens the Patch notes tab
- **THEN** the announce action is disabled
- **AND** a request to announce sent anyway is refused and records nothing

### Requirement: Withdrawing the current announcement

The Patch notes tab SHALL offer an action, "Withdraw the current
announcement", available while an announcement is in effect. It SHALL tell the
administrator what will happen and ask for confirmation. Once confirmed, no
package SHALL be in effect: users SHALL read no patch note, the dialog SHALL
NOT open for anyone, and the page SHALL show no last announcement, until the
next announcement. Withdrawing SHALL NOT change the working area. A request to
withdraw while no announcement is in effect SHALL be refused. Each withdrawal
SHALL emit an audit record.

#### Scenario: Withdrawing empties what users read

- **GIVEN** an announced package not yet seen by Bob
- **WHEN** an administrator confirms the withdrawal and Bob loads the application
- **THEN** no dialog opens for Bob and "What's new" is not offered

#### Scenario: Announcing after a withdrawal

- **GIVEN** an announcement was withdrawn
- **WHEN** an administrator confirms a new announcement
- **THEN** every user gets the dialog once, with the new package

#### Scenario: Nothing to withdraw

- **WHEN** a withdrawal is requested while no announcement is in effect
- **THEN** the request is refused and nothing changes

### Requirement: Browsing the announced package in the dialog

The system SHALL deliver to any authenticated user the patch notes of the
package in effect, in the package's order, together with whether that
announcement is pending for that user. When no package is in effect it SHALL
deliver no patch note.

The patch-note dialog SHALL be the same component when it opens at application
load and when it is opened from "What's new". It SHALL open on position 1.
When the package holds more than one patch note, the left of its action bar
SHALL hold a navigation made of an icon button, a position indicator such as
`1 / 4`, and a second icon button, moving through the positions and back. The
left button SHALL move towards position 1 and the right button towards the
following positions. The button that cannot move further SHALL be disabled.
Moving SHALL replace the dialog's title and body with the patch note at the
new position, shown from its top. With a single patch note the dialog SHALL
show no navigation. The dialog SHALL NOT offer any "Don't show again" control.

A patch note with no text at all for the viewer SHALL be left out of that
viewer's dialog and of the position count.

While a package is in effect, the user's profile menu SHALL offer a "What's
new" entry opening that dialog, whether or not the announcement is pending for
the user. The entry SHALL NOT appear when no package is in effect.

#### Scenario: The dialog opens on position 1

- **GIVEN** a package of four patch notes
- **WHEN** a user picks "What's new" in the profile menu
- **THEN** the dialog shows the first one and the indicator reads `1 / 4`
- **AND** the button towards position 1 is disabled

#### Scenario: Navigating to the next patch note

- **GIVEN** the dialog is open at `1 / 4`
- **WHEN** the user activates the button towards the following positions
- **THEN** the dialog shows the second patch note, from its top, and the indicator reads `2 / 4`

#### Scenario: The last position ends the navigation

- **GIVEN** the dialog is open at `4 / 4`
- **THEN** the button towards the following positions is disabled

#### Scenario: A single patch note has no navigation

- **GIVEN** a package of exactly one patch note
- **WHEN** the dialog opens
- **THEN** it shows that patch note with a Close button and no navigation

#### Scenario: No package in effect, no entry

- **WHEN** no announcement was ever made, or the last one was withdrawn
- **THEN** the profile menu offers no "What's new" entry

### Requirement: Recording that an announcement was seen

Any authenticated user SHALL be able to record, for themselves only, that they
have seen an announcement. The record SHALL be kept on the server, one per
user, so it holds on every browser and device. Recording SHALL be idempotent.
A request naming something that is not an announced package SHALL be refused
as not found. Recording an announcement older than the most recent one SHALL
NOT mark the most recent one as seen. A user's record SHALL be removed when
the user is deleted. Creating, editing, deleting, reordering or toggling patch
notes SHALL NOT change any user's record.

#### Scenario: Repeated record is accepted

- **WHEN** a user records as seen an announcement they already recorded
- **THEN** the request succeeds and nothing else changes

#### Scenario: An unknown announcement is refused

- **WHEN** a user records as seen an identifier that is not an announced package
- **THEN** the request is refused as not found and nothing is stored

#### Scenario: A newer announcement made meanwhile stays pending

- **GIVEN** a user's dialog opened for announcement 1, and an administrator then made announcement 2
- **WHEN** the user closes the dialog
- **THEN** announcement 2 is still pending for that user at their next load

#### Scenario: A record only applies to the caller

- **WHEN** user Alice records the latest announcement as seen
- **THEN** it is still pending for user Bob

### Requirement: Announcement administration tabs

The announcements administration page SHALL offer three tabs, in this order:
"Banners", "Patch notes", and the activation history. The Banners tab SHALL
list banners only and SHALL create banners. The Patch notes tab SHALL list
patch notes only and SHALL create patch notes. The page SHALL open on the
Banners tab. Each list SHALL show its own empty state when it holds nothing,
whatever the other holds.

#### Scenario: Banners tab holds no patch note

- **GIVEN** two banners and three patch notes
- **WHEN** an administrator opens the announcements page
- **THEN** the Banners tab is shown and lists the two banners only

#### Scenario: Patch notes tab holds no banner

- **GIVEN** two banners and three patch notes
- **WHEN** the administrator opens the Patch notes tab
- **THEN** it lists the three patch notes only

#### Scenario: Creating from a tab creates that kind

- **WHEN** the administrator uses the create action of the Patch notes tab
- **THEN** the patch-note editor opens directly, with no choice of kind

#### Scenario: An empty tab beside a filled one

- **GIVEN** two banners and no patch note
- **WHEN** the administrator opens the Patch notes tab
- **THEN** it shows an empty state, and the Banners tab still lists the two banners

### Requirement: Authorization for patch notes, announcing and history

Creating, editing, deleting, reordering and toggling patch notes, announcing
them, withdrawing the current announcement, reading the announcement in effect
and its author, reading the exposure history and reading the package of any
history line SHALL require the same platform-administration authority as
banners. Reading the package in effect with whether it is pending for the
caller, and recording that the caller has seen an announcement, SHALL require
authentication only. The working area SHALL only be returned to platform
administrators. No request SHALL record or read what another user has seen.

#### Scenario: Non-administrator cannot read the history

- **WHEN** an authenticated user without platform-administration authority requests the exposure history or the package of one of its lines
- **THEN** the request is refused and nothing is returned

#### Scenario: Non-administrator cannot manage patch notes

- **WHEN** an authenticated user without platform-administration authority tries to create, edit, delete, reorder or toggle a patch note
- **THEN** the request is refused and nothing changes

#### Scenario: Non-administrator cannot announce or withdraw

- **WHEN** an authenticated user without platform-administration authority tries to announce the patch notes or withdraw the current announcement
- **THEN** the request is refused and nothing changes

#### Scenario: Unauthenticated client cannot read or record

- **WHEN** an unauthenticated client requests the package in effect or records an announcement as seen
- **THEN** the request is refused

#### Scenario: The working area is not delivered to users

- **GIVEN** a package holding A, and a patch note B created since
- **WHEN** an authenticated user's client requests the package in effect
- **THEN** only A is returned

### Requirement: Patch-note dialog after an announcement

When an authenticated user loads the application and an announcement is
pending for that user, the client SHALL open the patch-note dialog on position
1: a large dialog showing the note's title and its body rendered as markdown
in the viewer's locale, with a Close button and the navigation. The dialog
SHALL open with focus on the dialog itself, at the top of the note, and its
links SHALL open in a new tab. The dialog SHALL NOT open on pre-authentication
screens.

An announcement SHALL be pending for a user when its package is in effect and
that user has not recorded it as seen. The dialog SHALL NOT open on its own
for any other reason: creating, editing, reordering, deleting or toggling a
patch note SHALL NOT open it, and a withdrawn announcement SHALL NOT be
pending for anyone.

Closing the dialog, whether through Close, Escape or a click outside, SHALL
record the announcement that opened it as seen by that user, whichever
position the user navigated to.

When recording fails, the dialog SHALL still close and SHALL NOT reopen during
the same page view; the only consequence SHALL be that it may open again at a
later load.

#### Scenario: Dialog opens at load after an announcement

- **GIVEN** a package of two patch notes pending for the user
- **WHEN** the user signs in and the application loads
- **THEN** the patch-note dialog opens on position 1, with its body rendered as markdown, the navigation, a Close button and no "Don't show again" control

#### Scenario: No announcement, no dialog

- **GIVEN** included patch notes and no announcement ever made
- **WHEN** the user loads the application
- **THEN** no patch-note dialog opens

#### Scenario: Seen once per announcement

- **GIVEN** the patch-note dialog opened at load
- **WHEN** the user closes it with Close, Escape or a click outside
- **THEN** that announcement is recorded as seen by that user on the server
- **AND** the dialog does not open on its own at later loads, including after a new sign-in and from another browser or device

#### Scenario: Working on patch notes does not open the dialog

- **GIVEN** a user who has seen the announcement in effect
- **WHEN** an administrator creates, edits, reorders and toggles patch notes, and the user loads the application
- **THEN** no patch-note dialog opens on its own

#### Scenario: A user who navigated still records the announcement

- **GIVEN** the dialog opened at load and the user navigated to position 3
- **WHEN** the user closes the dialog
- **THEN** the announcement is recorded as seen by that user

#### Scenario: The dialog opens at the top of the note

- **GIVEN** a patch note whose body contains a link and a code block below the first screen
- **WHEN** the dialog opens
- **THEN** focus is on the dialog itself, the note is shown from its top, and the link opens in a new tab

#### Scenario: Recording fails

- **WHEN** the user closes the dialog and the record cannot be stored
- **THEN** the dialog closes and stays closed for this page view, and may open again at a later load

### Requirement: Patch notes in the Patch notes tab

Patch notes SHALL be listed in the Patch notes tab of the administration page,
in a neutral style, in the administrator's order. Each row SHALL show, at its
left, a handle to move it, the patch note's title in the administrator's
locale, its toggle, and Preview, Edit and Delete actions. Changing a toggle
SHALL take effect without confirmation.

#### Scenario: Patch-note row content

- **GIVEN** an included patch note titled `What's new in 3.4` in `en`
- **WHEN** an administrator whose locale is `en` opens the Patch notes tab
- **THEN** its row shows a move control, `What's new in 3.4`, a toggle that is on, and Preview, Edit and Delete actions

#### Scenario: Toggling from the list

- **GIVEN** patch note A is included and patch note B is not
- **WHEN** an administrator turns on B's toggle
- **THEN** B is included at once, A stays included, and no confirmation is shown

### Requirement: Exposure history

The system SHALL keep one history line per exposure: each time a banner goes
from disabled to enabled (including a banner created enabled), and each time
patch notes are announced. A line SHALL carry its type, a title, the time the
exposure started, the time it ended (empty while it lasts) and the identifier
of the administrator who started it. Toggling a patch note SHALL NOT write any
line, and no line SHALL carry an action.

A banner's line SHALL carry the banner's title per locale and its severity as
they were when it was enabled, and SHALL end when the banner is disabled or
deleted. A request that does not change a banner's enabled state SHALL NOT
write or end a line.

A patch-note line SHALL carry the title of the first patch note of its package
and the number of patch notes the package holds, SHALL keep the package, and
SHALL end when the next announcement replaces it or when it is withdrawn.

Lines SHALL be written in the same transaction as the change they describe and
SHALL remain readable after the banner or the patch notes are deleted.

Platform administrators SHALL be able to read the 100 most recent lines,
newest first, and the administration page SHALL show them with the type, the
title, the activation, the deactivation and the author's display name. The
page SHALL let them narrow the table to one type, banner or patch note, and
SHALL remember that choice in the browser. For a patch-note line that keeps a
package, the page SHALL let the administrator open that package in the dialog
as users saw it; a line without a package SHALL be shown without that action.

#### Scenario: A banner exposure is one line

- **WHEN** administrator Alice enables banner X and later administrator Bob disables it
- **THEN** the history holds one line for X, with its activation time, its deactivation time, X's title and Alice as the author

#### Scenario: A banner still on air has no deactivation

- **WHEN** an administrator enables banner X
- **THEN** X's line shows an activation time and no deactivation

#### Scenario: Re-enabling a banner starts a new line

- **GIVEN** banner X was enabled then disabled
- **WHEN** an administrator enables X again
- **THEN** the history holds two lines for X, the newer one without deactivation

#### Scenario: An announcement is one line

- **GIVEN** the included patch notes are `Version 3.4`, then two others
- **WHEN** administrator Alice confirms an announcement
- **THEN** the history holds a patch-note line titled `Version 3.4` with two others, by Alice, without deactivation

#### Scenario: The next announcement ends the previous line

- **GIVEN** an announcement in effect
- **WHEN** an administrator confirms a new announcement
- **THEN** the previous line's deactivation is the time of the new one

#### Scenario: Withdrawing ends the line

- **WHEN** an administrator withdraws the current announcement
- **THEN** its line's deactivation is the time of the withdrawal

#### Scenario: Opening a package from the history

- **GIVEN** a patch-note line whose patch notes were since edited and deleted
- **WHEN** an administrator opens it from the history
- **THEN** the dialog shows the patch notes as they were announced

#### Scenario: Toggling a patch note writes nothing

- **WHEN** an administrator turns a patch note's toggle on, then off
- **THEN** the history is unchanged

#### Scenario: Filtering by type

- **GIVEN** the history holds banner and patch-note lines
- **WHEN** an administrator picks the "Patch notes" filter and later reopens the history
- **THEN** only patch-note lines are listed, both times

#### Scenario: History survives deletion

- **GIVEN** banner X was enabled then disabled
- **WHEN** an administrator deletes X
- **THEN** the history still lists X's line with its title and type

#### Scenario: Deleting an enabled banner ends its line

- **WHEN** an administrator deletes an enabled banner
- **THEN** its line's deactivation is the time of the deletion

#### Scenario: No-op toggle writes nothing

- **WHEN** an administrator enables a banner that is already enabled
- **THEN** no line is written

#### Scenario: Concurrent toggles write one change

- **WHEN** two administrators disable the same enabled banner at the same moment
- **THEN** its line is ended once

#### Scenario: A failed change writes nothing

- **WHEN** an activation fails and its transaction is rolled back
- **THEN** no line for it is stored

### Requirement: Existing patch notes and history after upgrade

On upgrade, the patch note that was enabled SHALL become the first package, in
effect and pending for no user, so "What's new" is not empty and no dialog
opens until an administrator announces. Its toggle SHALL stay on. When no
patch note was enabled, no package SHALL be in effect.

Earlier history SHALL be converted to lines: each banner activation with the
deactivation that followed it becomes one line. Earlier patch-note activations
SHALL become patch-note lines that are ended and keep no package, since the
content of the time was not kept; reading the history SHALL tolerate them.

#### Scenario: The enabled patch note is readable after upgrade

- **GIVEN** patch note A was enabled before the upgrade
- **WHEN** a user loads the application after the upgrade
- **THEN** no dialog opens on its own, and "What's new" shows A

#### Scenario: Earlier banner events become lines

- **GIVEN** banner X was activated by Alice, then deactivated, before the upgrade
- **WHEN** an administrator opens the history after the upgrade
- **THEN** it shows one line for X with both times and Alice as the author

#### Scenario: An earlier patch-note line has no package

- **GIVEN** a patch note was activated and replaced before the upgrade
- **WHEN** an administrator opens the history after the upgrade
- **THEN** its line shows both times and offers no package to open

## MODIFIED Requirements

### Requirement: Patch-note preview matches the user dialog

The administration page SHALL let an administrator open, for any patch note in
the list and for the content being edited, the dialog users see, with the same
layout and rendering, showing that single patch note without navigation. A
preview SHALL NOT record anything as seen and SHALL NOT change whether the
dialog opens for the administrator at load.

The patch-note editor SHALL also show an inline rendered preview of the body
being edited, updated as the administrator types.

#### Scenario: Preview from the list

- **WHEN** an administrator activates Preview on a patch note in the list
- **THEN** the dialog that users see opens with that patch note's body in the administrator's locale

#### Scenario: Preview from the editor uses unsaved content

- **GIVEN** an administrator has typed a body that is not saved yet
- **WHEN** the administrator opens the user-dialog preview from the editor
- **THEN** the dialog shows the typed body, rendered exactly as users would see it

#### Scenario: Preview records nothing

- **WHEN** an administrator closes a preview
- **THEN** nothing is recorded as seen on the server

### Requirement: Patch-note editor safeguards

The patch-note editor SHALL NOT discard unsaved changes silently: closing it
with Escape, a click outside or Cancel while title or body differ from what
was saved SHALL ask the administrator to confirm. On a patch note that is not
included in the next announcement, the editor SHALL offer to save it and
include it in one action, and a plain save SHALL tell the administrator that
it is not included. Neither save SHALL announce anything to users.

#### Scenario: Closing with unsaved changes asks first

- **GIVEN** an administrator changed a patch note's title in the editor
- **WHEN** they press Escape
- **THEN** a confirmation asks whether to discard the changes, and the editor keeps them if they decline

#### Scenario: Plain save keeps a new patch note out of the next announcement

- **WHEN** an administrator saves a new patch note with the plain save
- **THEN** it is stored with its toggle off, and the administrator is told that it is not included in the next announcement

#### Scenario: Save and activate

- **GIVEN** a patch note that is not included, open in the editor
- **WHEN** the administrator picks the action that saves and includes it
- **THEN** the patch note is saved and included, with no confirmation, no change to other patch notes and nothing announced

## REMOVED Requirements

### Requirement: Authorization for patch notes and history

**Reason**: Replaced by "Authorization for patch notes, announcing and
history": the dismissal and dismissal-count clauses and their two scenarios no
longer describe anything, and a modified requirement cannot drop scenarios.

**Migration**: None; the same authority is required for the same surfaces.

### Requirement: One active patch note at a time

**Reason**: A patch note's toggle now means "included in the next
announcement", and any number can be included. See "Patch-note working area".

**Migration**: The single patch note enabled before the upgrade becomes the
first announced package (see "Existing patch notes and history after
upgrade"). Clients no longer receive a `409` on concurrent activation.

### Requirement: Reopening the active patch note

**Reason**: Replaced by "Browsing the announced package in the dialog":
"What's new" opens the last announced package instead of one active patch
note.

**Migration**: None for users; the entry keeps its place and label.

### Requirement: Recording a patch-note dismissal

**Reason**: There is no "Don't show again" choice any more, and what a user
has seen is tracked per announcement, not per patch note. Replaced by
"Recording that an announcement was seen".

**Migration**: Existing dismissals are discarded. The package created by the
upgrade is pending for nobody, so no user gets a dialog until an administrator
announces.

### Requirement: Patch-note dialog at application load

**Reason**: Replaced by "Patch-note dialog after an announcement": the dialog opens for a pending announcement, not for an enabled patch note, and has no checkbox. A modified requirement
cannot drop scenarios, so it is replaced under a new name.

**Migration**: None beyond what the replacing requirement states.

### Requirement: Patch notes in the admin list

**Reason**: Replaced by "Patch notes in the Patch notes tab": the row gains a move handle and loses the confirmation naming a replaced patch note. A modified requirement
cannot drop scenarios, so it is replaced under a new name.

**Migration**: None beyond what the replacing requirement states.

### Requirement: Announcement activation history

**Reason**: Replaced by "Exposure history": the history holds one line per
exposure (a banner activation, a patch-note announcement) instead of one line
per event. A modified requirement cannot drop scenarios, so it is replaced
under a new name.

**Migration**: None beyond what the replacing requirement states.
