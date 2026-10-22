## ADDED Requirements

### Requirement: On request is an opt-in access mode of public teams

`JoiningMode` SHALL accept `on_request` next to `open` and `invite_only`. Only a holder of `can_update_info` on the team SHALL change it, through the existing team update. A team that is private after an update MUST NOT keep `on_request`: the control-plane SHALL store `invite_only` instead. No existing team SHALL change mode on upgrade. The Parameters tab SHALL offer Open, On request and Invite only for a public team and keep the locked "manual only" button for a private one.

#### Scenario: An admin opts in

- **WHEN** an admin of a public `invite_only` team picks On request
- **THEN** the team's `joining_mode` is `on_request` and its card offers "Ask to join" to non-members

#### Scenario: Making the team private

- **WHEN** an admin makes an `on_request` team private
- **THEN** its `joining_mode` becomes `invite_only`

#### Scenario: Upgrade

- **WHEN** a platform upgrades to this version
- **THEN** every team keeps its `joining_mode` and nobody can send a join request until an admin picks On request

### Requirement: Legacy request_only imports as invite_only

The platform importer SHALL map a bundle's legacy `request_only` (and `closed`) to `invite_only` and SHALL import `on_request` unchanged.

#### Scenario: Old bundle

- **WHEN** an administrator imports a bundle exported before July 2026 whose teams carry `request_only`
- **THEN** those teams are `invite_only` and receive no join requests

### Requirement: A non-member can ask to join an on-request team

An authenticated platform user who is not a member of a public `on_request` team SHALL be able to create a join request with an optional message of at most 280 characters. The control-plane MUST refuse the request when the team is not `on_request` (409), or when the caller is already a member (409). A person SHALL have at most one request per team: asking again while it is pending SHALL return the pending request and emit nothing; asking while a refused request of that team is unexpired SHALL answer 409 `join_request_refused`.

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

- **WHEN** Alice asks to join Atlas 5 days after an admin refused her request
- **THEN** the request answers 409 `join_request_refused`

### Requirement: The requester sees and cancels their request on the team card

The Teams marketplace SHALL load the caller's own unexpired requests once and pass each to its team's card. A non-member card of an `on_request` team SHALL show "Ask to join" without a request, "Request sent" with "Cancel request" while pending, and "Request declined" after a refusal. Cancelling SHALL delete the request and the admins' open notifications about it; the person MAY then ask again.

#### Scenario: Cancel

- **WHEN** Alice cancels her pending request to Atlas
- **THEN** the request is gone, Atlas's admins no longer have its notification, and her card shows "Ask to join" again

### Requirement: Team admins accept or refuse a request

Only a holder of `can_administer_members` on the team SHALL accept or refuse one of its requests; the check SHALL be made by the control-plane on each call. Accepting SHALL grant the requester `team_member` and nothing else, then delete the request. Refusing SHALL mark it refused until its expiry. A decision on a request that no longer exists SHALL answer 404 `join_request_not_found`. A team's pending requests SHALL stay decidable after the team leaves `on_request`.

#### Scenario: Accept

- **WHEN** Bob, an admin of Atlas, accepts Alice's request
- **THEN** Alice is a `team_member` of Atlas with no other role and the request no longer exists

#### Scenario: Two admins decide at once

- **WHEN** Bob accepts Alice's request and Carol, another admin, then refuses it
- **THEN** Carol's call answers 404 and Alice stays a member

#### Scenario: Not an admin

- **WHEN** Dan, an editor of Atlas, calls accept on Alice's request
- **THEN** the call answers 403 and nothing changes

### Requirement: Admins see pending requests in the Members tab

The Members tab SHALL show a "Pending requests" section to holders of `can_administer_members` while the team has unexpired pending requests, each with the requester's name, message and date and the Accept and Refuse actions. The section SHALL be absent when there is none.

#### Scenario: Admin promoted after the request

- **WHEN** Erin becomes an admin of Atlas after Alice asked to join
- **THEN** Erin has no notification for it but sees Alice's request in the Members tab and can accept it

### Requirement: Join requests expire and are cleaned up

A request SHALL expire 30 days after creation; every read SHALL ignore expired requests, a new ask SHALL replace an expired one, and the lifecycle notification step SHALL delete expired requests. Deleting a team SHALL delete its requests; deleting a user SHALL delete their requests and the admins' open notifications about them.

#### Scenario: Expiry

- **WHEN** nobody decides on Alice's request for 30 days
- **THEN** it no longer appears anywhere and Alice can ask again

### Requirement: Join request actions are audited

Creating, cancelling, accepting and refusing a request SHALL each emit an audit event with the actor, the team and the request id, and the requester on decisions. The message text MUST NOT appear in audit events or logs.

#### Scenario: Refusal audit

- **WHEN** Bob refuses Alice's request
- **THEN** a `team.join_request.refused` event names Bob as actor, Atlas, the request id and Alice as requester, without her message
