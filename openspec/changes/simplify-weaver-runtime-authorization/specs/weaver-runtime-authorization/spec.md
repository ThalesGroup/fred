## Purpose

Restore the existing Custom Assistant creation, configuration and chat behavior for Bob in fredlab within TSN under Weaver authorization. Define the preserved management/runtime contract and the subsequent local-document path without redesigning the working Swift agent or its configuration semantics.

## ADDED Requirements

### Requirement: Custom Assistant retains its managed-instance behavior

Weaver SHALL support creating, listing, reading, editing, enabling/disabling and deleting configured Custom Assistant instances through the existing product flow. A template SHALL remain a runtime-supplied definition; an instance SHALL retain a stable identifier, canonical owning space, source template/runtime and saved configuration. ReBAC changes SHALL NOT require replacing the Custom's agent definition or execution engine. Editing SHALL require the applicable space write permission; use SHALL require the canonical space/template execution conditions. No separate instance permission object SHALL be required.

#### Scenario: Bob creates and reopens a configured Custom
- **WHEN** Bob has the required space/template permissions and saves a Custom Assistant through the existing form
- **THEN** reopening it restores its saved identity, display metadata and configuration
- **AND** execution resolves that instance to the original Custom template and its saved effective tuning

#### Scenario: An instance is disabled
- **WHEN** execution is requested for a disabled instance whose template remains authorized
- **THEN** the instance refuses execution until explicitly enabled through an authorized edit

#### Scenario: The first Custom has no selected tools
- **WHEN** the existing Custom's empty default capability selection and a configured chat model are used
- **THEN** creation, streamed exchange and conversation reopening work without the Python Control Plane or Knowledge Flow API
- **AND** local document retrieval and other specialized agents are not prerequisites for this path

### Requirement: Instance listing reads authorized saved configuration

GET /spaces/{space_id}/agent-instances SHALL require AdmittedUser, space Read on
the active canonical team/personal space and can_use_agent on each saved template_id.
It SHALL return 200 with an array of ManagedAgentInstanceSummary, using list_by_space
and the individual GET's record_to_summary projection. Enabled and disabled records
SHALL retain created_at, agent_instance_id order. Each distinct template SHALL be
checked once per request, bounded by crate::fga::READ_CONCURRENCY, with no cross-request
cache. The read SHALL use no mutation lock or SQL transaction and retain no SQL
connection during FGA calls. It SHALL consult no catalog/runtime, refresh no
FieldSpecs and infer no execution availability from enabled.

#### Scenario: The space has no visible instances
- **WHEN** the authorized space is empty or every saved template is refused
- **THEN** the list returns 200 with []

#### Scenario: Several saved instances are visible
- **WHEN** the list is read after creation or editing, including enabled and disabled instances
- **THEN** each item equals its individual GET projection in stable persisted order
- **AND** deleting an instance removes it from subsequent lists; other spaces and organizations remain isolated
- **AND** catalog/runtime unavailability does not change this saved-state read

#### Scenario: Template checks deny access or fail technically
- **WHEN** a template decision is false
- **THEN** all its instances are omitted without affecting other authorized instances
- **AND** a technical FGA error instead fails the request without a successful empty or partial list
- **AND** SQL errors and projection errors on authorized instances also propagate

#### Scenario: The space is retired or its read permission is revoked
- **WHEN** its canonical lifecycle or permission check refuses the list request
- **THEN** the existing error propagates instead of returning 200 with []

### Requirement: Instance deletion is scoped to space write authority

DELETE /spaces/{space_id}/agent-instances/{agent_instance_id} SHALL require an
admitted user and an active canonical team/personal space with Write. It SHALL
reuse lock_for, authorize_locked and the existing fence before deleting by both
space_id and agent_instance_id, then commit. It SHALL NOT require can_use_agent or
call the catalog/runtime. Only the agent_instance configuration SHALL be deleted;
messages/checkpoints and space purge SHALL remain unchanged. No business FGA tuple
mutation SHALL be added beyond the existing fence's technical revision updates.

#### Scenario: An enabled or disabled instance is removed
- **WHEN** an authorized user deletes an existing instance in that space
- **THEN** the response is 204 without a body and its name becomes reusable there
- **AND** a subsequent authorized GET or second DELETE returns 404

#### Scenario: An instance is absent or belongs to another space
- **WHEN** an authorized user requests its deletion in the given space
- **THEN** the response is 404 and no instance is removed

#### Scenario: Template use is revoked while space Write remains
- **WHEN** the admitted user deletes an instance whose template is no longer usable
- **THEN** deletion still succeeds under the active space's Write permission

#### Scenario: Space access or lifecycle no longer permits deletion
- **WHEN** space rights are revoked or the space is retired before the locked recheck
- **THEN** existing authorization/lifecycle errors refuse deletion and the instance remains

