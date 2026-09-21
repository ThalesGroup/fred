# Proposal

## Why

Deep agents and their native subagents need a shared, conversation-scoped place to exchange working files. The current checkpoint-backed filesystem is internal to the agent graph and cannot provide a replica-safe storage surface to capability code or future human-facing workflows such as #2706.

## What Changes

- Give every Deep agent conversation a text-only, read/write `/scratchpad/` shared live by the parent agent and all native subagents.
- Store conversation files in Fred Runtime's object storage so they remain available across turns and runtime replicas until the conversation's recovery window expires.
- Mount Deep's internal artifacts at `/.deep/` using the same storage substrate while preventing model-originated writes to that namespace.
- Pass one composite backend to the Deep agent and its native subagents, with unmatched paths rejected.
- Expose scratchpad operations to trusted runtime and capability code through a typed `ConversationScratchpadPort`; do not add a Knowledge Flow or public scratchpad API.
- Enforce separate soft safety quotas for `/scratchpad/` and `/.deep/`, with code defaults that deployments can override, explicit failures, and bounded overshoot possible only during cross-replica concurrent mutations.
- Extend conversation erasure to remove both stored namespaces after the existing recovery window.
- Treat the scratchpad and composite-backend portions of #2751 and #2752 as one implementation slice; corpus, attachment, and skill mounts remain separate future work.

## Capabilities

### New Capabilities

- `deep-agent-conversation-filesystem`: Defines the standard conversation-scoped filesystem shared by a Deep agent, its native subagents, and trusted capability code, including namespace permissions, persistence, quotas, isolation, and lifecycle.

### Modified Capabilities

None. The related `deep-agent-runtime` capability is still an in-flight change rather than a durable capability under `openspec/specs/`; this change is a follow-on contract and must be reconciled with that pending delta before either is archived.

## Impact

- Fred Runtime will construct a conversation-scoped filesystem and pass a composite Deep-agent backend to both the parent and native subagents.
- `fred-core`'s existing `BaseFilesystem` remains the object-storage abstraction for this slice; small backward-compatible changes are allowed, while broader store-abstraction consolidation is deferred.
- Runtime service contracts gain a typed scratchpad port for trusted capability/backend access.
- Fred Runtime gains one configured object-storage bucket. Conversation prefixes and feature subdirectories are code-owned rather than separately configurable.
- Conversation deletion/recovery handling must include the new stored objects.
- Existing Deep filesystem-tool guards must recognize the standard runtime-provided filesystem surface without exposing unsupported tools such as `execute`.
- No Knowledge Flow service, M2M authentication flow, public API, binary-file support, or UI editor is introduced.
