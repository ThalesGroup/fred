## Why

A team that builds a good agent cannot hand it to another team: today the only way is to rebuild it by hand. The existing same-team "Duplicate" also silently loses configuration files (the ppt-filler template), because it is rebuilt in the browser without them. Tracked in #2949. This is also the base for a later agent marketplace.

Copying an agent raises a question every capability has to answer: which of its settings can leave the place where the agent lives? A library selection, a resource folder or an uploaded template belong to the team that owns the agent. A tone, a page limit or an option flag do not. Today nothing in a capability says which is which.

This change introduces that distinction once, in a form that does not depend on what the "place" is:
- **scope:** the place an agent lives in and whose items its settings may point to. Today a scope is a team or a personal space. Projects and organisations are expected next. They may all become kinds of a common "workspace"; that model is still to be discussed with the team and is not decided here.
- **scope-private setting:** a setting that points to an item owned by the scope (a library, a folder, a document, a file). It never leaves the scope.
- **public setting:** every other setting. It travels with the agent.

Because capabilities classify their settings against "the scope" and not against "the team", the same classification will hold when projects or organisations become scopes. No capability will need to be revisited.

## What Changes

- **"Copy to…" on the agent card.** A new entry in the agent card's "more" menu opens a team picker. The user selects one or more destination teams they edit, or their personal space.
- **Shared team picker.** The picker is the one already used to copy prompts (`ImportPromptDialog`), moved to shared components and made generic. It now shows each team's readiness:
  - A team where the agent template is not enabled is greyed out, with "Agent template not enabled".
  - A team that lacks some of the agent's capabilities shows a warning icon and a short label. A tooltip lists the missing capabilities.
  - When at least one listed team lacks capabilities, a short paragraph above the list explains the consequence. The copy will not have every ability, but data such as the instructions stays intact.
  - An info icon next to the title opens a tooltip that explains what a copy carries and what it does not.
- **Capabilities classify their settings as scope-private or public.** Each capability marks its scope-private settings. A test fails when a setting that looks like a reference to an item is neither marked scope-private nor explicitly declared public, so a new capability cannot forget.
- **Each capability prepares its own copy.** A new capability operation returns the capability's configuration ready for another scope:
  - public settings are kept;
  - scope-private settings go back to their default value, and the capability stays enabled;
  - configuration files are recreated in the destination, as if an editor had uploaded them there.
  The central server never needs to know any capability's settings.
- **Server-side copy.** The control plane gains two endpoints:
  - a readiness preview per destination team;
  - a copy to several teams at once, with one result per team.
- **Name.** The agent's name is kept when it is free in the destination team. On a conflict it gets a numbered suffix, like prompt imports.
- **Duplicate goes through the copy.** The existing "Duplicate" now uses the same server copy within the same scope, so scope-private settings and configuration files are kept. It still lets the user choose the name. The browser-side rebuild is deleted.
- **Audit.** An audit event `agent.copied` records the source, the destination and the author. No provenance field is stored on the agent.
- **Help Center.** The fr and en pages explain copying an agent.

## Capabilities

### New Capabilities

- `agent-copy`: copying an agent's configuration to another scope (today a team or the personal space) and duplicating it within its scope. Covers permissions, destination readiness, the scope-private / public classification of capability settings, configuration files, naming, and what is never copied.

### Modified Capabilities

None. Prompt copying keeps its behaviour; only its dialog component moves.

## Impact

- **Capability SDK and runtime:**
  - a way for a capability to mark its settings scope-private or public;
  - a capability operation that prepares its configuration for another scope;
  - document-access, ppt-filler and the MCP server options with bound libraries are classified.
  - This is an addition to the runtime contract, nothing changes in it. Capabilities served by a pod built with an older SDK are reported as missing when copied.
- **Control plane:**
  - new endpoints for the copy preview and for the copy;
  - an audit event;
  - "Duplicate" moves to the server copy;
  - entries in `authz-endpoint-matrix.yaml`.
- **Frontend:**
  - the team picker becomes a shared component;
  - the agent card's "Copy to…" entry;
  - "Duplicate" calls the server copy, and its browser-side rebuild is deleted;
  - fr and en strings, regenerated API client.
- **Docs:**
  - `CONTROL-PLANE-PRODUCT-CONTRACT.md` and `RUNTIME-EXECUTION-CONTRACT.md` §8 dated entries;
  - `capabilities/AUTHORING.md` and the `add-fred-capability` skill;
  - Help Center fr and en;
  - a migration note per PR.
- **No database change.**
- **Delivery:** three PRs, each reviewable on its own: capability SDK and runtime, then control plane, then frontend and Help Center.