### Requirement: Existing configuration semantics survive the ReBAC replacement

Weaver SHALL preserve the existing agent field/tuning, capability selection, validated capability-configuration envelope and model-selection/routing contracts. It SHALL preserve display metadata, intended-use statement and supported profile recommendations instead of reducing the configuration to a new prompt-only schema. Save-time validation and partial-update semantics SHALL remain effective. Configuration supplied to an edit API SHALL be validated under editing authority; caller-supplied execution fields SHALL NOT replace the trusted saved configuration. Unsupported dependencies SHALL be reported explicitly, not silently removed or replaced by defaults.

#### Scenario: Capability selection distinguishes inheritance and no tools
- **WHEN** an update omits capability selection, sets it to null, or supplies an empty list
- **THEN** the result respectively keeps the stored selection, inherits current template defaults, or selects no capabilities for a selectable template
- **AND** fixed template capabilities cannot be disabled by supplying []

#### Scenario: A supported capability configuration is saved
- **WHEN** its runtime validation accepts the submitted configuration
- **THEN** its versioned configuration envelope survives save/read/runtime resolution without semantic rewriting
- **AND** an unrelated partial update preserves it

#### Scenario: An unavailable capability is selected
- **WHEN** an instance selects a dependency not yet connected in Weaver
- **THEN** saving or executing the affected configuration reports that missing dependency explicitly
- **AND** the system does not silently execute the same instance without its requested tools

#### Scenario: Creation/read increment with no connected dependencies
- **WHEN** an admitted user with space write and canonical template use creates an instance with empty effective capabilities and no profile recommendation
- **THEN** Weaver saves the full pod tuning snapshot with Swift enrollment overrides and returns the saved projection
- **AND** an authorized space-scoped read returns those saved values and enabled/disabled state without rediscovering the template
- **AND** active capability or non-null profile selections return explicit 422 errors until connected

#### Scenario: The space is retired during template discovery
- **WHEN** creation has started discovery but the space is retired before insertion
- **THEN** the existing locked lifecycle/permission recheck refuses the insertion
- **AND** no instance or per-instance authorization tuple is created

#### Scenario: A partial edit preserves omitted data and clears only explicit values
- **WHEN** an authorized PATCH edits an existing instance
- **THEN** it preserves identity, provenance, creation attribution and omitted data, including unknown tuning metadata
- **AND** null metadata leaves it unchanged, while an empty description is explicit
- **AND** omitted tuning values are kept, null/{} clears them, and a nonempty map replaces them with validated known entries
- **AND** a rename alone preserves role/prompt; status enables/disables the same instance
- **AND** a no-op preserves updated_at/updated_by and name collisions return 409 agent_name_conflict

#### Scenario: Editing refreshes fields without resetting the saved tuning
- **WHEN** PATCH touches tuning values or capability settings
- **THEN** only FieldSpecs are refreshed from the saved source's current template, outside SQL
- **AND** tuning-only edits can fall back to saved FieldSpecs on catalog unavailability, never on authorization denial
- **AND** capability edits require the current catalog and reject unconnected active selections in 422, including fixed defaults
- **AND** omitted configuration is preserved when selection is unchanged; values for unselected capabilities are ignored when configuration is supplied
- **AND** an omitted recommendation is preserved, null clears it and a non-null recommendation returns 422 until connected
- **AND** metadata-only edits do not consult discovery or reject untouched unconnected settings; GET reads the saved snapshot

#### Scenario: An edit races with another write or access retirement
- **WHEN** discovery finishes after another instance edit or a space/template access change
- **THEN** PATCH rereads the space-scoped row under the existing mutation lock and applies changes to that current version
- **AND** omitted concurrent changes survive; lifecycle/write/template use are rechecked before the existing fence and UPDATE
- **AND** foreign instances return 404 and a denied/retired scope cannot be written

### Requirement: The existing chat preserves metadata and execution ownership

Control Plane SHALL supply the session index/metadata and execution preparation needed by the existing chat. Runtime SHALL remain the owner of messages, checkpoints, streaming and execution. Preparation SHALL return trusted runtime/history routing and supported chat controls without proxying execution or creating a signed grant. Creation, listing, reopening and renaming SHALL preserve the user's session association. Both preparation and runtime access SHALL verify the applicable person/space/instance association before exposing or reusing conversation context. Instance removal SHALL NOT implicitly erase its message history.

#### Scenario: Bob reopens a conversation
- **WHEN** Bob remains authorized and selects a saved conversation from the existing list
- **THEN** its metadata routes the chat to the correct runtime history and instance
- **AND** a new turn uses the current trusted configuration and current authorization checks

#### Scenario: A session identifier names another association
- **WHEN** a request substitutes a session belonging to another person, space or instance
- **THEN** preparation and runtime access refuse before exposing history or resuming a checkpoint

