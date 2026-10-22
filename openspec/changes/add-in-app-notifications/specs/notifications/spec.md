## ADDED Requirements

### Requirement: Notifications belong to one recipient

The control-plane SHALL store one notification per recipient. Every notification route SHALL act only on the caller's own notifications; a notification of another user MUST answer 404. No route SHALL let a client create a notification or choose its recipients: recipients SHALL be computed by the control-plane service that emits it.

#### Scenario: Reading someone else's notification

- **WHEN** Bob marks as read or deletes a notification addressed to Alice
- **THEN** the request answers 404 and Alice's notification is unchanged

#### Scenario: Listing

- **WHEN** Alice lists her notifications
- **THEN** only notifications addressed to Alice are returned, newest first, at most 50 per page, with a cursor for the next page

### Requirement: Notifications are rendered from type and payload

A notification SHALL carry a registered type and a payload of ids plus a display snapshot taken at creation; it MUST NOT store rendered text. The frontend SHALL render its icon, title, body, link and buttons from the type and the payload in the viewer's locale. An unknown type SHALL render as a generic tile without buttons.

#### Scenario: Locale follows the viewer

- **WHEN** a notification created while Alice used French is shown after she switches to English
- **THEN** its title and body are in English

### Requirement: Badge counts unseen notifications

The far-left app bar SHALL show a Notifications entry with a bell icon. Its badge SHALL show the number of the caller's unseen, unexpired notifications and SHALL be hidden at zero; above 99 it SHALL read "99+"; the count SHALL also be in the entry's accessible name. Opening the popover SHALL mark as seen every notification up to the newest one it listed, so the badge resets; a notification created after that point SHALL stay unseen.

#### Scenario: Opening resets the badge

- **WHEN** Alice has 3 unseen notifications and opens the popover
- **THEN** the badge disappears once the popover has loaded

#### Scenario: Arrival while the popover is open

- **WHEN** a notification is created for Alice after her popover listed its items
- **THEN** it is not marked seen by that opening and badges on the next refresh

### Requirement: Badge updates while the user is in the app

While the application tab is visible, the frontend SHALL refresh the unseen count at most every 15 seconds and on focus or visibility change; it MUST NOT poll while the tab is hidden, and MUST NOT hold a connection open for notifications. No toast SHALL be shown.

#### Scenario: Live arrival

- **WHEN** a notification is created for Alice while her tab is visible
- **THEN** her badge shows it within 15 seconds, without a reload

#### Scenario: Hidden tab

- **WHEN** Alice's tab is hidden
- **THEN** no unseen-count request is sent until it becomes visible again, when one is sent at once

### Requirement: Popover lists, reads and deletes notifications

Clicking the bell SHALL open a popover over the navigation panel, closed by an outside click or Escape. It SHALL list the caller's notifications newest first with an empty state when there are none, and a "Clear all" action deleting all of them except the pending decisions. A tile SHALL disappear as soon as its recipient acts on it: clicking the tile, or a button that follows a link, SHALL delete it for the caller and follow its link if it has one; a button calling a domain endpoint SHALL leave the deletion to that endpoint, so the tile goes only when the call succeeds and stays when it fails. Each tile SHALL show an always-visible close button that deletes it, except a pending decision. Tiles SHALL keep an unread style until acted on.

A pending decision is an unhandled notification of a decision type (`team.join_requested`). Its tile SHALL have no close button, and clicking it SHALL follow its link without deleting it; it SHALL stay until someone decides. Once handled, it SHALL show "handled by <name>" instead of its buttons and get its close button back. "Clear all" SHALL keep pending decisions, server-side, and SHALL be disabled when they are all the popover lists.

#### Scenario: Dismissed on click

- **WHEN** Alice clicks a tile, or its "Open the agent" button
- **THEN** its link opens and the notification is deleted for her

#### Scenario: Failed action keeps the tile

- **WHEN** Alice clicks a button that calls a domain endpoint and the call fails
- **THEN** her tile stays in the list

