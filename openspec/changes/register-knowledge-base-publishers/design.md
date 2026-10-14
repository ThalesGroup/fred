## Context

See proposal.md for the motivation. Today `publish_definition`
(`knowledge_bases/service.py`) admits a service identity (`is_service_agent`, or the
`local-dev` client when security is off), checks that the declaration falls under the
prefix the request claims (`prefix_covers`), and the store binds that prefix to the first
client that publishes under it (a row keyed by the prefix, no rebinding path).

## Goals / Non-Goals

**Goals:** deny by default; the operator, not the first caller, decides which client owns
which prefix; one gate that works with any OIDC provider.

**Non-Goals:** what a published pod may write (one client per definition, `KNOWLEDGE-BASE.md`
§4); revoking definitions already stored for a client that will not be listed; a way to
move a prefix to another client (the store's existing refusal stands).

## Decisions

**Operator registration in configuration, not a new IdP role.** A dedicated role would keep
trust on first use between Knowledge Bases and need mapping in every provider (Keycloak,
Entra, ZITADEL...). A registered `client_id` uses only `azp`, which every provider issues,
and the prefix is assigned at registration. It is also how Fred already admits the other
contributed components: applications (`application_sources`) and agent pods
(`runtime_catalog_sources`).

**Where it lives: `knowledge_bases.publishers`** in the Control Plane configuration, next to
`run_max_attempts`, the section for "what Fred decides about running a Knowledge Base".
Each entry is `{client_id, prefix}`. A client may hold several entries; a prefix appears
once, and no registered prefix covers another (refused at startup, so one name is never
publishable by two clients).

**The check, in order:** service identity (unchanged); client registered; request prefix
equals the registered one; declaration under it (`prefix_covers`, unchanged). Every refusal
is `KnowledgeBaseClientMismatch` (403) with a message naming the client and the setting.

**The store binding stays.** With registration it records what the configuration already
decided and keeps refusing a second client under a bound prefix. Deleting it would be a
separate change: a prefix moved to another client in configuration is still refused by the
store, as today.

**`local-dev` stays admitted as a service identity** where security is off, but is not
exempt from registration: Fred's local configuration (`configuration.yaml`) lists it.

## Risks / Trade-offs

- [Breaking at upgrade: an unlisted Knowledge Base fails its next `publish`] → migration
  note with `operations` impact, listing the clients before upgrading; the 403 names the
  setting.
- [A definition stored before the upgrade by a client that will not be listed stays in the
  catalog] → the note asks operators to review Admin > Features > Knowledge Bases; nothing
  reaches a team without enablement.
- [Adding a Knowledge Base now needs a Control Plane configuration change] → the same step
  applications and agent pods already require; it is the point of the change.

## Migration Plan

Before upgrading, list each Knowledge Base client and its prefix under
`applications.control-plane-backend.configuration.knowledge_bases.publishers` in the fred
chart values. Rollback: `helm rollback` restores that revision's own values and works as
is; deploying the previous chart with the new values fails its values schema until
`knowledge_bases.publishers` is removed (the previous backend would ignore the key).