### Requirement: Weaver has one authorization path

Weaver SHALL replace the scoped Swift execution and document-access path without backward-compatible modes, legacy authorization fallback or data migration. Replacement SHALL preserve authentication, admission, isolation, delegation, credential renewal and run-lifetime guarantees. Missing equivalents SHALL block the affected functionality rather than disable its protection.

#### Scenario: An old startup dependency is unavailable
- **WHEN** Weaver cannot establish canonical admission or authorization prerequisites
- **THEN** it refuses readiness or the affected operation explicitly
- **AND** it does not recreate Swift admission/suspension tables, synchronize an old FGA schema or disable security

### Requirement: Runtime uses the published authorization binding

Runtime SHALL consume the Control Plane's canonical store/model binding read-only, validate compatibility, and use the exact published model for every authorization decision. It SHALL NOT create stores/models, select the latest model implicitly, or fall back to another binding.

#### Scenario: Binding cannot be verified
- **WHEN** the binding is missing, inconsistent, unsupported or unreachable at startup
- **THEN** runtime does not become ready to serve protected execution

### Requirement: Execution context is bound to the authenticated person

Control Plane and runtime SHALL bind execution to the authenticated person or trusted workload delegation and canonical organization, space, instance, template and conversation facts. Browser or model fields SHALL NOT establish identity or broaden authority. Context SHALL carry no credentials or permanent permission snapshot. Missing account/admission enforcement SHALL NOT be treated as approval.

#### Scenario: Bob requests an unrelated instance
- **WHEN** Bob names an instance or conversation outside the verified execution association
- **THEN** execution is refused before model or storage access

#### Scenario: An ordinary bearer asserts another person
- **WHEN** a caller without trusted delegation authority supplies person/run/agent assertions
- **THEN** those assertions do not authorize execution as that person

### Requirement: Execution requires space read and template use

Admission and protected operations SHALL require `can_read(user, execution_space)` and `can_use(execution_space, canonical_template)` together with applicable admission, lifecycle and operation-specific conditions. Service identity or platform governance roles SHALL NOT substitute for the person's content rights. Templates with unavailable dependencies SHALL remain unavailable.

#### Scenario: Bob reads fredlab but the template is disabled
- **WHEN** Bob requests execution in fredlab
- **THEN** template-use refusal prevents execution despite his space read permission

#### Scenario: A template has unavailable dependencies
- **WHEN** activation or execution is requested for that template
- **THEN** the system refuses rather than bypassing dependency enforcement

### Requirement: Revocation is enforced at operation boundaries

Runtime SHALL recheck authorization before each protected operation, including each model invocation and capability access, with no authorization-result cache across operations. Duplicate checks within an operation SHALL be reusable. A refusal SHALL prevent the operation and terminate the run's authority; dependency failures SHALL block access with a distinct technical failure. Neither SHALL become an ordinary tool result that allows the model to bypass the gate. Already authorized operations may finish within the accepted lifetime bound; immediate interruption of previously authorized SSE generation is not promised.

#### Scenario: A tool-free Custom loses access before its next model call
- **WHEN** its next model invocation is requested after effective access revocation
- **THEN** the invocation is refused and the run's delegated authority ends

#### Scenario: Bob loses access between two searches
- **WHEN** the second search is requested after revocation
- **THEN** it performs no protected storage access and the run's delegated authority ends

### Requirement: JWT renewal does not renew authorization

Existing person/service credential renewal and trusted delegation SHALL remain supported independently of permission decisions. Renewing a token SHALL NOT restore revoked rights, extend a terminal run, or trigger retries to bypass authorization refusal. No authorization check per SSE token or per JWT refresh SHALL be required.

#### Scenario: Credentials expire while Bob remains authorized
- **WHEN** an active run needs fresh outgoing credentials
- **THEN** its existing renewal mechanism can obtain them and protected operations still undergo authorization

#### Scenario: Fresh credentials exist after a run terminates
- **WHEN** an outgoing operation is attempted using that run
- **THEN** the operation is refused despite the credentials being unexpired

### Requirement: Document scope includes ancestors without extra ancestor permissions

A document operation SHALL authorize the execution space and derive its space-and-ancestor scope from canonical placement. It SHALL NOT require separate read permissions on those ancestors. Team scope SHALL contain its organization and itself, never descendants or siblings. Project document scope SHALL contain its organization, team and itself; personal scope SHALL contain only itself. User/model restrictions SHALL only narrow scope. This requirement does not add project agent execution support.

#### Scenario: Bob reads fredlab but has no direct read grant on TSN
- **WHEN** the agent searches from fredlab
- **THEN** eligible TSN and fredlab documents are searchable without an additional TSN read check
- **AND** project children, other teams and other organizations are excluded

### Requirement: Retrieval exposes only authoritative published content

