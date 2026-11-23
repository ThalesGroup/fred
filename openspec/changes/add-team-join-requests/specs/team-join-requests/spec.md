## ADDED Requirements

### Requirement: On request is an opt-in access mode of public teams

`JoiningMode` SHALL accept `on_request`, set by a holder of `can_update_info` through the team update. A private team MUST NOT keep it: the control-plane SHALL store `invite_only`. When a team leaves `on_request`, every pending request SHALL be refused, its requester told, and the request deleted, with no 24-hour wait. No team SHALL change mode on upgrade, and the importer SHALL keep mapping legacy `request_only` to `invite_only`.

#### Scenario: Leaving the mode

- **WHEN** an admin switches Atlas from On request to Invite only while Alice's request is pending
- **THEN** Alice is told her request was refused and may ask again as soon as Atlas takes requests

### Requirement: A non-member can ask to join

A non-member of a public `on_request` team SHALL be able to ask to join with an optional message of at most 280 characters, and cancel while pending. A person SHALL have at most one request per team: asking again while pending SHALL return it; asking less than 24 hours after a refusal SHALL answer 409 `join_request_refused`. The team card SHALL show "Ask to join", "Request sent" with "Cancel request", or "Request declined".

#### Scenario: Asking twice

- **WHEN** Alice asks to join Atlas twice
- **THEN** the second call returns her pending request and no admin is notified again

### Requirement: Team admins accept or refuse

Only a holder of `can_administer_members` SHALL accept or refuse a request, checked on each call. Accepting SHALL grant `team_member` only, then delete the request. Refusing SHALL keep it 7 days, during which "Accept anyway" SHALL accept it while the team is public and `on_request` (else 409 `team_not_on_request`). A decision on a request that no longer exists SHALL answer 404.

#### Scenario: Two admins decide at once

- **WHEN** Bob and Carol accept Alice's request at the same time
- **THEN** one call succeeds and the other answers 404

### Requirement: Joining another way closes the request

Any other grant of a role on the team SHALL delete the person's request to it and its notifications, with no answer sent.

#### Scenario: Added from the Members tab

- **WHEN** Bob adds Alice from the Members tab while her request is pending
- **THEN** the request and its notifications are deleted

### Requirement: Admins see requests in the Members tab

The Members tab SHALL offer a Requests tab to holders of `can_administer_members` listing pending requests and those refused in the last 7 days, refreshed on its own, never through notifications.

#### Scenario: Admin promoted after the request

- **WHEN** Carol becomes an admin of Atlas after Alice asked
- **THEN** Carol sees Alice's request in the Requests tab

### Requirement: A non-member sees a not-a-member screen

Opening a team page SHALL show "You are not a member of this team" to a non-member, platform admins included, with "Ask to join" on a public `on_request` team unless a request is pending or a refusal makes them wait.

#### Scenario: Former member follows an old link

- **WHEN** Alice, removed from Atlas, opens a link to Atlas's agents
- **THEN** she sees the not-a-member screen, not the agents

### Requirement: Join requests expire, are cleaned up and audited

Pending requests SHALL expire after 30 days and refused ones 7 days after refusal, deleted by the lifecycle job. Deleting a team or a user SHALL delete their requests. Creating, cancelling, accepting and refusing SHALL be audited without the message text.

#### Scenario: Expiry

- **WHEN** a pending request is 31 days old
- **THEN** it is no longer listed and the next lifecycle run deletes it
