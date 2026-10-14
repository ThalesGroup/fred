## MODIFIED Requirements

### Requirement: The agent card shows its marketplace state in a bottom bar

The team agent card SHALL show a marketplace state bar only when publication is enabled for a public team outside the personal space and the agent has a state visible to the viewer. A never-published agent, a hidden state, or a Removed state that the viewer cannot see MUST NOT render the bar, its background, or reserved space. Editors SHALL still find Publish in the card's more menu. Visible bars SHALL be pinned to the card's bottom edge and built from the same component as the marketplace card's Like/Import bar:
- **Published:** the like count and the import count.
- **Modified, not republished:** a warning-coloured state, with the counters kept, saying the marketplace still shows the previous version.
- **Removed:** a state that opens a popover with the reason, the date, the platform admin's reason message if any, and a "Hide" button.

Members who are not editors SHALL see only the Published state; Modified and Removed SHALL be visible to editors and the team admin only.

#### Scenario: Not published bar per role

- **WHEN** a team that can publish shows an agent that has never been published
- **THEN** neither an editor nor a member sees a marketplace bar or empty band below the card, and editors find Publish in the card's more menu

#### Scenario: Hidden state has no bar

- **WHEN** a publication state was hidden or a viewer cannot see a Removed state
- **THEN** the agent card has no marketplace bar or reserved space

#### Scenario: Team that cannot publish

- **WHEN** publication is disabled for the team, the team is private, or it is the personal space
- **THEN** no card of the Agents page shows the bar

#### Scenario: Member sees only Published

- **WHEN** a member who is not an editor views a modified published agent
- **THEN** the bar shows Published with its counters, without the modified state
