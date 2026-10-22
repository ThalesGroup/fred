## ADDED Requirements

### Requirement: On request is an opt-in access mode of public teams

`JoiningMode` SHALL accept `on_request` next to `open` and `invite_only`. Only a holder of `can_update_info` on the team SHALL change it, through the existing team update. A team that is private after an update MUST NOT keep `on_request`: the control-plane SHALL store `invite_only` instead. When a team leaves `on_request`, by an explicit change or by becoming private, the control-plane SHALL send each pending requester the refusal notification and delete the request, so this automatic refusal never starts the 24-hour wait; only an admin's refusal does. Asking and this sweep SHALL be serialized per team, so no pending request survives on a team that no longer takes requests. No existing team SHALL change mode on upgrade. The Parameters tab SHALL offer Open, On request and Invite only for a public team and keep the locked "manual only" button for a private one.

#### Scenario: An admin opts in

- **WHEN** an admin of a public `invite_only` team picks On request
- **THEN** the team's `joining_mode` is `on_request` and its card offers "Ask to join" to non-members

#### Scenario: Making the team private

- **WHEN** an admin makes an `on_request` team private
- **THEN** its `joining_mode` becomes `invite_only`

#### Scenario: Leaving the mode refuses pending requests

- **WHEN** an admin of Atlas switches it from On request to Invite only while Alice and Frank have pending requests
- **THEN** Alice and Frank each receive "Your request to join Atlas was refused", and neither request remains in Atlas's Members tab

#### Scenario: No wait after an automatic refusal

- **GIVEN** Atlas left On request, automatically refusing Alice's request, and came back to On request an hour later
- **WHEN** Alice asks to join Atlas again
- **THEN** a new pending request is created; Erik, refused by an admin before the switch, still waits until 24 hours after that refusal

#### Scenario: Upgrade

- **WHEN** a platform upgrades to this version
- **THEN** every team keeps its `joining_mode` and nobody can send a join request until an admin picks On request

### Requirement: Legacy request_only imports as invite_only

The platform importer SHALL map a bundle's legacy `request_only` (and `closed`) to `invite_only` and SHALL import `on_request` unchanged.

#### Scenario: Old bundle

- **WHEN** an administrator imports a bundle exported before July 2026 whose teams carry `request_only`
- **THEN** those teams are `invite_only` and receive no join requests

### Requirement: A non-member can ask to join an on-request team

An authenticated platform user who is not a member of a public `on_request` team SHALL be able to create a join request with an optional message of at most 280 characters. The control-plane MUST refuse the request when the team is not `on_request` (409), or when the caller is already a member (409). A person SHALL have at most one request per team: asking again while it is pending SHALL return the pending request and emit nothing; asking less than 24 hours after a refusal of that team SHALL answer 409 `join_request_refused`; asking later SHALL replace the refused request with a new pending one.

#### Scenario: First ask

- **WHEN** Alice asks to join the public `on_request` team Atlas with the message "I run the Lyon pilot"
- **THEN** a pending request exists for Alice and Atlas, expiring 30 days later, and Atlas's admins are notified

#### Scenario: Asking twice

- **WHEN** Alice asks to join Atlas again while her request is pending
- **THEN** the response is her existing request and no admin receives a new notification

#### Scenario: Team not on request

- **WHEN** Alice asks to join an `invite_only` team
- **THEN** the request answers 409 and nothing is stored

#### Scenario: After a refusal

- **WHEN** Alice asks to join Atlas 2 hours after an admin refused her request
- **THEN** the request answers 409 `join_request_refused`

#### Scenario: Asking again the next day

- **WHEN** Alice asks to join Atlas 25 hours after an admin refused her request
- **THEN** a new pending request replaces the refused one and Atlas's admins are notified again

### Requirement: The requester sees and cancels their request on the team card

The Teams marketplace SHALL load the caller's own unexpired requests once and pass each to its team's card. A non-member card of an `on_request` team SHALL show "Ask to join" without a request, "Request sent" with "Cancel request" while pending, and "Request declined" for 24 hours after a refusal, then "Ask to join" again. Cancelling SHALL delete the request and the admins' open notifications about it; the person MAY then ask again.

#### Scenario: Cancel

- **WHEN** Alice cancels her pending request to Atlas
- **THEN** the request is gone, Atlas's admins no longer have its notification, and her card shows "Ask to join" again

### Requirement: Team admins accept or refuse a request

Only a holder of `can_administer_members` on the team SHALL accept or refuse one of its requests; the check SHALL be made by the control-plane on each call. Accepting SHALL grant the requester `team_member` and nothing else, then delete the request, so a failed grant leaves the request to decide again. Refusing SHALL mark it refused and keep it 7 days. Accepting a refused request ("Accept anyway") SHALL be allowed during those 7 days while the team is public and `on_request`, SHALL grant `team_member` the same way and SHALL send the requester the acceptance notification in place of the refusal one. Accepting when the team is no longer public and `on_request` SHALL answer 409 `team_not_on_request` and change nothing. A decision on a request that no longer exists SHALL answer 404 `join_request_not_found`. A decision on a requester who is already a member SHALL only delete the request and its notifications, sending no answer.

