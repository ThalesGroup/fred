## ADDED Requirements

### Requirement: Join requests notify the team's admins

Creating a join request SHALL send `team.join_requested` to every holder of `can_administer_members` on the team, naming the team and the requester, with the message, a link to the Members tab and Refuse and Accept buttons calling the decision routes. The first decision SHALL resolve it for the other admins ("Accepted by" or "Refused by" <name>). A cancelled request SHALL delete it.

#### Scenario: Two admins

- **WHEN** Alice asks to join Atlas, whose admins are Bob and Carol, and Bob accepts from his tile
- **THEN** Bob's notification disappears and Carol's shows "Accepted by Bob" without buttons

### Requirement: The requester is told the decision

Accepting or refusing SHALL send the requester `team.join_request_answered` with the outcome, never naming the admin; an acceptance SHALL offer "Open the team". The type SHALL need no team permission.

#### Scenario: Refused

- **WHEN** Bob refuses Alice's request to Atlas
- **THEN** Alice is told her request was refused, with no button and no admin name

### Requirement: Decision tiles wait for an answer

An unhandled notification of a decision type SHALL have no close button, SHALL survive "Clear all" and SHALL stay when "View" opens its link. A button calling a domain endpoint SHALL keep the tile when the call fails, with an error toast, and remove it silently on 404 or 403; while a call is in flight the tile's buttons SHALL be disabled.

#### Scenario: Clear all keeps pending decisions

- **GIVEN** Bob holds an information tile and an open join request tile
- **WHEN** he chooses "Clear all"
- **THEN** only the join request tile remains

#### Scenario: Accept fails

- **WHEN** Bob clicks Accept and the endpoint answers 500
- **THEN** an error toast is shown and the tile stays
