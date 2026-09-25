# platform-announcements Specification

## Purpose
Lets platform administrators communicate with every user of the deployment at
runtime, by authoring announcements that render as dismissible banners at the
top of the application without requiring a redeploy.

## Requirements

### Requirement: Announcement content model

An announcement SHALL carry a severity, localized text, and two independent
flags controlling whether it is shown and whether a user may dismiss it.

Severity SHALL be one of `info`, `warning`, `error`, `success`. Each severity
SHALL determine the banner's colour and icon; neither is separately authorable.

`title`, `description_short` and `description_long` SHALL each be a map from
locale code to text, supporting at least `fr` and `en`. Text SHALL be resolved
against the viewer's active locale, falling back to `en` when that locale has
no entry.

`description_short` and `description_long` SHALL be interpreted as markdown.

An announcement SHALL carry a content version that changes whenever any of its
text, severity, or `dismissible` flag changes, and whenever a disabled
announcement is enabled again. Disabling an announcement SHALL NOT change it:
nothing a reader sees has moved.

Replacing an announcement's content SHALL NOT change whether it is delivered.
Enabling and disabling SHALL be a distinct operation.

#### Scenario: Locale resolution with fallback

- **WHEN** an announcement has a `fr` and an `en` title and the viewer's locale is `fr`
- **THEN** the `fr` title is displayed

#### Scenario: Missing locale falls back to English

- **WHEN** an announcement has only an `en` title and the viewer's locale is `fr`
- **THEN** the `en` title is displayed

#### Scenario: Severity fixes the icon

- **WHEN** an announcement has severity `warning`
- **THEN** the banner renders the warning icon and warning colour
- **AND** no authored icon or colour can override them

#### Scenario: Rejecting an unknown severity

- **WHEN** an administrator submits an announcement whose severity is not one of the four allowed values
- **THEN** the request is rejected with a validation error and nothing is persisted

### Requirement: Administering announcements

The system SHALL let a platform administrator list, create, update, delete, and
enable or disable announcements. Every one of those operations SHALL require
platform-administration authority.

Creating or updating an announcement SHALL require a non-empty `title` and
`description_short` for at least one locale. `description_long` SHALL be
optional.

Each administrative mutation SHALL emit an audit record naming the acting user
and the affected announcement.

#### Scenario: Administrator creates an announcement

- **WHEN** a platform administrator submits a valid announcement
- **THEN** it is persisted, returned with its identifier and content version, and an audit record is emitted

#### Scenario: Non-administrator is refused

- **WHEN** an authenticated user without platform-administration authority calls any announcement administration operation
- **THEN** the request is refused and no announcement is created, changed, or deleted

#### Scenario: Announcement without a short description is rejected

- **WHEN** an administrator submits an announcement whose `description_short` is empty for every locale
- **THEN** the request is rejected with a validation error

#### Scenario: Editing bumps the content version

- **WHEN** an administrator changes the text of an existing announcement
- **THEN** its content version changes

#### Scenario: Toggling does not require a full resubmission

- **WHEN** an administrator disables an enabled announcement
- **THEN** the announcement is retained with its content intact and stops being delivered to users
- **AND** its content version is unchanged

#### Scenario: Re-enabling relaunches the announcement for everyone

- **WHEN** an administrator enables an announcement that was disabled
- **THEN** its content version changes, so the banner appears again for users who had dismissed the previous run

### Requirement: Delivering active announcements

The system SHALL expose the set of enabled announcements to any authenticated
user. Announcements SHALL NOT be readable without authentication.

The delivered set SHALL reflect an administrator's change within approximately
one minute for a user who leaves the application open, and immediately when the
application regains window focus or is loaded.

#### Scenario: Enabled announcements are delivered

- **WHEN** an authenticated user's client requests the active announcements and two announcements are enabled
- **THEN** both are returned, and disabled ones are not

#### Scenario: Unauthenticated access is refused

- **WHEN** an unauthenticated client requests the active announcements
- **THEN** the request is refused

#### Scenario: A newly enabled announcement reaches an open session

- **WHEN** an administrator enables an announcement while a user has the application open and idle
- **THEN** that user's client displays the banner without a manual reload, within about a minute

#### Scenario: Returning to the tab refreshes immediately

- **WHEN** a user switches back to the application's browser tab
- **THEN** the client re-reads the active announcements before the next polling interval elapses

### Requirement: Rendering the banner stack

Enabled announcements SHALL render as full-width banners at the top of the
application, above the routed content and pushing it down rather than
overlaying it. They SHALL only render for an authenticated user, and SHALL NOT
render on pre-authentication screens.

When several announcements are enabled, all of them SHALL render, stacked and
ordered by severity — `error`, then `warning`, then `success`, then `info` —
and, within one severity, by creation date, oldest first.

Each banner SHALL show its severity icon, its title, and its rendered
`description_short`, followed by an actions toolbar.

#### Scenario: Multiple announcements stack in severity order

- **WHEN** an `info` and an `error` announcement are both enabled
- **THEN** both banners render, with the `error` banner above the `info` one

#### Scenario: Content is pushed down, not covered

- **WHEN** one or more banners render
- **THEN** the routed page content starts below them and remains fully reachable

#### Scenario: Nothing renders before authentication

- **WHEN** an unauthenticated visitor reaches a pre-authentication screen and announcements are enabled
- **THEN** no banner renders

#### Scenario: No enabled announcements renders nothing

- **WHEN** no announcement is enabled
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