#### Scenario: Accept

- **WHEN** Bob, an admin of Atlas, accepts Alice's request
- **THEN** Alice is a `team_member` of Atlas with no other role and the request no longer exists

#### Scenario: Two admins decide at once

- **WHEN** Bob accepts Alice's request and Carol, another admin, then refuses it
- **THEN** Carol's call answers 404 and Alice stays a member

#### Scenario: Accept anyway

- **WHEN** Bob refused Alice's request to Atlas 3 days ago and Carol clicks Accept anyway in the Members tab
- **THEN** Alice is a `team_member` of Atlas, the request no longer exists, and Alice receives "Your request to join Atlas was accepted" instead of the refusal

#### Scenario: Not an admin

- **WHEN** Dan, an editor of Atlas, calls accept on Alice's request
- **THEN** the call answers 403 and nothing changes

#### Scenario: Accept anyway after the team stopped taking requests

- **GIVEN** Bob refused Alice's request to Atlas, then Atlas became Invite only
- **WHEN** Carol calls accept on that refused request
- **THEN** the call answers 409 `team_not_on_request`, Alice is not a member and the refused request stays

#### Scenario: Failed grant

- **WHEN** Bob accepts Alice's request and writing her membership fails
- **THEN** the call fails and Alice's request is still pending, with the admins' tiles still open

### Requirement: Joining another way closes the request

Any other grant of a role on the team (an admin adding the person from the Members tab or granting them a role, the team invite link, the default teams of a new user, the platform admin's team registry or admin rescue, a self-service join) SHALL delete the person's request to that team, whatever its state, and the notifications of both its groups; no answer SHALL be sent to the person.

#### Scenario: Added from the Members tab

- **GIVEN** Alice has a pending request to Atlas
- **WHEN** Bob adds Alice from the Members tab
- **THEN** Alice's request is gone, Bob's and Carol's request tiles are gone, and Alice receives no answer

### Requirement: Admins see pending requests in the Members tab

The Members tab SHALL show a "Pending requests" section to holders of `can_administer_members` while the team has pending requests or requests refused in the last 7 days, each with the requester's name, message and date; a pending one SHALL offer Refuse (left) and Accept (right), a refused one Accept anyway while the team is public and `on_request` (refused rows are hidden otherwise). A failed decision SHALL show the error toast. The section SHALL be absent when there is none. It SHALL stay fresh across sessions on its own (periodic refresh and refetch on focus), never through notifications.

#### Scenario: Admin promoted after the request

- **WHEN** Erin becomes an admin of Atlas after Alice asked to join
- **THEN** Erin has no notification for it but sees Alice's request in the Members tab and can accept it

### Requirement: A non-member sees a not-a-member screen on a team's pages

Opening any `/team/<team_id>/...` page SHALL show a loading state until a membership answer fetched since the team was opened arrives, then the page for a member, or a "You are not a member of this team" screen for anyone else, platform admins included. On a public `on_request` team the screen SHALL offer "Ask to join", except while the person's request is pending or a refusal still makes them wait, where it says so and points to the Teams marketplace instead; on any other team it SHALL point to the Teams marketplace. This rule is enforced in the UI only; enforcing team membership server-side for platform admins is tracked in GitHub issue #3260.

#### Scenario: Former member follows an old link

- **WHEN** Alice, who left Atlas, opens a link to Atlas's Agents page
- **THEN** she sees "You are not a member of this team" and not the team's pages

#### Scenario: Platform admin who is not a member

- **WHEN** a platform admin who holds no role on Atlas opens Atlas's pages
- **THEN** they see the same not-a-member screen

#### Scenario: Public on-request team

- **WHEN** Frank, not a member, opens a page of the public `on_request` team Atlas
- **THEN** the screen offers "Ask to join", which opens the request dialog

#### Scenario: Refused less than 24 hours ago

- **WHEN** Frank, refused by Atlas's admin an hour ago, opens a page of Atlas
- **THEN** the screen says when he may ask again and offers no "Ask to join"

### Requirement: Join requests expire and are cleaned up

A pending request SHALL expire 30 days after creation and a refused one 7 days after its refusal; every read SHALL ignore expired requests, a new ask SHALL replace an expired one, and the lifecycle notification step SHALL delete expired requests. Deleting a team SHALL delete its requests; deleting a user SHALL delete their requests and the admins' open notifications about them.

#### Scenario: Expiry

- **WHEN** nobody decides on Alice's request for 30 days
- **THEN** it no longer appears anywhere and Alice can ask again

### Requirement: Join request actions are audited

Creating, cancelling, accepting and refusing a request SHALL each emit an audit event with the actor, the team and the request id, and the requester on decisions. The message text MUST NOT appear in audit events or logs.

#### Scenario: Refusal audit

- **WHEN** Bob refuses Alice's request
- **THEN** a `team.join_request.refused` event names Bob as actor, Atlas, the request id and Alice as requester, without her message
