## ADDED Requirements

### Requirement: Patch-note visibility

Each patch note SHALL carry a visibility toggle, independent of every other
patch note; any number of patch notes SHALL be visible at once. The toggle
SHALL only decide whether the patch note appears in the users' patch-note
dialog and its history: a visible patch note appears there, a patch note that
is not visible appears nowhere on the user side.

A patch note SHALL be created with the toggle off. Editing a patch note's
title or body SHALL NOT change its toggle, and SHALL be possible whatever the
patch note's age and whether or not it is visible. Changing a toggle SHALL NOT
change any banner or any other patch note, and SHALL NOT make the dialog open
on its own for any user.

#### Scenario: A new patch note is not visible

- **WHEN** an administrator creates a patch note
- **THEN** it is listed with its toggle off and users cannot read it

#### Scenario: Several patch notes visible at once

- **GIVEN** patch note A is visible
- **WHEN** an administrator turns on the toggle of patch note B
- **THEN** A and B are both visible, with no confirmation and no change to A

#### Scenario: Turning the toggle off removes it from what users read

- **GIVEN** patch notes A and B are visible
- **WHEN** an administrator turns off A's toggle
- **THEN** users' dialog and history hold B only

#### Scenario: An old patch note stays editable

- **GIVEN** a visible patch note that is not at the top of the list
- **WHEN** an administrator changes its body and saves
- **THEN** the change is stored, the patch note stays visible, and users read the new text in the history

#### Scenario: Making a patch note visible does not open the dialog

- **GIVEN** a user for whom no announcement is pending
- **WHEN** an administrator makes a patch note visible and the user loads the application
- **THEN** no patch-note dialog opens on its own, and the patch note is readable from "What's new"

### Requirement: Ordering patch notes

Patch notes SHALL have an order chosen by the administrator. The Patch notes
tab SHALL list them in that order and SHALL let the administrator change it by
drag and drop and, equivalently, with the keyboard alone. The order SHALL be
stored on the server and SHALL be the same for every administrator. It SHALL
NOT depend on any date. A newly created patch note SHALL be placed at the top
of the list.

The users' dialog SHALL present the visible patch notes in that same order:
position 1 SHALL be the visible patch note nearest the top of the list.
Reordering SHALL NOT change any toggle and SHALL NOT make the dialog open on
its own for any user. A reorder request that does not name exactly the
existing patch notes SHALL be refused and SHALL change nothing.

#### Scenario: Reordering by drag and drop

- **GIVEN** the list holds A, B, C in that order
- **WHEN** an administrator drags C above A
- **THEN** the list holds C, A, B, and still does after the page is reloaded

#### Scenario: Reordering with the keyboard

- **GIVEN** the list holds A, B, C in that order
- **WHEN** an administrator moves B up one place using the keyboard only
- **THEN** the list holds B, A, C and the new place is announced to assistive technology

#### Scenario: The dialog follows the list order

- **GIVEN** the list holds A (visible), B (not visible), C (visible) in that order
- **WHEN** a user opens the patch-note dialog
- **THEN** A is at position 1 and C at position 2, out of 2

#### Scenario: A new patch note goes to the top

- **GIVEN** the list holds A, B
- **WHEN** an administrator creates patch note C
- **THEN** the list holds C, A, B

#### Scenario: A stale reorder is refused

- **GIVEN** an administrator's page lists A, B while another administrator has just deleted B
- **WHEN** the first administrator submits the order B, A
- **THEN** the request is refused and the stored order is unchanged

#### Scenario: Reordering does not open the dialog

- **GIVEN** a user for whom no announcement is pending
- **WHEN** an administrator reorders the patch notes and the user loads the application
- **THEN** no patch-note dialog opens on its own

### Requirement: Announcing patch notes to users

The Patch notes tab SHALL offer an action, labelled "Announce the update"
("Annoncer la mise à jour" in French), that announces the patch notes to
users. The action SHALL ask the administrator to confirm before anything
happens. Once confirmed, the system SHALL record an announcement with its time
and the acting administrator, and from then on every user SHALL get the
patch-note dialog at their next application load, once per user for that
announcement.

The action SHALL be unavailable while no patch note is visible, and a request
to announce in that state SHALL be refused. Next to the action, the page SHALL
show the date and time of the most recent announcement and the display name of
the administrator who made it, or nothing when none was ever made. Each
announcement SHALL emit an audit record and SHALL appear in the activation
history.

