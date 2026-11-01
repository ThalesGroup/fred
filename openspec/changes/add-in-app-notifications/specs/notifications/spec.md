## ADDED Requirements

### Requirement: Notifications belong to one recipient

The control-plane SHALL store one notification per recipient, and every notification route SHALL act only on the caller's own notifications; another user's notification MUST answer 404. No route SHALL create a notification: the emitting control-plane service SHALL compute its recipients.

#### Scenario: Someone else's notification

- **WHEN** Bob deletes a notification addressed to Alice
- **THEN** the request answers 404 and Alice's notification is unchanged

### Requirement: Notifications are rendered from type and payload

A notification SHALL carry a type and a payload of ids plus a display snapshot; it MUST NOT store rendered text. The frontend SHALL render it in the viewer's locale, and an unknown type as a generic tile without buttons.

#### Scenario: Locale follows the viewer

- **WHEN** a notification created while Alice used French is shown after she switches to English
- **THEN** its title and body are in English

### Requirement: The bell counts unseen notifications

The app bar SHALL show a bell whose badge counts the caller's unseen, unexpired notifications, hidden at zero and "99+" above 99. While the tab is visible the count SHALL refresh at most every 15 seconds and on focus; it MUST NOT poll a hidden tab. Opening the popover SHALL mark as seen every notification up to the newest one listed.

#### Scenario: Opening resets the badge

- **WHEN** Alice has 3 unseen notifications and opens the popover
- **THEN** the badge disappears once the popover has loaded

#### Scenario: Arrival while the popover is open

- **WHEN** a notification is created for Alice after her popover listed its items
- **THEN** it stays unseen and badges on the next refresh

### Requirement: The popover lists and deletes notifications

The popover SHALL list the caller's notifications newest first, 50 per page, with an empty state and "Clear all". "View" or a button that follows a link SHALL delete the notification for the caller and follow the link; each tile SHALL have a close button that deletes it.

#### Scenario: Acting on a tile

- **WHEN** Alice clicks "Open the agent" on a tile
- **THEN** the agent opens and the notification is deleted for her

#### Scenario: Clear all

- **WHEN** Alice chooses "Clear all"
- **THEN** all her notifications are deleted and the empty state is shown

### Requirement: One open notification per subject

Notifications about one subject SHALL share a group key. While a recipient has an unhandled notification of that group, a new emission SHALL update its payload and MUST NOT create a second one nor reset its seen state. When the subject is acted on, the actor's notification SHALL disappear and the other recipients' SHALL show who handled it instead of its buttons.

#### Scenario: Two saves of a published agent

- **WHEN** Bob saves two changes to an agent Alice published
- **THEN** Alice has one republish notification, counted once

#### Scenario: Handled by someone else

- **WHEN** Bob republishes the agent that Alice's republish notification is about
- **THEN** Alice's notification shows "Handled by Bob" and no button

### Requirement: Only who can act receives a notification

Each type SHALL declare the team permission a recipient needs; both marketplace types SHALL require `can_update_agents`. A notification SHALL reach only recipients holding it when emitted, and a recipient who loses it (role revoked, leaving, team deleted) SHALL lose their open notifications of that type about that team.

#### Scenario: Losing the editor role

- **WHEN** Alice holds a republish notification and her editor role on that team is revoked
- **THEN** that notification is deleted and no longer counted

### Requirement: Emitting never fails the triggering action

A notification SHALL be emitted after the triggering commit. A failure MUST NOT fail that action; it SHALL be logged with ids only and counted.

#### Scenario: Store unavailable

- **WHEN** saving a published agent succeeds but the notification insert fails
- **THEN** the save answers success and a warning without payload text is logged

### Requirement: Notifications expire after 30 days

A notification SHALL expire 30 days after creation: it MUST NOT be listed or counted, and the lifecycle job SHALL delete it. Deleting a user or a team SHALL delete their notifications.

#### Scenario: Expiry

- **WHEN** a notification is 31 days old
- **THEN** it is neither listed nor counted, and the next lifecycle run deletes it

### Requirement: The publisher is told about their published agent

Publishing or republishing SHALL record the publisher. When another editor saves a change to a Published agent, the publisher SHALL receive `agent.republish_needed` with an "Open the agent" button; republishing or removing the entry SHALL resolve it. When the entry enters the Removed state without the publisher causing it, the publisher SHALL receive `agent.marketplace_removed` with the reason and the platform admin's message, if any. A removal by the agent's team SHALL NOT notify, nor SHALL an entry published before the publisher was recorded.

#### Scenario: Another editor changes the agent

- **WHEN** Bob saves a change to an agent Alice published
- **THEN** Alice receives the republish notification naming Bob and the agent

#### Scenario: Platform admin removal

- **WHEN** a platform admin removes Alice's published agent with the message "Duplicate entry"
- **THEN** Alice receives a notification showing the reason and "Duplicate entry"

### Requirement: A platform admin turns each type on or off

A holder of `can_manage_platform` SHALL list every notification type with its switch, all on by default, and turn one off or on platform-wide, audited. Turning a type off SHALL hide its notifications from the list, the count and "Clear all" while they are still created; turning it back on SHALL show those still stored. Turning a type off SHALL ask for confirmation first.

#### Scenario: A turned-off type is hidden

- **GIVEN** Alice holds an unseen `agent.marketplace_removed` notification
- **WHEN** a platform admin turns `agent.marketplace_removed` off
- **THEN** that notification is neither listed nor counted on Alice's bell

#### Scenario: Not a platform admin

- **WHEN** a user without `can_manage_platform` reads or changes the switches
- **THEN** the request is refused and nothing changes
