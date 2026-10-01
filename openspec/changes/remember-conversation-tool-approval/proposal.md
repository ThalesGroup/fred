## Why

Repeated approval prompts for the same tool interrupt a managed conversation even after the person has decided to trust that tool for this conversation. The approval UI also uses a different color and layout from agent questions.

## What Changes

- Add an "Approve for this conversation" action to managed tool-approval prompts. It approves the pending call and remembers the names of the gated tools shown in that prompt for the signed-in user, agent instance, and conversation.
- Automatically answer later approval prompts only when every gated tool in the prompt has a remembered grant. Keep the runtime's existing pause, authorization, and single-use resume path for every call.
- Persist grants in browser local storage across reloads and browser restarts. A different conversation, user, or agent instance gets no grant.
- Render Accept, Reject, and the conversation action as neutral choices in one vertical list, matching agent-question choices.

Tracked by [#2857](https://github.com/ThalesGroup/fred/issues/2857) on the existing HITL branch and draft PR.

## Capabilities

### New Capabilities

- `conversation-tool-approval`: scoped, remembered approval for tools in a managed conversation.

### Modified Capabilities

None.

## Impact

Managed-chat HITL card, conversation state and SSE resume handling, browser local storage, frontend tests, and the compact UX contract. No runtime API, database migration, or change to the approval policy is required.
