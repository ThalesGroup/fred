## Why

Starting another conversation with the current agent requires leaving the chat, opening Agents, and finding the same agent again. A direct action in the conversation header removes that detour while keeping the user's existing session available in the sidebar.

Tracked by [GitHub issue #2873](https://github.com/ThalesGroup/fred/issues/2873).

## What Changes

- Add a new-conversation icon button, with an accessible name and a tooltip, at the right of the managed chat header for an existing conversation.
- Open the existing empty chat state for the same team and agent; create a session only when the user first sends a message.
- Use the existing spectrum-border visual language with a subdued, static resting state. Animate only on deliberate hover or keyboard focus and respect reduced-motion preferences.
- Add the English and French label used by the tooltip and the accessible name.
- Show the agent's icon, name, and role above the greeting of every empty conversation, so the user can see which agent they are about to talk to (the header's agent name is easy to miss).
- Use the lighter `outline-muted` token for every outlined `IconButton` border.

## Capabilities

### New Capabilities

- `managed-chat-navigation`: Starting a fresh conversation with the current managed agent directly from an open conversation.

### Modified Capabilities

None.

## Impact

- Frontend managed chat page, its styles and focused tests, the shared `IconButton` outlined border, English and French translations, and the chat UX component document.
- No backend API, data model, or new dependency.