Announcing SHALL be the only thing that makes the dialog open on its own.

When the last visible patch note stops being visible, because its toggle is
turned off or because it is deleted, the system SHALL cancel the most recent
announcement: users who had not seen it SHALL NOT get the dialog for it, even
once a patch note is visible again, and nothing SHALL stay pending. A new
announcement SHALL be needed for the dialog to open on its own again. A
cancelled announcement SHALL no longer be shown next to the action, and the
cancellation SHALL appear in the activation history.

#### Scenario: Announcing asks for confirmation

- **GIVEN** at least one visible patch note
- **WHEN** an administrator activates the announce action
- **THEN** a confirmation is shown, and nothing is recorded until it is confirmed

#### Scenario: Cancelling the confirmation announces nothing

- **WHEN** an administrator activates the announce action and cancels the confirmation
- **THEN** no announcement is recorded and no user gets the dialog

#### Scenario: Every user gets the dialog once

- **GIVEN** an administrator confirmed an announcement
- **WHEN** users Alice and Bob each load the application afterwards
- **THEN** the dialog opens for each of them
- **AND** it does not open on its own again for a user who closed it, until another announcement is made

#### Scenario: A second announcement shows the dialog again

- **GIVEN** Alice closed the dialog opened by a first announcement
- **WHEN** an administrator confirms a second announcement and Alice loads the application
- **THEN** the dialog opens for Alice once more

#### Scenario: Last use is shown next to the action

- **GIVEN** administrator Alice announced on 12 October at 10:30
- **WHEN** an administrator opens the Patch notes tab
- **THEN** the page shows, next to the action, that date and time and Alice's display name

#### Scenario: No visible patch note, no announcement

- **GIVEN** no patch note is visible
- **WHEN** an administrator opens the Patch notes tab
- **THEN** the announce action is disabled
- **AND** a request to announce sent anyway is refused and records nothing

#### Scenario: Hiding the last visible patch note cancels the announcement

- **GIVEN** one visible patch note, an announcement seen by Alice and not yet by Bob
- **WHEN** an administrator turns off that patch note's toggle, then turns it on again, and Bob loads the application
- **THEN** no patch-note dialog opens for Bob
- **AND** the page shows no last announcement next to the action

#### Scenario: Deleting the last visible patch note cancels the announcement

- **GIVEN** one visible patch note and an announcement not yet seen by Bob
- **WHEN** an administrator deletes that patch note, makes another one visible, and Bob loads the application
- **THEN** no patch-note dialog opens for Bob

#### Scenario: Hiding one of several visible patch notes cancels nothing

- **GIVEN** two visible patch notes and an announcement not yet seen by Bob
- **WHEN** an administrator turns off one toggle and Bob loads the application
- **THEN** the dialog opens for Bob with the remaining patch note

#### Scenario: Announcing again after a cancellation

- **GIVEN** an announcement was cancelled and a patch note is visible again
- **WHEN** an administrator confirms a new announcement
- **THEN** every user gets the dialog once, including those who had seen the cancelled one

#### Scenario: The announcement is in the history

- **WHEN** administrator Alice confirms an announcement
- **THEN** the activation history lists it with its time and Alice as the author

### Requirement: Browsing patch-note history in the dialog

The system SHALL deliver to any authenticated user the visible patch notes in
the administrator's order, together with whether an announcement is pending
for that user.

The patch-note dialog SHALL be the same component when it opens at application
load and when it is opened from "What's new". It SHALL open on position 1.
When more than one patch note is visible, the left of its action bar SHALL
hold a navigation made of an icon button, a position indicator such as
`1 / 4`, and a second icon button, moving through the positions and back. The
left button SHALL move towards position 1 and the right button towards the
following, older positions. The
button that cannot move further SHALL be disabled. Moving SHALL replace the
dialog's title and body with the patch note at the new position, shown from
its top. With a single visible patch note the dialog SHALL show no navigation.
The dialog SHALL NOT offer any "Don't show again" control.

A patch note with no text in the viewer's locale nor in the fallback locale
SHALL be left out of that viewer's history and of the position count.

While at least one patch note is visible, the user's profile menu SHALL offer
a "What's new" entry opening that dialog, whether or not an announcement is
pending for the user. The entry SHALL NOT appear when no patch note is
visible.

