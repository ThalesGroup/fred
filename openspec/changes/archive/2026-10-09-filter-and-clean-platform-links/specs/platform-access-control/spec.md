## ADDED Requirements

### Requirement: Administrators filter invitation history by lifecycle status

Platform administrators SHALL be able to filter one team's complete invitation history by All, Active, Revoked, Expired or Suspended. All SHALL be the default. Results and pagination totals SHALL reflect the selected status across the entire history, not only loaded rows. Revoked SHALL take precedence over Expired, which SHALL take precedence over Suspended; unrevoked, unexpired links SHALL be Active when Link access is enabled and Suspended otherwise. Changing the filter SHALL start at the first page and SHALL NOT display rows from the previous filter as current results. Filtering SHALL NOT change validity, membership, counters or access settings. The history table SHALL have a bounded fixed height with internal row scrolling, while its header, pagination and surrounding controls remain visible.

#### Scenario: Filter beyond the first page

- **WHEN** an administrator selects Expired and matching links exist beyond the previously loaded page
- **THEN** the result pages and total SHALL include all and only expired links for the selected team

#### Scenario: Revoked link also expires

- **WHEN** an expired link has been revoked
- **THEN** it SHALL appear under Revoked and All, not under Expired

#### Scenario: Link access is disabled

- **WHEN** a team's Link access is disabled
- **THEN** its unrevoked, unexpired links SHALL appear under Suspended rather than Active

### Requirement: Administrators delete obsolete invitation history explicitly

Only platform administrators SHALL permanently delete a team's revoked or expired invitation records. The administration surface SHALL offer one bulk cleanup action with an explicit confirmation identifying the team, eligible count and loss of link notes and counters. Eligibility SHALL include the entire selected team's history independently of the displayed filter or page and SHALL be checked using server time at execution. The action SHALL preserve active links, valid suspended links, other teams' links, memberships, admission exceptions and team settings. Deletion SHALL be atomic and return the actual deleted count; repeating it with no eligible records SHALL succeed with zero. Deleted URLs SHALL remain invalid. Cleanup SHALL be available when Link access is disabled. The UI SHALL disable cleanup when no eligible records are known, hide stale history during refresh, and refresh totals/results after success. Cancellation and failed deletion SHALL NOT announce success. Audit records SHALL identify the actor, team and deleted count without reusable tokens or visitor identities.

#### Scenario: Confirm cleanup from a filtered page

- **WHEN** an administrator confirms cleanup while displaying Active links or a later history page
- **THEN** all revoked or expired records for that team SHALL be deleted, including records outside the displayed results
- **AND** currently valid links and existing team members SHALL remain unchanged

#### Scenario: Preserve a suspended invitation

- **WHEN** cleanup runs while Link access is disabled and an invitation remains unrevoked and unexpired
- **THEN** that invitation SHALL remain recoverable and resume when Link access is enabled

#### Scenario: A link expires during confirmation

- **WHEN** an invitation reaches its expiry before cleanup executes
- **THEN** server-time eligibility SHALL include it and the response SHALL report the actual deleted count

#### Scenario: Cancel or fail cleanup

- **WHEN** the administrator cancels confirmation or the deletion transaction fails
- **THEN** no records SHALL be removed and no success SHALL be announced

#### Scenario: Ordinary team manager attempts cleanup

- **WHEN** a person without platform-management permission requests cleanup
- **THEN** the request SHALL be refused without removing history or changing admission