#### Scenario: Close without hovering

- **WHEN** Alice looks at her list without hovering or focusing a tile
- **THEN** each tile except a pending decision shows its close button, which deletes it

#### Scenario: Pending decision

- **WHEN** Bob, an admin of Atlas, holds an open join request tile and clicks it
- **THEN** the tile has no close button, the Members tab opens and the tile stays in his list
- **AND** once Carol decides, Bob's tile reads "Accepted by Carol" and shows its close button

#### Scenario: Clear all

- **WHEN** Alice chooses "Clear all"
- **THEN** all her notifications are deleted and the empty state is shown

#### Scenario: Clear all keeps pending decisions

- **GIVEN** Bob holds two information tiles and an open join request tile
- **WHEN** he chooses "Clear all"
- **THEN** only the join request tile remains, and "Clear all" is disabled

### Requirement: Repeated subjects do not repeat notifications

Notifications about the same subject SHALL share a group key. While a recipient has an unhandled notification for a group, a new emission for that group SHALL update its payload and MUST NOT create a second notification nor reset its seen or read state.

#### Scenario: Two saves of a published agent

- **WHEN** Bob saves two changes to an agent Alice published
- **THEN** Alice has one republish notification, showing the latest editor, and its badge counted once

### Requirement: Actionable notifications are resolved once for all recipients

A notification type MAY declare buttons. A button SHALL either navigate or call the existing domain endpoint for that action, which keeps its own authorization and audit. When the subject of a group is acted on, the actor's own notification SHALL disappear, and every other recipient's notification of that group SHALL show who handled it instead of its buttons.

#### Scenario: Acted on by the recipient

- **WHEN** Alice republishes the agent her republish notification is about
- **THEN** that notification disappears from her list

#### Scenario: Acted on by someone else

- **WHEN** Bob republishes the agent that Alice's republish notification is about
- **THEN** Alice's notification shows "Handled by Bob" and no button

### Requirement: Notifications expire after 30 days

A notification SHALL expire 30 days after its creation. Expired notifications MUST NOT be listed or counted, and SHALL be deleted by the periodic lifecycle job. Deleting a user SHALL delete their notifications; deleting a team SHALL delete the notifications about that team.

#### Scenario: Expiry

- **WHEN** a notification is 31 days old
- **THEN** it is neither listed nor counted, and the next lifecycle run deletes it

### Requirement: A notification reaches only who can act on it

Every notification type SHALL declare the permission a recipient needs, on the notification's team, to act on what it asks; `agent.republish_needed` and `agent.marketplace_removed` SHALL require `can_update_agents`. A team notification SHALL be sent only to recipients who hold that permission when it is emitted. When a recipient loses that permission (a role is revoked, they leave or are removed from the team, or the team is deleted), their open notifications of that type about that team SHALL be deleted. The unseen count MUST stay a single query on the recipient's own rows.

#### Scenario: The publisher left the team

- **WHEN** Alice published an agent, then left its team, and Bob saves a change to it or a platform admin removes it
- **THEN** Alice receives no notification

#### Scenario: The publisher can no longer edit the team's agents

- **WHEN** Alice published an agent, then lost the editor role while staying a member, and Bob saves a change to it or a platform admin removes it
- **THEN** Alice receives no notification

#### Scenario: Losing the editor role

- **WHEN** Alice holds a republish notification about a team and her editor role on that team is revoked
- **THEN** that notification is deleted and no longer counted in her badge

#### Scenario: Leaving a team

- **WHEN** Alice leaves a team while holding notifications about it
- **THEN** those notifications are deleted; her notifications about other teams are kept

### Requirement: Emitting never fails the triggering action

A notification SHALL be emitted after the triggering action is committed. A failure to emit MUST NOT fail or roll back that action; it SHALL be logged with ids only and counted.

#### Scenario: Store unavailable

- **WHEN** saving a published agent succeeds but the notification insert fails
- **THEN** the save answers success and a warning is logged without payload text

