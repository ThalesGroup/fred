## Purpose

Lets a team member choose, for one conversation, which of the team's enabled
models answers and whether it reasons, from a single composer control.

## ADDED Requirements

### Requirement: Members can read the selectable models for an agent

The members-readable effective-chat-model read SHALL return the models a member
may choose for that agent instance: chat models served by the instance's own
pod, allowed by the platform for the team (`can_use`), and enabled by the team.
Each SHALL carry a choice key (profile id), model identity, display name,
whether its reasoning is enabled platform-wide, and the team's reasoning
default for it. The read SHALL also say whether the choice is locked by a
higher level (platform binding or pod per-agent override). It SHALL NOT reveal
which level produced the recommendation. Any team member SHALL be allowed to
read it.

#### Scenario: Plain member opens a chat

- **GIVEN** models A and B allowed and enabled, model D allowed but disabled by
  the team, and model C allowed but not served by the agent's pod
- **WHEN** a plain member's chat page reads the effective chat model
- **THEN** it receives the recommended model plus A and B as selectable, not C or D

#### Scenario: Choice locked by the platform binding

- **WHEN** a platform binding is in force
- **THEN** the read reports the choice as locked and the composer offers no model rows

#### Scenario: Pod unreachable

- **WHEN** the agent's pod cannot be reached
- **THEN** the read returns no model and no selectable models, without error

### Requirement: The model choice lasts for the conversation only

The composer SHALL start every new conversation on the agent's recommended
model. A picked model SHALL be kept in the browser session for that
conversation only. It SHALL be sent with each of its turns and SHALL NOT be
stored server-side. Picking the recommended model SHALL clear the choice.

#### Scenario: New conversation

- **GIVEN** a user who picked model B in a previous conversation
- **WHEN** they start a new conversation with the same agent
- **THEN** the composer shows the recommended model and sends no choice

#### Scenario: Reload keeps the choice

- **WHEN** the user picked B and reloads the page in the same tab
- **THEN** the composer still shows B and the next turn carries B

### Requirement: A stale choice falls back visibly

When the selectable models no longer contain the conversation's chosen model
(disabled by the team, revoked by the platform, or no longer served by the
pod), the composer SHALL drop the choice and show the recommended model. It
SHALL display a notice naming the model that is no longer available. A choice
the pod ignores at turn time SHALL still produce an answer from the next level.

The same check SHALL run when the member switches to another conversation
whose stored choice the current list does not offer.

#### Scenario: Switching to a conversation whose choice is gone

- **GIVEN** conversation 2 stored chosen model B, and B was disabled since
- **WHEN** the member switches from conversation 1 to conversation 2
- **THEN** conversation 2 opens on the recommended model with a notice that B
  is no longer available

#### Scenario: Team disables the model mid-conversation

- **GIVEN** a conversation on chosen model B
- **WHEN** the team disables B and the page refreshes the selectable models
- **THEN** the composer switches to the recommended model and shows a notice
  that B is no longer available

### Requirement: Admin changes made elsewhere reach an open chat

The chat page SHALL re-read the selectable models when it mounts, when the
browser window regains focus and when the member opens another conversation,
so a team or platform change made in another browser applies without a page
reload. A mount or focus read SHALL be skipped when the last read is less than
30 seconds old. A plain re-render SHALL NOT trigger a read.

#### Scenario: Admin disables a model while a member's chat is open

- **GIVEN** a member's chat is open on chosen model B in another tab
- **WHEN** a team admin disables B and the member returns to the chat tab
- **THEN** the page re-reads the selectable models, and the composer switches
  to the recommended model with a notice that B is no longer available

#### Scenario: Quick tab switching

- **GIVEN** the selectable models were read 5 seconds ago
- **WHEN** the browser window regains focus
- **THEN** the page does not read them again

#### Scenario: Opening another conversation

- **WHEN** the member opens another conversation of the same agent
- **THEN** the page re-reads the selectable models before the next send

### Requirement: Reasoning follows the chosen model and the team default

The composer SHALL show the reasoning on/off row only when the chosen model's
reasoning is enabled platform-wide. The row SHALL start in the team's reasoning
default for that model, when a conversation starts and when the user switches
to that model. While the row is shown, the composer SHALL send an explicit
reasoning value on every turn. When the row is hidden, it SHALL send none. No
effort level SHALL be offered.

#### Scenario: Team default on

- **WHEN** a new conversation starts on a model whose team reasoning default is on
- **THEN** the row is shown ON and the first turn carries reasoning true

#### Scenario: Switching to a model with team default off

- **WHEN** the user switches to a reasoning-enabled model whose team default is off
- **THEN** the row is shown OFF and the next turn carries reasoning false

### Requirement: One compact composer control

The model choice and the reasoning row SHALL live in one composer control that
shows the current model. It SHALL list the selectable models and, when
available, the reasoning row. A locked choice, or a single selectable model
without a reasoning row, SHALL render as read-only text.

#### Scenario: Single model with reasoning

- **GIVEN** one selectable model whose reasoning is enabled
- **WHEN** the user opens the control
- **THEN** it shows that model as the only, selected row and the reasoning row
