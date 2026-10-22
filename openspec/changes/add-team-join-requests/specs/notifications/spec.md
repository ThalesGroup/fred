## ADDED Requirements

### Requirement: Join requests notify the team's current admins

Creating a join request SHALL send a `team.join_requested` notification, with the team as its team, to every user holding `can_administer_members` on it at that time; its action permission SHALL be `can_administer_members`, so losing that right deletes it. The tile SHALL read "<requester> asks to join <team>", show the message if any, link to the team's Members tab and offer Accept and Refuse, each calling the decision endpoint. The first decision SHALL resolve the group `join_request:<request_id>`: the deciding admin's notification disappears and the other admins see "Handled by <name>". A cancelled request SHALL delete the open notifications of its group. When a decision answers 404, the tile SHALL delete its notification.

#### Scenario: Two admins

- **WHEN** Alice asks to join Atlas, whose admins are Bob and Carol, and Bob accepts from his tile
- **THEN** Bob's notification disappears and Carol's shows "Handled by Bob" without buttons

#### Scenario: Editor is not notified

- **WHEN** Alice asks to join Atlas, where Dan is an editor but not an admin
- **THEN** Dan receives no notification

#### Scenario: Admin demoted

- **WHEN** Carol loses her admin role on Atlas while Alice's request is pending
- **THEN** Carol's notification for it is deleted

#### Scenario: Stale tile

- **WHEN** Carol clicks Refuse on a request that Alice already cancelled
- **THEN** the call answers 404 and the tile disappears from Carol's list

### Requirement: The requester is told the decision

Accepting, refusing or accepting anyway a request, and the automatic refusal when its team leaves `on_request`, SHALL send the requester a `team.join_request_answered` notification with outcome `accepted` or `refused`, in group `join_request_outcome:<request_id>`. The type SHALL declare no action permission and SHALL NOT be filtered by team permissions. An `accepted` notification SHALL carry the team, so the requester leaving or being removed from the team, or the team's deletion, deletes it; a `refused` one SHALL carry no team and survive both. The tile SHALL read "Your request to join <team> was accepted" with a link and an "Open the team" button to the team's Agents page, or "Your request to join <team> was refused" with no link or button. It MUST NOT name the deciding admin. Accepting a refused request SHALL delete the requester's refusal notification before sending the acceptance one.

#### Scenario: Accepted

- **WHEN** Bob accepts Alice's request to Atlas
- **THEN** Alice receives "Your request to join Atlas was accepted" whose button opens Atlas's Agents page

#### Scenario: Refused

- **WHEN** Bob refuses Alice's request to Atlas
- **THEN** Alice receives "Your request to join Atlas was refused" with no button and no admin name

#### Scenario: Leaving takes the acceptance, not a refusal

- **GIVEN** Alice holds an old refusal and an acceptance for Atlas
- **WHEN** she leaves Atlas, is removed from it, or Atlas is deleted
- **THEN** her acceptance notification is deleted and her refusal notification stays
