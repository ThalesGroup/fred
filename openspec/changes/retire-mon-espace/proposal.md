## Why

The unused “Mon espace” personal file area adds a fourth resource root, backend path handling, and SDK template behavior to an already fragmented filesystem model. Retiring it is a first, reviewable step toward the filesystem consolidation tracked in [#2328](https://github.com/ThalesGroup/fred/issues/2328).

## What Changes

- **BREAKING** Remove the “Mon espace” tab and its personal-file statistics and actions from Team Resources.
- **BREAKING** Stop exposing or accepting `/teams/{team_id}/users/{uid}` as a filesystem area in Knowledge Flow, including synthetic directory listings, stat, search, and writes. Existing stored objects remain intact pending a separate retention or migration decision.
- **BREAKING** Remove the personal-file helper from the SDK workspace filesystem contract and the personal template fallback; resolve templates from the agent's own files and then team-shared files.
- Keep the distinct `/teams/{team_id}/agents/{agent_id}/users/{uid}` area, team-shared files, agent configuration assets, and the `/fs` MCP/API surface used by them. MCP filesystem retirement is a separate lot.
- Update active product and authoring documentation and focused tests to describe only supported roots.

## Capabilities

### New Capabilities

- `team-resource-spaces`: Supported filesystem roots and template lookup after retirement of the team-level personal area.

### Modified Capabilities

None. There is no existing main OpenSpec capability for these legacy resource roots.

## Impact

Team Resources frontend and feature-flag wording; Knowledge Flow scoped filesystem routing and provenance; fred-sdk authoring contract; fred-runtime workspace adapter; related tests and active filesystem documentation. No object-store deletion or bucket migration is part of this change.
