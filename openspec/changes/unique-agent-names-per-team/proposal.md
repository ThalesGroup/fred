## Why

Two agents of one team, or of one personal space, can share a name today, so they cannot be told apart in the agent list, the chat header or the KPIs. Nothing prevents it: `agent_instance.display_name` has no unique index and no service check, and the copy feature left uniqueness out of scope. Tracked in #3042.

## What Changes

- An agent name is unique within its team or personal space. The comparison ignores case and surrounding spaces, so "Assistant RH" and " assistant rh " collide. Names stay free across teams.
- The server trims the name on create, rename and duplicate.
- Creating, renaming or duplicating under a taken name is refused with a 409 that carries a stable `code` (`agent_name_conflict`). The agent form and the duplicate dialog show the message on the name field.
- Copying to another team keeps the existing `<name>_imported-<n>` rule, now compared the same way. A platform import renames a conflicting agent with the same rule instead of failing.
- A database migration renames existing duplicates, keeping the oldest agent's name and giving the others `<name> (2)`, `<name> (3)`, and so on, then adds a unique index on the team and the normalised name.

## Capabilities

### New Capabilities
- `agent-names`: uniqueness of agent names within a team or personal space, and how conflicts are refused or resolved.

### Modified Capabilities
None. The `agent-copy` naming rule (in the completed `copy-agent-across-teams` change) keeps its wording; only the name comparison it relies on is defined here.

## Impact

- Control plane:
  - an Alembic migration (rename duplicates, then a unique index on `team_id, lower(display_name)`, names being stored trimmed);
  - the agent instance store (conflict error);
  - `product/service.py` (enroll, update);
  - `product/agent_copy.py` (normalised comparison, duplicate check);
  - `import_export/importer.py` (rename on conflict).
- Frontend: `AgentFormModal` and `DuplicateAgentDialog` show the conflict on the name field. `AgentCopyResult` gains `error_code`, so the OpenAPI client is regenerated.
- Docs:
  - `CONTROL-PLANE-PRODUCT-CONTRACT.md` (`display_name` rule and the 409 code);
  - a migration note with impact `minor` (a new Alembic revision; the rename is automatic, and the note gives a read-only query listing the affected names).
