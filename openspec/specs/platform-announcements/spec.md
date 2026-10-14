# platform-announcements Specification

## Purpose
Lets platform administrators communicate with every user of the deployment at
runtime, by authoring announcements that render as dismissible banners at the
top of the application without requiring a redeploy.

## Requirements

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

### Requirement: More-info dialog

A banner SHALL offer a "more info" action when, and only when, its
`description_long` is non-empty for the resolved locale. Activating it SHALL
open a dialog showing the announcement's title and its rendered
`description_long`.

The dialog SHALL be dismissible by its own close button and by the standard
dismissal gestures of the application's dialogs. Closing the dialog SHALL NOT
dismiss the banner.

#### Scenario: More-info action is offered

- **WHEN** an announcement has a non-empty `description_long`
- **THEN** its banner shows the more-info action

#### Scenario: More-info action is absent

- **WHEN** an announcement has an empty `description_long`
- **THEN** its banner shows no more-info action

#### Scenario: Dialog shows the long description

- **WHEN** a user activates the more-info action
- **THEN** a dialog opens with the announcement's title and its `description_long` rendered as markdown

#### Scenario: Closing the dialog leaves the banner

- **WHEN** a user closes the more-info dialog
- **THEN** the dialog closes and the banner remains visible

### Requirement: Dismissing a banner

A banner SHALL offer a dismiss action when, and only when, its announcement is
marked dismissible. Dismissing SHALL remove that banner from the stack with a
short collapse animation, leaving the other banners in place.

A dismissal SHALL persist for that user's browser, so the banner does not
return on a later page load or sign-in, for as long as the announcement's
content version is unchanged.

A change to the announcement's content version SHALL make the banner appear
again for users who had dismissed the previous version.

Dismissal state is stored client-side; it SHALL NOT follow the user to a
different browser or device, and losing it SHALL only cause the banner to
reappear, never any other failure.

#### Scenario: Dismissible banner is dismissed

- **WHEN** a user activates the dismiss action on a dismissible banner
- **THEN** that banner collapses and is removed, and any other banners remain

#### Scenario: Non-dismissible banner offers no dismiss action

- **WHEN** an announcement is marked not dismissible
- **THEN** its banner shows no dismiss action and cannot be removed by the user

#### Scenario: Dismissal survives a reload

- **WHEN** a user dismisses a banner and later reloads the application in the same browser
- **THEN** that banner does not render

#### Scenario: Edited announcement reappears

- **WHEN** an administrator edits an announcement a user had dismissed
- **THEN** that user sees the banner again on the next delivery

#### Scenario: Dismissal does not cross browsers

- **WHEN** a user who dismissed a banner in one browser opens the application in another
- **THEN** the banner renders there

#### Scenario: Unavailable client storage degrades safely

- **WHEN** the browser's local storage cannot be read or written
- **THEN** the banners render and remain usable, and dismissals simply do not persist

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
notes. Its label SHALL carry the number of included patch notes against the
most an announcement holds, as in "Announce the update (3/10)". The action
SHALL show the included patch notes in their order and ask the administrator
to confirm before anything happens.

Once confirmed, the system SHALL freeze the included patch notes, in list
order, with their title and body in every language they hold, as a package
recorded with its time and the acting administrator. That package, and only
it, SHALL be what users read until the next announcement or a withdrawal.
Every announcement SHALL create a new package and SHALL make the dialog open
for every user at their next application load, once per user for that
announcement, including users who had seen the previous one. There SHALL be no
way to change a package once announced.

The package SHALL be exactly the list the administrator confirmed: the
request SHALL name the confirmed patch notes in order, and SHALL be refused,
announcing nothing, when the included patch notes are no longer that list in
that order. The page SHALL then reload the list and tell the administrator
that the selection changed. The action SHALL be unavailable while a toggle or
a reorder is still being saved.

An announcement SHALL hold at most 10 patch notes. Above that number the
action SHALL be unavailable, with a hint to deselect some, and a request to
announce SHALL be refused.

Two announcements or withdrawals requested at the same time SHALL be applied
one after the other, so that at most one package is in effect.

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

#### Scenario: The list changed since the confirmation

- **GIVEN** an administrator's confirmation lists A then B, while another administrator has just excluded B
- **WHEN** the first administrator confirms
- **THEN** the request is refused, no package is recorded, the list is reloaded and the page says the selection changed

#### Scenario: More patch notes than an announcement holds

- **GIVEN** 11 patch notes are included
- **WHEN** an administrator opens the Patch notes tab
- **THEN** the announce action is disabled with a hint to deselect some
- **AND** a request to announce sent anyway is refused and records nothing

#### Scenario: Two administrators announce at the same time

- **WHEN** two administrators confirm an announcement at the same moment
- **THEN** one package is in effect afterwards and the other one's line is ended

#### Scenario: Nothing included, no announcement

- **GIVEN** no patch note is included
- **WHEN** an administrator opens the Patch notes tab
- **THEN** the announce action is disabled
- **AND** a request to announce sent anyway is refused and records nothing

### Requirement: Withdrawing the current announcement

The Patch notes tab SHALL offer an action, "Withdraw the current
announcement", available while an announcement is in effect, including when
the list holds no patch note any more. It SHALL tell the
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

#### Scenario: Withdrawing after every patch note was deleted

- **GIVEN** an announcement is in effect and every patch note has since been deleted
- **WHEN** an administrator opens the Patch notes tab
- **THEN** the withdraw action is offered above the empty state

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
new position, shown from its top. The dialog SHALL keep the same height from
one patch note to the next, whatever their length. With a single patch note
the dialog SHALL show no navigation. The dialog SHALL NOT offer any "Don't show again" control.

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
locale, its toggle, and Preview, Edit and Delete actions. The toggle SHALL be
a checkbox labelled by the patch note's title and its "included" or "not
included" status, so that activating that text changes it. Changing a toggle
SHALL take effect without confirmation.

#### Scenario: Patch-note row content

- **GIVEN** an included patch note titled `What's new in 3.4` in `en`
- **WHEN** an administrator whose locale is `en` opens the Patch notes tab
- **THEN** its row shows a move control, a checked checkbox named `What's new in 3.4`, and Preview, Edit and Delete actions

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
