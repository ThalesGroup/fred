## Context

See `proposal.md` for motivation. `ManagedChatPage` already has a right-side header slot, and `useManagedChat.startNewConversation()` clears the current `session` query parameter. The hook resets session state on that transition; the first send creates a new session. Agent cards already use a paused spectrum-border mixin for conversation actions.

## Goals / Non-Goals

**Goals:** Keep the current team and agent route, reuse the existing session transition, and make the action visually quiet while the user reads.

**Non-Goals:** Change session creation, agent selection, or backend APIs.

## Decisions

- Put an explicitly labelled button in `ManagedChatPage`'s `topBarRight` and invoke `chat.startNewConversation()`. A link to the same route could leave the page mounted with no reliable session-state transition; the existing hook owns that transition.
- Show the button only while a session is bound. The empty chat already represents a new conversation, so a second action there would be redundant.
- Use the shared `Button` atom and spectrum-border mixin. Keep a neutral outline at rest, reveal the brand border on hover and `:focus-visible`, and stop rotation for `prefers-reduced-motion: reduce`. This follows the AgentCard conversation affordance while avoiding ambient motion in the reading view.
- Add a concise localized label. Reserve action space and let the title truncate at narrow widths; retain the agent name's own row.

## Risks / Trade-offs

- An active response can be abandoned by a session switch. The hook already aborts in-flight work on a session change; a focused page test will verify this path and that the previous session remains accessible.
- Existing CSS Module button specificity can override the border style. Reuse the AgentCard override pattern and verify light/dark, narrow-width, focus, and reduced-motion states during review.