#### Scenario: The dialog opens on position 1

- **GIVEN** four visible patch notes
- **WHEN** a user picks "What's new" in the profile menu
- **THEN** the dialog shows the one at the top of the administrator's list and the indicator reads `1 / 4`
- **AND** the button towards position 1 is disabled

#### Scenario: Navigating to the next patch note

- **GIVEN** the dialog is open at `1 / 4`
- **WHEN** the user activates the button towards the following positions
- **THEN** the dialog shows the second patch note, from its top, and the indicator reads `2 / 4`

#### Scenario: The last position ends the navigation

- **GIVEN** the dialog is open at `4 / 4`
- **THEN** the button towards the following positions is disabled

#### Scenario: A single patch note has no navigation

- **GIVEN** exactly one visible patch note
- **WHEN** the dialog opens
- **THEN** it shows that patch note with a Close button and no navigation

#### Scenario: Edited text is what users read

- **GIVEN** a visible patch note at position 2
- **WHEN** an administrator corrects its body and a user opens "What's new"
- **THEN** position 2 shows the corrected text

#### Scenario: No visible patch note, no entry

- **WHEN** no patch note is visible
- **THEN** the profile menu offers no "What's new" entry

### Requirement: Recording that an announcement was seen

Any authenticated user SHALL be able to record, for themselves only, that they
have seen an announcement. The record SHALL be kept on the server, one per
user, so it holds on every browser and device. Recording SHALL be idempotent.
A request naming something that is not an announcement SHALL be refused as not
found. Recording an announcement older than the most recent one SHALL NOT mark
the most recent one as seen. A user's record SHALL be removed when the user is
deleted. Creating, editing, deleting, reordering or toggling patch notes SHALL
NOT change any user's record.

#### Scenario: Repeated record is accepted

- **WHEN** a user records as seen an announcement they already recorded
- **THEN** the request succeeds and nothing else changes

#### Scenario: An unknown announcement is refused

- **WHEN** a user records as seen an identifier that is not an announcement
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
them to users, reading the most recent announcement and its author, and
reading the activation history, SHALL require the same platform-administration
authority as banners. Reading the visible patch notes with whether an
announcement is pending for the caller, and recording that the caller has seen
an announcement, SHALL require authentication only. Patch notes that are not
visible SHALL only be returned to platform administrators. No request SHALL
record or read what another user has seen.

#### Scenario: Non-administrator cannot read the history

- **WHEN** an authenticated user without platform-administration authority requests the activation history
- **THEN** the request is refused and no event is returned

#### Scenario: Non-administrator cannot manage patch notes

- **WHEN** an authenticated user without platform-administration authority tries to create, edit, delete, reorder or toggle a patch note
- **THEN** the request is refused and nothing changes

#### Scenario: Non-administrator cannot announce

- **WHEN** an authenticated user without platform-administration authority tries to announce the patch notes
- **THEN** the request is refused and no announcement is recorded

#### Scenario: Unauthenticated client cannot read or record

- **WHEN** an unauthenticated client requests the visible patch notes or records an announcement as seen
- **THEN** the request is refused

#### Scenario: Hidden patch notes are not delivered to users

- **GIVEN** patch note A is visible and patch note B is not
- **WHEN** an authenticated user's client requests the visible patch notes
- **THEN** only A is returned

### Requirement: Patch-note dialog after an announcement

When an authenticated user loads the application, an announcement is pending
for that user and at least one patch note is visible, the client SHALL open
the patch-note dialog on position 1: a large dialog showing the note's title
and its body rendered as markdown in the viewer's locale, with a Close button
and the history navigation. The dialog SHALL open with focus on the dialog
itself, at the top of the note, and its links SHALL open in a new tab. The
dialog SHALL NOT open on pre-authentication screens.

An announcement SHALL be pending for a user when an administrator made one and
that user has not recorded the most recent one as seen. The dialog SHALL NOT
open on its own for any other reason: creating, editing, reordering, deleting
a patch note or changing its visibility SHALL NOT open it. An announcement
SHALL NOT be pending for anyone once it has been cancelled, which happens when
the last visible patch note stops being visible; so no announcement is ever
pending while no patch note is visible.

