## Purpose

Defines how a Knowledge Base handler reaches its run's library in Fred without
supplying values the SDK or the platform already own.

## ADDED Requirements

### Requirement: A run's library client from the run alone

The SDK SHALL let a handler obtain a document client for its run's library from
the run context alone. That client SHALL write into the context's `library_id`,
authenticate as the pod, and use the configuration the pod was started with. A
handler SHALL NOT have to load the pod configuration, name the library, or name
a document source to publish.

#### Scenario: Handler publishes with the run context only
- **WHEN** a handler opens a client for its run and publishes `guides/a.md`
- **THEN** the document is written into the run context's library, under the pod's identity

#### Scenario: Configuration read once per process
- **WHEN** a pod serves several runs, each opening a client for its run
- **THEN** the pod configuration is read once, not once per run

### Requirement: Own-store Knowledge Bases are told plainly

When the pod configuration has no Knowledge Flow URL, opening a run's library
client SHALL fail at once with an error stating that this pod is configured
without Knowledge Flow, and SHALL make no HTTP call.

#### Scenario: No Knowledge Flow configured
- **WHEN** a handler of a pod without `knowledge_base.knowledge_flow_url` opens a client for its run
- **THEN** it receives an error naming the missing key, before any request

### Requirement: Document source chosen by the platform

A document client SHALL send a document source tag only when its caller gave
one explicitly. Otherwise it SHALL omit the field, so Knowledge Flow applies
the default source of its own deployment.

#### Scenario: No source tag given
- **WHEN** a client opened for a run publishes a document
- **THEN** the write carries no `source_tag` field

#### Scenario: Explicit source tag kept
- **WHEN** a client constructed with `source_tag="archive"` publishes a document
- **THEN** the write carries `source_tag=archive`