### Requirement: The publisher is asked to update a changed published agent

Publishing or republishing an agent SHALL record who published it. When an editor other than that publisher saves a change to a Published agent, the publisher SHALL receive an action-required notification proposing to update the marketplace version, with an "Open the agent" button opening that agent's edit form on the team's Agents page. No notification SHALL be sent for a save that changes nothing, for the publisher's own save, or for an entry published before the publisher was recorded. Republishing or removing the entry SHALL resolve it.

#### Scenario: Another editor changes the agent

- **WHEN** Bob saves a change to an agent Alice published
- **THEN** Alice receives the republish notification naming Bob and the agent

#### Scenario: The publisher changes their own agent

- **WHEN** Alice saves a change to an agent she published
- **THEN** no notification is created; her in-session republish proposal is unchanged

### Requirement: The publisher learns their agent was removed from the marketplace

When a published entry enters the Removed state (removed by a platform admin, or automatically) and the publisher did not cause it, the publisher SHALL receive an information notification naming the agent and the team, with the removal reason and the platform admin's message if any, and an "Open the agent" button. A removal by a member of the agent's team SHALL NOT notify.

#### Scenario: Platform admin removal

- **WHEN** a platform admin removes Alice's published agent with the message "Duplicate entry"
- **THEN** Alice receives a notification showing the reason and "Duplicate entry"

#### Scenario: Removal by the team

- **WHEN** a team editor removes the entry from the marketplace
- **THEN** no removal notification is created

### Requirement: A platform admin turns each notification type on or off

The platform SHALL offer a platform admin, and only a holder of `can_manage_platform`, the list of every notification type the backend knows, each with whether it is sent. Every type SHALL be on until a platform admin turns it off. The setting SHALL be platform-wide, with no per-team or per-user override. While a type is off, no notification of that type SHALL be created. Turning a type off SHALL delete every notification of that type already sent, for every recipient. Turning it back on SHALL affect only events after the change; deleted notifications MUST NOT come back. The action a notification points to SHALL stay available where it lives. Each change SHALL be audited. The admin page SHALL ask for confirmation before turning a type off, saying the notifications of that type already sent will be deleted for everyone; turning a type on SHALL need no confirmation.

#### Scenario: Every type is on by default

- **WHEN** a platform admin opens the Notifications page on a platform where nothing was changed
- **THEN** every notification type is listed with its name, a sentence on when it is sent and to whom, and its switch on

#### Scenario: Turning a type off

- **GIVEN** Alice and Bob each hold a `team.join_requested` notification
- **WHEN** a platform admin turns `team.join_requested` off
- **THEN** both notifications are deleted, a new join request notifies nobody, and the requests stay in the team's Members > Pending requests

#### Scenario: Confirming a switch-off

- **WHEN** a platform admin switches a type off on the Notifications page
- **THEN** a confirmation says its sent notifications will be deleted, and nothing changes unless they confirm

#### Scenario: Turning a type back on

- **WHEN** a platform admin turns a type back on
- **THEN** the next event of that type notifies its recipients, and the notifications deleted when it was turned off do not come back

#### Scenario: Not a platform admin

- **WHEN** a user without `can_manage_platform` reads or changes the switches
- **THEN** the request is refused and nothing changes

### Requirement: A failed tile action is reported

When a button that calls a domain endpoint fails for any reason other than the subject being gone (404) or the caller no longer allowed to act on it (403), the popover SHALL show the application's error toast and keep the tile usable; on 404 or 403 the tile SHALL be deleted. While one of a tile's calls is in flight, its buttons SHALL be disabled, so a double click sends one decision.

#### Scenario: Accept fails

- **WHEN** a team admin clicks Accept on a join request tile and the endpoint answers 500
- **THEN** an error toast says the action could not be completed and the tile stays

#### Scenario: Double click

- **WHEN** a team admin clicks Accept then Refuse on a tile before the first call answers
- **THEN** only the Accept call is sent

