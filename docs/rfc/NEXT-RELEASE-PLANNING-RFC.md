# Next Release Planning RFC

## Purpose

This document keeps a lightweight record of business topics planned for the
next release.

It is intentionally short and product-oriented:

- capture the intended behavior
- preserve the business rationale
- avoid turning early planning into implementation detail too soon

Detailed API, UI, permission, and migration work should later move into the
relevant backlog and design documents.

GitHub issues are not a good long-term format for epics and cross-cutting
product themes. This RFC therefore acts as the durable release-oriented view:

- group related topics under a few stable product themes
- preserve intent even when the original GitHub tickets are removed or merged
- keep detailed delivery slicing out of this document

## Topic Map by Theme

## Teams and Spaces

### Teams independent from Keycloak groups

Move the team model away from Keycloak-group-backed ownership so teams become a
first-class product concept with cleaner membership, permissions, and personal
space handling.

### Platform admin visibility and limits on non-member teams

#### Intent

A platform admin must not automatically get full product visibility into a team
 they do not belong to.

For a team where the platform admin is not a member, the platform admin must
not be able to:

- see that team's Lumis area
- see that team's Resources area
- see that team's Apps area

In product terms, those tabs should not be available for non-member teams.

#### Temporary allowed actions before a dedicated team admin UI exists

Until a dedicated platform-admin team management UI exists, platform admins may
still:

- manage team members
- update team settings
- view the team itself, including its core metadata

This includes being able to read the team's name, description, banner, and
similar identity/settings fields even when the team is private.

#### Business intent

The goal is to keep a clear distinction between:

- platform administration powers
- membership-based access to team-owned product spaces

Being a platform admin should allow operating the platform and maintaining team
configuration, but it should not silently grant access to all team content and
workspaces.

### Safe team member removal

#### Intent

Removing a member from a team must become a deliberate and safe product
operation rather than a simple directory update.

#### Expected behavior

The product should support:

- validating the removal before it is executed
- making explicit what checks must pass before a member can be removed
- defining the lifecycle of that member's team conversations after removal

#### Business intent

This topic is important because team membership removal has direct consequences
for access, ownership, continuity, and retained conversation history.

The product must make sure that removing a member does not create silent data
access problems, ambiguous conversation ownership, or inconsistent post-removal
behavior.

### Team avatar

Add team avatar support.

### Storage limits per space

Introduce storage limits per space, with separate quotas for personal and team
spaces.

### Clear team role precedence in the UI

Ensure team role display in the UI reflects the highest effective role for a
user when multiple relations coexist.

## Context Enrichment

### Team context

#### Intent

Each team should be able to define a shared team context that can enrich the
behavior of its Lumis.

#### Expected behavior

The product should support:

- creating and storing a team context
- exposing a team-context field in team settings
- allowing Lumis to use that team context
- allowing users to enable or disable whether a Lumi takes the team context
  into account

#### Business intent

The goal is to give teams a lightweight shared layer of guidance and identity
that can improve Lumi behavior without requiring users to repeat the same
context in every interaction.

This capability should remain controllable, so teams and users can decide when
team context should shape Lumi behavior and when it should stay out of the
interaction.

### Conversation profile

#### Intent

Each user should be able to define a conversation profile that can enrich how
Lumis interact with them across conversations.

#### Expected behavior

The product should support:

- creating and storing a conversation profile
- exposing a conversation-profile field in the user profile
- allowing Lumis to use that conversation profile
- allowing users to enable or disable whether a Lumi takes the conversation
  profile into account

#### Business intent

The goal is to give users a lightweight personal layer of interaction guidance
that follows them across Lumis, without forcing them to restate the same
preferences or framing in every conversation.

### Resource mention with @ in chat

Introduce an @-mention interaction in chat so users can point Lumis to specific
resources as part of a conversation, and allow Lumis to take those pointed
resources into account as explicit conversation inputs. This theme also
includes secure resource search to support @-mention discovery across resource
names, folders, and files.

## Lumi Product Evolution

### Lumi blueprint concept

#### Intent

The product should introduce a backend concept of Lumi blueprint or Lumi schema
to represent a reusable Lumi model that can be used as-is.

#### Expected behavior

The first step should support:

- defining a Lumi blueprint concept in the backend
- using a blueprint directly as a ready-to-use Lumi model
- providing a first "Knowledge Manager" blueprint with its expected form and
  input structure

#### Business intent

The goal is to make Lumi creation more structured and repeatable by introducing
reusable product-level models instead of treating every Lumi as a fully custom
configuration from the start.

The first version should validate this approach with a concrete and useful
blueprint before expanding the catalog of Lumi models.

### Dashboard snapshot generation

Allow a Lumi to generate a fixed dashboard view from a query and publish that
snapshot as an app artifact.

### App concept on top of Fred

Longer-term direction.

