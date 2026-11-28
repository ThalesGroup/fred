# fred-capability-memory

The `memory` agent capability: short notes an agent instance keeps across the
conversations of its space. The agent remembers a fact, preference or choice
the user stated, and forgets a note on request. Agent editors review and
delete notes from the agent's settings.

The capability reaches the notes only through `RuntimeServices.memory` (a
`MemoryPort`, fred-sdk); the Control Plane owns them and checks every call.

Installing this package registers the capability — the `fred-agents` pod
discovers it at boot through the `fred.capabilities` entry point. Nothing else
to wire.