Closing the dialog, whether through Close, Escape or a click outside, SHALL
record the announcement that opened it as seen by that user, whichever
position the user navigated to.

When recording fails, the dialog SHALL still close and SHALL NOT reopen during
the same page view; the only consequence SHALL be that it may open again at a
later load.

#### Scenario: Dialog opens at load after an announcement

- **GIVEN** two visible patch notes and an announcement pending for the user
- **WHEN** the user signs in and the application loads
- **THEN** the patch-note dialog opens on position 1, with its body rendered as markdown, the navigation, a Close button and no "Don't show again" control

#### Scenario: No announcement, no dialog

- **GIVEN** visible patch notes and no announcement ever made
- **WHEN** the user loads the application
- **THEN** no patch-note dialog opens

#### Scenario: Seen once per announcement

- **GIVEN** the patch-note dialog opened at load
- **WHEN** the user closes it with Close, Escape or a click outside
- **THEN** that announcement is recorded as seen by that user on the server
- **AND** the dialog does not open on its own at later loads, including after a new sign-in and from another browser or device

#### Scenario: Creating a patch note does not open the dialog

- **GIVEN** a user who has seen the most recent announcement
- **WHEN** an administrator creates a patch note, makes it visible and moves it to the top, and the user loads the application
- **THEN** no patch-note dialog opens on its own

#### Scenario: Editing a patch note does not open the dialog

- **GIVEN** a user who has seen the most recent announcement
- **WHEN** an administrator edits a visible patch note and the user loads the application
- **THEN** no patch-note dialog opens on its own

#### Scenario: Nothing visible, nothing pending

- **GIVEN** an announcement pending for the user
- **WHEN** an administrator turns off every toggle and the user loads the application
- **THEN** no patch-note dialog opens
- **AND** it does not open at a later load once a patch note is visible again, until an administrator announces again

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
in a neutral style, in the administrator's order. Each row SHALL show, at
its left, a handle to move it, the patch note's title in the administrator's locale, its
visibility toggle, and Preview, Edit and Delete actions. Changing a toggle
SHALL take effect without confirmation.

#### Scenario: Patch-note row content

- **GIVEN** a visible patch note titled `What's new in 3.4` in `en`
- **WHEN** an administrator whose locale is `en` opens the Patch notes tab
- **THEN** its row shows a move control, `What's new in 3.4`, a toggle that is on, and Preview, Edit and Delete actions

#### Scenario: Toggling from the list

- **GIVEN** patch note A is visible and patch note B is not
- **WHEN** an administrator turns on B's toggle
- **THEN** B is visible at once, A stays visible, and no confirmation is shown

### Requirement: Announcement activation and announcing history

The system SHALL record an event every time any announcement, of either type,
goes from disabled to enabled or from enabled to disabled; for a patch note,
enabled means visible. This includes an announcement created already enabled
and an enabled announcement that is deleted. A request that does not change
the enabled state SHALL NOT record an event. The system SHALL also record an
event every time an administrator announces the patch notes to users, and
every time an announcement is cancelled because the last visible patch note
stopped being visible.

Each event SHALL carry the announcement's identifier, its type, a snapshot of
its title per locale taken at the time of the
event, the action (`activated`, `deactivated`, `announced` or `unannounced`),
the time, and the identifier of the acting user. An `announced` event SHALL
carry the identifier and title of the patch note at position 1 at that time;
an `unannounced` event SHALL carry those of the patch note that stopped being
visible. Events
SHALL be written in the same transaction as the
state change they describe, SHALL never be updated or deleted by the
application, and SHALL remain readable after the announcement is deleted.

Platform administrators SHALL be able to read the 100 most recent events,
newest first, and the administration page SHALL show them with the acting
user's display name. The page SHALL let them narrow the table to one action,
and SHALL remember that choice in the browser.

#### Scenario: Showing only activations

- **GIVEN** the history holds activations and deactivations
- **WHEN** an administrator picks the "Activations" filter and later reopens the history
- **THEN** only `activated` events are listed, both times

#### Scenario: Activation and deactivation are recorded with the author

- **WHEN** administrator Alice enables banner X and later administrator Bob disables it
- **THEN** the history lists, newest first, a `deactivated` event for X by Bob and an `activated` event for X by Alice, each with its time and X's title

#### Scenario: Making a patch note visible records one event