Introduce an explicit app concept so teams can manage and expose application
experiences built on top of Fred, with a clear product model for how apps are
created, governed, surfaced, and scoped.

## Marketplace and Distribution

### Agent marketplace and community sharing

Longer-term direction.

#### Intent

Users should be able to publish one of their Lumis to a global marketplace so
that other users can discover it and start using it outside the Lumi's original
team.

#### Expected behavior

When a Lumi is shared to the marketplace:

- other users can chat with it
- other users cannot read its internal settings
- other users cannot edit its configuration

Using a shared Lumi should create a user-facing experience that remains scoped
to the adopter's personal space first.

For the first version, when a user adopts or uses a shared Lumi:

- that Lumi is visible only in the user's personal space
- cross-team sharing behavior is not part of the initial scope

#### Business intent

The goal is to enable safe reuse of useful Lumis across the wider community
without exposing authoring details or turning shared Lumis into globally
editable assets.

The first release should validate the marketplace value at the personal-space
level before extending the model to team-level sharing. This theme includes the
core publish action itself, the associated UI entry points, and the underlying
data-model evolution needed to let a Lumi be used outside its source team.

## Resource Experience and Ingestion

### Internal RAG filesystem awareness

#### Intent

The internal RAG capabilities should gain awareness of the underlying file
system structure.

#### Expected behavior

The first step should support a filesystem-awareness capability equivalent to a
directory listing or "LS" behavior in the backend.

#### Business intent

The goal is to let Lumis reason better about available internal knowledge
sources by understanding how files and directories are organized, instead of
only consuming isolated retrieved content.

This should improve grounding and navigation within internal knowledge spaces
without yet requiring a broader file-management experience.

### Resource upload scalability

Revisit the resource file upload model so it remains viable under high
concurrency and larger user volume.

### Drive-style resource navigation

Introduce a drive-style navigation experience for resources, including tree
navigation and in-app markdown document viewing.

### Better source citation navigation

Improve how source citations are presented and navigated so users can move more
easily between a Lumi answer and the supporting source material.

### Production-ready connectors

Evolve the connector model so connectors can be operated safely in production,
including team-scoped instantiation, visibility on synced content, secure sync
status, and reliable synchronization behavior across replicated deployments.

### Team-scoped processors

Allow processors to be scoped to a team so custom processing capabilities can
be limited to the teams they are intended for.

### Explicit processor selection at upload time

Allow users and APIs to choose which processor should handle a document during
upload and processing, instead of relying only on implicit file-type inference.

## Chat and HITL Experience

### Chat dataviz rendering

Allow Lumis to render supporting data visualizations directly in chat responses,
with the ability for users to download the generated chart as a PNG.

### Chat widget integration

Introduce richer interactive widgets in chat, such as confirmation dialogs,
document viewers, and choice dialogs, with room for additional widget types
later.

### File preview in chat

Allow generated files to be previewed directly in chat before the user decides
whether to download them.

### Rich copy from chat messages

Improve chat message copy behavior so Lumi responses paste cleanly into email
and common office tools, especially for structured content such as tables.

## Governance and Responsible AI

### C3 production readiness: stability, scalability, and security

Foundational production priority. This theme must remain visible even while the
main delivery focus stays on robustness fixes and rapid convergence toward the
agentic-pod target.

This topic covers the production-readiness baseline for the platform, including
load handling, controlled access, endpoint security, privacy and compliance
requirements, and broader operational risk analysis.

Benchmarks, diagnostics, reviews, and hardening outcomes should progressively
refine this theme over time.

### Terms of Use acceptance gating

Require users to review and accept the current Terms of Use before accessing
the platform, including on first login and whenever the terms are updated.

### Responsible AI default guidance

Make responsible-AI guidance part of the default product experience, including
default team resources and baseline Lumi behavior that checks requests against
those governance materials.

## Platform Hardening and Architecture

### Consistent identity propagation for downstream calls

Make identity propagation explicit and consistent for backend calls from the UI
layer to downstream services, especially Knowledge Flow, so authenticated and
local-only behaviors are clearly separated.

### Store persistence hardening

Review and harden store persistence methods so frontend-supplied payloads
cannot overwrite immutable fields.

### Modular backend dependencies

Make backend dependencies explicit and modular so optional storage backends do
not break unrelated deployments.

### Ephemeral file processing

Keep transient file conversions and intermediate artifacts out of durable local
storage so runtime pods remain lightweight and do not accumulate avoidable
filesystem state.

### Async vector search execution

Move vector search execution to native async paths so retrieval-heavy flows do
not keep paying the cost of synchronous backend calls.

### Remove sync/async bridging in agent flows

Continue removing sync-to-async bridging patterns from agent and tool
execution paths so async request handling stays reliable, non-blocking, and
predictable across the platform.

### Consistent permission-driven UI authorization

Make UI authorization decisions rely on one consistent permission model so
feature visibility, enabled states, and request payloads follow the same source
of truth across the product.