Local capabilities SHALL enforce scope in storage queries and verify candidate placement, active lifecycle, search inclusion and published generation/chunk membership against authoritative PostgreSQL facts before exposing content or metadata to external rerankers, models or callers. No OpenFGA document tuples or per-document OpenFGA decisions SHALL be required. Knowledge Flow HTTP APIs SHALL NOT participate in this path. Identifiers and citations SHALL confer no independent access right.

#### Scenario: A deleted document remains in the vector index
- **WHEN** it appears among search candidates
- **THEN** its content, metadata and citation are excluded from exposed results

#### Scenario: A candidate has stale or missing publication provenance
- **WHEN** its generation or chunk cannot be matched to the committed publication
- **THEN** it is excluded without a legacy fallback

#### Scenario: Search inclusion is unconfirmed
- **WHEN** a document is excluded or has a pending inclusion change
- **THEN** it is not exposed by document retrieval until authoritative inclusion is confirmed

#### Scenario: Bob follows an earlier citation after revocation
- **WHEN** a new read operation attempts to retrieve the cited document
- **THEN** it rechecks the current run and document-access conditions before exposing content

### Requirement: Departure has no automatic restoration

Revocation SHALL remove effective access in the applicable scope and end affected
run/delegation authority within five minutes after effective access revocation.
Already-running activity within this bound is acceptable; instantaneous
interruption is not required. The implementation SHALL retain the next-protected-operation checks.
Renewable service credentials SHALL NOT extend authority beyond that bound.
A returning person SHALL undergo ordinary newcomer admission without automatic
restoration of previous access or runs, including when the identity subject is
reused. No reversible suspension feature SHALL be required for this journey.
Runtime/access cleanup SHALL NOT imply unspecified deletion of shared content,
persisted histories or audit evidence. The five-minute bound SHALL be enforced independently of JWT expiration or
service-token renewal.

#### Scenario: Bob returns after departure
- **WHEN** Bob is admitted again after his access was revoked
- **THEN** his former memberships and delegated runs are not automatically restored

#### Scenario: A run has no further protected operations
- **WHEN** revocation occurs during an already-authorized generation
- **THEN** existing activity can finish within the agreed delay
- **AND** the run and its delegated authority cannot remain active beyond that bound

### Requirement: Canonical context enriches logs and product KPIs

Applicable runtime logs and product KPI events SHALL carry canonical organization,
team, project and execution-space identifiers from the resolved context, together
with existing run/session/trace and agent identifiers. Existing performance, cost,
model, tool and outcome details SHALL remain available. Hierarchy dimensions SHALL
be queryable and SHALL NOT be accepted as authoritative from browser/model fields.
Absent hierarchy levels SHALL NOT be fabricated. Concurrent runs SHALL NOT share
or leak context, and terminal events SHALL retain the appropriate attribution.
Telemetry enrichment SHALL NOT expose credentials or change access boundaries.

#### Scenario: A project run is queried by its parent team
- **WHEN** an operator with appropriate telemetry access filters product KPIs by the parent team
- **THEN** events from its project runs are selectable through the canonical team identifier
- **AND** the project identifier supports further filtering

#### Scenario: A fredlab run reads an organization document
- **WHEN** the runtime emits search and model KPI events
- **THEN** execution attribution remains TSN/fredlab with no project
- **AND** source-document placement does not overwrite execution attribution

#### Scenario: Two runs overlap and one fails
- **WHEN** their execution and terminal events are recorded concurrently
- **THEN** each event retains its own verified hierarchy and correlation identifiers

### Requirement: Template authorization covers configured dependencies

Authorization to execute an activated template SHALL cover use of its capabilities
and models attached through trusted effective configuration. Weaver SHALL reuse
the existing capability registry, configuration and model-selection/routing
mechanisms for this journey and SHALL NOT require a separate capability/model
OpenFGA permission catalogue. Activation SHALL check support/configuration of the
declared dependencies; resolution/execution SHALL reject unavailable dependencies.
Selections SHALL remain within the configured set. Capabilities SHALL retain
operation-specific and data-access authorization, and existing non-ReBAC security
restrictions SHALL NOT be silently removed. Unsupported dependencies SHALL NOT
be accepted merely to unblock activation.

#### Scenario: Bob executes a configured document assistant
- **WHEN** Bob passes space/template authorization and the attached local search capability and model are available
- **THEN** the existing mechanisms supply those dependencies without a separate capability/model FGA grant
- **AND** document access still passes the shared Weaver checks

#### Scenario: A requested dependency is outside the binding
- **WHEN** a browser or model requests a capability or model outside the trusted configured set
- **THEN** the request is refused without expanding the binding

#### Scenario: A dependency is missing
- **WHEN** activation or execution encounters a required unsupported or unavailable dependency
- **THEN** it fails explicitly without a blanket allow, legacy fallback or automatic substitution outside the configured set