- **GIVEN** patch note A is visible
- **WHEN** administrator Alice makes patch note B visible
- **THEN** the history records an `activated` event for B by Alice and no event for A

#### Scenario: Announcing is recorded

- **GIVEN** the visible patch note at position 1 is titled `Version 3.4`
- **WHEN** administrator Alice confirms an announcement
- **THEN** the history records an `announced` event by Alice, labelled `Version 3.4`

#### Scenario: Cancelling is recorded

- **GIVEN** an announcement was made and `Version 3.4` is the only visible patch note
- **WHEN** administrator Bob turns off its toggle
- **THEN** the history records a `deactivated` event then an `unannounced` event, both by Bob and labelled `Version 3.4`

#### Scenario: Nothing to cancel records nothing

- **GIVEN** no announcement was ever made, or the most recent one is already cancelled
- **WHEN** an administrator turns off the last visible patch note
- **THEN** the history records the `deactivated` event only

#### Scenario: Reordering records nothing

- **WHEN** an administrator reorders the patch notes
- **THEN** no event is recorded

#### Scenario: History survives deletion

- **GIVEN** banner X was enabled then disabled
- **WHEN** an administrator deletes X
- **THEN** the history still lists both events for X with its title and type

#### Scenario: Deleting an enabled announcement is recorded

- **WHEN** an administrator deletes a visible patch note
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
visible, the editor SHALL offer to save it and make it visible in one action,
and a plain save SHALL tell the administrator that users do not see it. Neither
save SHALL announce anything to users.

#### Scenario: Closing with unsaved changes asks first

- **GIVEN** an administrator changed a patch note's title in the editor
- **WHEN** they press Escape
- **THEN** a confirmation asks whether to discard the changes, and the editor keeps them if they decline

#### Scenario: Plain save keeps a new patch note out of sight

- **WHEN** an administrator saves a new patch note with the plain save
- **THEN** it is stored with its toggle off, and the administrator is told that users do not see it

#### Scenario: Save and activate

- **GIVEN** a patch note that is not visible, open in the editor
- **WHEN** the administrator picks the action that saves and makes it visible
- **THEN** the patch note is saved and visible, with no confirmation and no change to other patch notes

## REMOVED Requirements

### Requirement: Authorization for patch notes and history

**Reason**: Replaced by "Authorization for patch notes, announcing and
history": the dismissal and dismissal-count clauses and their two scenarios no
longer describe anything, and a modified requirement cannot drop scenarios.

**Migration**: None; the same authority is required for the same surfaces.

### Requirement: One active patch note at a time

**Reason**: Any number of patch notes can now be visible at once; the visible
set is the history users browse. See "Patch-note visibility".

**Migration**: The single patch note enabled before the upgrade stays visible
and the others stay hidden; an administrator turns on the older ones to put
them in the history. Clients no longer receive a `409` on concurrent
activation.

### Requirement: Reopening the active patch note

**Reason**: Replaced by "Browsing patch-note history in the dialog": "What's
new" opens the whole visible history instead of one active patch note.

**Migration**: None for users; the entry keeps its place and label.

### Requirement: Recording a patch-note dismissal

**Reason**: There is no "Don't show again" choice any more, and what a user
has seen is tracked per announcement, not per patch note. Replaced by
"Recording that an announcement was seen".

**Migration**: Existing dismissals are discarded. No announcement is pending
after the upgrade, so no user gets a dialog until an administrator announces.

### Requirement: Patch-note dialog at application load

**Reason**: Replaced by "Patch-note dialog after an announcement": the dialog opens for a pending announcement, not for an enabled patch note, and has no checkbox. A modified requirement
cannot drop scenarios, so it is replaced under a new name.

**Migration**: None beyond what the replacing requirement states.

### Requirement: Patch notes in the admin list

**Reason**: Replaced by "Patch notes in the Patch notes tab": the row gains a move handle and loses the confirmation naming a replaced patch note. A modified requirement
cannot drop scenarios, so it is replaced under a new name.

**Migration**: None beyond what the replacing requirement states.

### Requirement: Announcement activation history

**Reason**: Replaced by "Announcement activation and announcing history": the history also holds `announced` and `unannounced` events, and enabling a patch note no longer deactivates another. A modified requirement
cannot drop scenarios, so it is replaced under a new name.

**Migration**: None beyond what the replacing requirement states.
