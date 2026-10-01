## Purpose

Let users begin another conversation with the same managed agent directly from the conversation they are viewing.

## ADDED Requirements

### Requirement: Start a fresh conversation with the current agent
The managed chat SHALL offer a new-conversation action when an existing conversation is open. Activating it SHALL show an empty conversation for the same team and agent without modifying or deleting the previous conversation.

#### Scenario: Start from an existing conversation
- **WHEN** a user activates the new-conversation action while viewing a conversation with an agent
- **THEN** the chat shows the empty composer for that same agent, and the previous conversation remains available in the session list

#### Scenario: Create a session on first message
- **WHEN** a user activates the action and has not yet sent a message in the new conversation
- **THEN** the system has not created a new session
- **WHEN** the user sends the first message
- **THEN** the message belongs to a new session for the same team and agent

### Requirement: Name the agent in an empty conversation
An empty managed conversation SHALL show the agent's icon, name, and role above the greeting, however the conversation was started. Until the first message creates a session, it SHALL NOT show the conversation header; an existing session with no messages keeps its header.

#### Scenario: Empty conversation
- **WHEN** a user opens an empty conversation with an agent, from the header action, the Agents page, or Home
- **THEN** the agent's icon, name, and role appear above the greeting, and the conversation header is hidden

#### Scenario: Existing session with no messages
- **WHEN** a user opens an existing conversation whose history is empty or failed to load
- **THEN** the conversation header stays visible with its title and new-conversation action

### Requirement: Keep the action discoverable without continuous motion
The action SHALL be an icon button with an accessible name and a tooltip, SHALL support keyboard activation, and use the existing spectrum treatment only during deliberate interaction. It SHALL have no continuous animation at rest and SHALL respect reduced-motion preferences.

#### Scenario: Conversation at rest
- **WHEN** a user reads an open conversation without interacting with the action
- **THEN** the action remains identifiable and its gradient does not move

#### Scenario: Hover or keyboard focus
- **WHEN** a user hovers over or focuses the action with the keyboard
- **THEN** the action shows the spectrum treatment and remains legible in light and dark themes
- **WHEN** the user prefers reduced motion
- **THEN** the spectrum treatment remains static

#### Scenario: Narrow header
- **WHEN** the managed chat header has limited width
- **THEN** the action remains usable without obscuring the conversation title or agent identity
