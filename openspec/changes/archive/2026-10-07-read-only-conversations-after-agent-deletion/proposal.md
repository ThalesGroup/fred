## Why

Deleting a managed agent leaves its conversations in the session list, but their history loader still depends on execution preparation for that agent. Users can see an empty thread and execution controls for an instance that no longer exists. Preserve those conversations for consultation and make their execution state explicitly read-only.

Tracked by [GitHub issue #2992](https://github.com/ThalesGroup/fred/issues/2992).

## What Changes

- Resolve history access from the existing session metadata and its captured runtime, independently of `prepare-execution` and the current agent catalog.
- Extend the existing session-detail response with typed history-access and agent-deletion information. Keep runtime message content at the runtime boundary.
- Append the exact `(deleted)` suffix to the agent label in affected conversations and show a localized notice that the agent was deleted and the conversation is read-only. Preserve history, traces, existing attachments, title management and conversation deletion under their current permissions.
- Block new messages, commands, retries, HITL answers/skips, continuation/restart, uploads and execution-context changes for a deleted-agent conversation. Hide the action that starts a fresh conversation with the deleted instance.
- Distinguish confirmed agent deletion from loading failures and runtime outages. Display unavailable history explicitly when its runtime cannot be resolved or reached.
- Preserve live-agent behavior, history caching, stale-response guards and session navigation. Refresh the conversation state after agent deletion through the existing query cache invalidation.

## Capabilities

### New Capabilities

- `managed-conversations`: Durable access to managed conversation history and the execution availability of a conversation after its agent is deleted. The current spec inventory has no session/history lifecycle capability; chat navigation and agent-question specs cover separate interactions.

### Modified Capabilities

None. The conversation lifecycle gates whether existing HITL and interrupted-execution interactions can run; their runtime contracts do not change.

## Impact

Control Plane session-detail schema/service/API and focused tests; generated OpenAPI and frontend client; managed chat hooks/page/thread and attachment drawer as needed; existing query enhancements, sidebar/history navigation tests and English/French translations; existing product-contract and component-UX documentation; one operator migration note.

No database migration, dependency, configuration change, soft deletion, history proxy, alternate-agent reassignment or broader conversation-ownership redesign. Already admitted turns are outside this slice. Simon approved implementation on 2026-10-07 with the `(deleted)` label refinement.
