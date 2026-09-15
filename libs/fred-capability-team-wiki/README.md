# fred-capability-team-wiki

The `team_wiki` agent capability: read access to the calling team's wiki, the
shared knowledge base its members and its agents build together.

Design and rationale: `docs/swift/rfc/TEAM-WIKI-RFC.md`.

Installing this package registers the capability — the `fred-agents` pod
discovers it at boot through the `fred.capabilities` entry point. Nothing else
to wire.
