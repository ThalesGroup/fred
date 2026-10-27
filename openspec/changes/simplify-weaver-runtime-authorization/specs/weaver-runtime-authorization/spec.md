## Purpose

Restore the existing Custom Assistant creation, configuration and chat behavior for Bob in fredlab within TSN under Weaver authorization. Define the preserved management/runtime contract and the subsequent local-document path without redesigning the working Swift agent or its configuration semantics.

## ADDED Requirements

### Requirement: Catalog persistence preserves pod ownership

Each capability offering SHALL be identified by `(runtime_id, capability_id)`.
Template capability links SHALL use the same runtime owner and reference an
existing offering of that runtime. Version and public descriptor changes SHALL
update only that offering. A complete successful inventory SHALL replace one pod
atomically; failed discovery SHALL preserve its last successful inventory and
record unreachability separately. Catalog observations SHALL NOT grant permission
or establish execution readiness.

#### Scenario: Two pods share a capability library
- **WHEN** pods A and B declare the same local capability ID at different versions
- **THEN** both offerings coexist and updating A does not modify B
- **AND** a template of A cannot link to an offering present only on B

#### Scenario: Withdrawal differs from discovery failure
- **WHEN** a successful inventory omits a previously declared capability
- **THEN** its last descriptor remains stored with advertised set to false
- **WHEN** discovery fails instead
- **THEN** the last successful inventory and links remain, with the pod marked unreachable

#### Scenario: An inconsistent snapshot is submitted
- **WHEN** a snapshot repeats an identity or links to an undeclared local capability
- **THEN** the whole replacement is refused without partially updating the inventory

### Requirement: Complete pod capability inventory is organization-administered

Configured Agent Pods SHALL advertise all installed tool capabilities, independently
of template pickers, and registered template consumer/default links. The response SHALL
explicitly declare completeness. No agent, model, Application or Knowledge Base
projection SHALL enter this inventory. Configuration descriptions SHALL exclude
values, private connection configuration and credentials.

The Control Plane SHALL expose organization-scoped read and single-pod refresh,
using AdmittedUser, Manage, canonical organization placement and active lifecycle.
It SHALL resolve the pod identity/URL from platform configuration, reject disabled
refresh sources, and grant no implicit access from a platform role. A read SHALL
combine observations/offers/links in a consistent SQL snapshot. A refresh SHALL
perform bounded network discovery outside SQL, recheck authority under the existing
lock/fence, and atomically persist only a complete valid snapshot for that pod.

Observation state and timestamps SHALL remain independent of advertised/withdrawn
status and execution availability. Failed or invalid discovery SHALL preserve the
last inventory and report an explicit failure, including on first contact. Public
contracts SHALL be generated from their backend sources. Catalog refresh SHALL
NOT change instance settings, histories, agent/model permissions or destinations.

#### Scenario: Installed capability without a declared consumer
- **WHEN** the registry has an installed tool capability not exposed by any registered template
- **THEN** the complete inventory contains the offer with no consumer link
- **AND** it is not inferred from the union of template pickers

#### Scenario: Retraction, failure and recovery
- **WHEN** A successfully withdraws an offer, later fails or sends invalid JSON, then recovers
- **THEN** withdrawal is retained separately from the failed observation
- **AND** only a complete valid recovery replaces A's inventory; B and saved instances stay unchanged

#### Scenario: Contradictory inventory
- **WHEN** an inventory repeats an offer/link, names a foreign runtime, has incomplete fields or a dangling link
- **THEN** refresh returns 502 and records unavailability without a partial replacement

#### Scenario: Administrative access
- **WHEN** an admitted active organization manager reads or refreshes
- **THEN** access follows Manage; a member without Manage is refused
- **AND** an unrelated organization, wrong space kind or unknown runtime is not found
- **AND** platform role alone never grants access, and authority lost during discovery prevents writing

### Requirement: Agent model inventory belongs to the platform

The Control Plane SHALL own the agent model inventory, populated only through
compatible discovery APIs at platform-approved sources. Each offer SHALL be
identified by `(source_id, upstream_model_id)`, independently of runtime pods.
Platform authority SHALL own approved destinations and credentials. Discovery
SHALL NOT grant organization permission or prove execution availability in a pod.
Sources without compatible discovery and per-pod manual agent model catalogs
SHALL NOT form part of this target. Knowledge Flow embedding configuration and
document processing SHALL remain outside this model-catalog change.

#### Scenario: Two sources return the same model name
- **WHEN** sources A and B both discover the same upstream model ID
- **THEN** they remain distinct offers and changes to A do not reassign B's saved choices
- **AND** no pod identity or display name replaces the source-qualified key

#### Scenario: Discovery succeeds but inference is unavailable
- **WHEN** the Control Plane discovers a model and a pod lacks the necessary inference access
- **THEN** discovery does not establish permission or readiness to execute that model

#### Scenario: An organization attempts to redirect credentials
- **WHEN** an organization administrator or invocation supplies an unapproved destination
- **THEN** it cannot change the platform-approved catalog/inference association or receive provider credentials

### Requirement: Organization model administration is atomic and authorized

Organization inventory, source refresh and policy read/write SHALL require admission,
active canonical organization placement and Manage through the existing Weaver gate.
Platform roles alone SHALL NOT grant access. Inventory SHALL combine safe platform
observations/offers and only the requesting organization's policy in one consistent
snapshot, followed by admission/authorization recheck. No public projection SHALL
expose credential values/references or internal destination configuration.

Refresh SHALL authorize before discovery, release every SQL connection/transaction
during HTTP, then recheck admission and Manage under the existing locks and FGA fence
before publication in that same transaction. Exact source configuration and latest
refresh token SHALL still constrain publication. A denied completion SHALL NOT
publish either success or failure. Discovery SHALL NOT mutate organization policy.

Policy replacement SHALL use expected revision and atomically persist the permitted
composite keys, explicit nullable default/fallback and audit attribution. Missing
policy SHALL mean revision zero with no permitted offers or implicit choices.
Default/fallback SHALL belong to the same organization's permitted set. New permissions
and changed non-null choices SHALL require known, advertised, chat-qualified offers
from enabled sources with successful observations at their current configuration
revision. Retained unavailable choices SHALL NOT prevent reductions or clearing.
Withdrawal, discovery failure and configuration change SHALL retain diagnostic
references without substitution or automatic reauthorization.

#### Scenario: Admission or Manage is lost during source discovery
- **WHEN** an authorized manager starts discovery and loses admission or Manage before HTTP completes
- **THEN** publication is refused before any observation or offer update, including on discovery failure
- **AND** the last successful snapshot remains intact

#### Scenario: Source refreshes or configurations race
- **WHEN** two refreshes overlap or platform configuration changes during discovery
- **THEN** only the latest claimed token for the exact current configuration can publish
- **AND** other sources and every organization policy remain unchanged

#### Scenario: Organization policy replacements race
- **WHEN** two authorized writes use the same expected policy revision
- **THEN** exactly one commits the next revision and the other conflicts
- **AND** no permitted-set/default/fallback mixture is visible or committed

#### Scenario: A new selection is unknown or no longer eligible
- **WHEN** a policy adds an unknown, withdrawn, non-chat or unknown-chat offer, or changes a choice during failed discovery
- **THEN** the whole replacement is refused and the saved policy remains unchanged
- **AND** an old snapshot from another source revision cannot validate the selection

#### Scenario: A manager reduces permission during an outage
- **GIVEN** a policy retains unavailable X and Y and default X
- **WHEN** the manager removes Y while retaining X, or revokes X and explicitly clears its default
- **THEN** the atomic replacement succeeds without requiring new discovery for the retained choices
- **AND** no automatic fallback or substitute is selected

#### Scenario: Organizations share discovered offers but not decisions
- **WHEN** organization A permits an offer or the platform discovers another offer
- **THEN** organization B's policy is unchanged and new offers remain unpermitted
- **AND** an admitted A manager cannot read or modify B's policy

#### Scenario: An administrator attempts to change source approval
- **WHEN** a caller supplies a destination, credential, qualification or completeness override
- **THEN** it cannot change the platform approval or the discovery destination
- **AND** public model schemas contain only identities, normalized metadata, observations and organization choices

### Requirement: Organization model restrictions cover every selected model

Organization model restrictions SHALL apply to the actual model used for each
invocation, including explicit choices, recommendations, defaults, overrides and
fallbacks. Agent authorization SHALL NOT expand that set. Control Plane
administrative validation SHALL NOT be presented as runtime enforcement; the pod
SHALL enforce the restriction locally at invocation against the complete trusted
context resolved once for that turn. It SHALL NOT refresh turn authority through
additional HTTP/SQL/OpenFGA calls on each invocation, retry or descendant. Rust SHALL NOT proxy inference or implement a second model router.

#### Scenario: A forbidden fallback is selected
- **WHEN** an authorized agent selects a fallback forbidden by its owning organization
- **THEN** the pod refuses that model invocation, regardless of the fallback's routing priority

#### Scenario: Organizations choose different permitted sets
- **WHEN** one organization changes its model restrictions
- **THEN** the other organization's choices are unchanged
- **AND** execution evaluates the canonical owning organization's restrictions

### Requirement: Discovery preserves qualification and authority boundaries

Discovery credentials SHALL be provisioned explicitly for the approved source.
Read-only discovery rights SHOULD be preferred. A credential also granting inference
SHALL require explicit platform acceptance for that source; a distinct secret SHALL
NOT be treated as proof of read-only rights. Pod inference secrets SHALL NOT be
implicitly transferred to Rust.

Mixed inventories SHALL be supported when reliable supported metadata identifies
chat eligibility. Inventory membership SHALL remain separate from eligibility;
missing modality metadata SHALL NOT establish chat capability or withdrawal.
Only a complete successful inventory for the approved visibility scope SHALL
confirm absence. Failed discovery SHALL preserve the last successful inventory
and SHALL NOT trigger disappearance fallback.

Existing permitted selections MAY continue during discovery outage under the
authority resolved at turn admission; new selection writes SHALL wait for successful
refresh. Resolver authorization-read failure SHALL prevent admission of that turn;
the runtime SHALL NOT reuse a previous turn's context. User choices, recommendations, organization defaults
and removal fallback SHALL reference discovered offers, without a separately
administered profile or platform/fallback authorization exemption.

#### Scenario: A mixed inventory changes a model's metadata
- **WHEN** an offer remains listed but no longer establishes chat compatibility
- **THEN** its inventory membership is retained separately from its chat eligibility
- **AND** the change is not treated as confirmed withdrawal

#### Scenario: Discovery rights cannot be isolated
- **WHEN** a provider's discovery credential also permits inference
- **THEN** using it in Rust requires explicit platform acceptance for that source
- **AND** merely creating another credential does not satisfy that decision

Design 5e records the accepted direction and tasks M1-M5 separate delivery scopes.
The accepted M4 arbitration requires local invocation checks against one complete
turn-start resolution. The earlier narrow SQL authority access proposal and
per-invocation authority refreshes are superseded. No runtime enforcement is claimed.


### Requirement: Instance model settings and resolver data use platform offers

Instance APIs SHALL store `recommended_model` as a composite offer key and only
`temperature`, `max_tokens`, `top_p` in `model_options`, within existing tuning JSON.
PATCH omission SHALL preserve; null recommendation SHALL clear; null options SHALL
reset; an options object SHALL replace its three overrides. Structural validation
SHALL reject non-finite numbers, non-positive/non-integer tokens, top_p outside
[0, 1] and unknown options. Known output/context bounds SHALL constrain token
options without implying provider compatibility or inferring absent capabilities.
Changed recommendations SHALL reuse M2 selection validation in the existing locked
write transaction, against canonical space ownership and current policy/catalog.

The existing resolver SHALL preserve authentication, trusted delegation, admission,
space/template authorization and enabled-instance checks. It SHALL read configuration,
policy, sources, offers and connections consistently, exposing revisions, safe facts,
explicit references, permissions, candidate status and diagnostics separately.
Only trusted delegated workloads SHALL receive approved candidate connections;
ordinary instance and administrative projections SHALL contain none. The resolver
SHALL NOT select a model or grant authority reusable across turns. M3 exposes
data only; M4 SHALL bind the trusted response to one admitted turn.

#### Scenario: Options and partial edits
- **WHEN** an editor changes metadata, omits options, clears a recommendation or resets options
- **THEN** unrelated settings and legacy references remain intact
- **AND** descriptive edits and explicit clears remain possible during discovery failure
- **AND** invalid options or an ineligible changed recommendation refuse the complete write

#### Scenario: Source or policy changes race with a recommendation
- **WHEN** a recommendation write competes with policy revocation, publication or source revision change
- **THEN** shared M2 selection validation and existing locks decide against current facts at write time
- **AND** a source snapshot from an older configuration revision cannot admit a new selection

#### Scenario: A personal instance resolves its model context
- **WHEN** a trusted workload resolves an enabled personal-space instance for an admitted person
- **THEN** model policy belongs to the canonical owning organization, not a browser organization parameter
- **AND** all candidate connections come from the same SQL snapshot of platform approvals

#### Scenario: A recommendation becomes unavailable or withdrawn
- **WHEN** discovery fails, an offer is withdrawn, permission is revoked or chat is no longer established
- **THEN** the retained reference and distinct diagnostics remain available
- **AND** discovery failure alone neither changes selection nor triggers fallback
- **AND** permission alone is not proof of local executability; invocation checks remain M4 work

#### Scenario: Legacy profile and existing form
- **WHEN** a pre-M3 instance contains only a legacy profile reference
- **THEN** ordinary reads retain it and the resolver marks explicit re-selection required
- **AND** no name conversion or profile-based resolution occurs
- **AND** the existing form retains its controls and preserves model settings on descriptive saves


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

### Requirement: Agent management UI uses canonical Weaver space contracts

The existing agent page and full configuration form SHALL use generated space
CRUD/catalog contracts in team and personal spaces resolved from the Weaver
context. Management SHALL follow the server's Write decision, without a local role
matrix. Readable lists SHALL remain independent of creation-catalog availability.
Mutation errors SHALL retain input and distinguish authorization, absence, conflict,
validation and transport/server failures. Adjacent unconnected actions SHALL stay
explicitly unavailable without legacy requests; other shared consumers are preserved.

#### Scenario: A reader opens Agents
- **WHEN** the instance list is readable but Write is not allowed
- **THEN** the visible instances remain searchable and sortable
- **AND** no creation catalog or management mutation is requested

#### Scenario: An editor changes only metadata
- **WHEN** an editor opens the saved instance through GET and changes its name or role
- **THEN** PATCH omits unchanged tuning, selection, capability configuration and profile
- **AND** a catalog failure or empty catalog does not discard the stored settings
- **AND** a failed mutation keeps the draft and is not reported as success

#### Scenario: The selected space changes while data or a dialog is pending
- **WHEN** navigation selects another canonical team or personal space
- **THEN** the previous list and open selection are not displayed as belonging to it
- **AND** successful mutations invalidate only their owning space and instance
- **AND** an old delete confirmation cannot initiate deletion from the new context

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

Weaver SHALL preserve the existing agent field/tuning, capability selection, validated capability-configuration envelope and model-selection/routing contracts. It SHALL preserve display metadata, intended-use statement and offer recommendations (with legacy profile strings retained for diagnosis) instead of reducing the configuration to a new prompt-only schema. Save-time validation and partial-update semantics SHALL remain effective. Configuration supplied to an edit API SHALL be validated under editing authority; caller-supplied execution fields SHALL NOT replace the trusted saved configuration. Unsupported dependencies SHALL be reported explicitly, not silently removed or replaced by defaults.

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
- **AND** active capability selections remain explicit 422 errors until connected; legacy profiles are diagnostic-only and new model recommendations use M3 offer keys

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

#### Scenario: M5a registration is retried after a lost response
- **WHEN** an admitted owner repeats registration of the same session ID and instance
- **THEN** the original metadata is returned without a duplicate, changed title/activity or reassignment
- **AND** an ID owned by someone else is hidden as 404, while an incompatible owned association returns 409
- **AND** a successful prior registration can still be recovered after the instance is disabled or removed

#### Scenario: M5a private metadata remains readable after instance removal
- **WHEN** the authenticated owner retains admission and space Read but the instance is removed or disabled
- **THEN** list/read/rename/activity still operate on that owner's metadata and retain its original provenance
- **AND** removal is exposed as agent_deleted and the public history destination remains available while its source route is approved
- **AND** execution preparation refuses the removed/disabled instance; neither messages nor checkpoints are deleted

#### Scenario: M5a metadata mutations cannot change authority
- **WHEN** PATCH supplies owner, space, instance, template or runtime fields
- **THEN** the request is rejected as invalid fields without changing any metadata
- **AND** accepted activity timestamps never regress or exceed the server's current time; title-only edits retain activity order

#### Scenario: M5a public routing is missing or unapproved
- **WHEN** preparation has no enabled configured runtime with an explicit canonical ingress-relative public base
- **THEN** it refuses with a typed unavailable-route/runtime error and never derives a public URL from an internal URL or browser input
- **AND** a failed template discovery returns an explicit error without falling back to another pod or a stale execution preparation

#### Scenario: M5a preparation is product data, not execution authority
- **WHEN** an admitted owner prepares an enabled instance and optionally supplies a registered matching conversation
- **THEN** the response contains public execution/history routes and M2/M3 composite model facts, with no inference connection or credential reference
- **AND** unsupported capability/HITL controls are not advertised; no local profile or additional model policy is constructed
- **AND** every subsequent turn still performs the existing authenticated M4 resolution, including the registered conversation association check
- **AND** runtime retains its local provenance comparison and refuses an old unbound history rather than adopting it

### Requirement: Private history reads use current space rights independently of execution

Runtime history readers SHALL retain authenticated-person admission and use M5a
session metadata with that person's own credential to verify private ownership and
current space Read. They SHALL derive space placement from persisted M4 provenance
and compare session, person, space, instance, template and receiving runtime before
loading conversation content. Browser identifiers SHALL NOT establish authority.
History reads SHALL NOT prepare execution, call the turn resolver, reuse prior-turn
authority, create a run or cache authorization between independent consultations.

#### Scenario: Owner reads after instance removal or disablement
- **WHEN** the owner retains admission and space Read, with matching persisted provenance
- **THEN** messages and checkpoint details remain readable even if the instance is deleted, disabled or its template unusable
- **AND** a bound session with no messages returns an empty list

#### Scenario: Another person or a revoked owner reads history
- **WHEN** a caller names another person's session or no longer has space Read
- **THEN** no content is loaded and the same unavailable response hides the conversation
- **AND** history indexes omit refused candidates through the same shared guard

#### Scenario: Provenance is absent or inconsistent
- **WHEN** local provenance is missing or disagrees with the Control Plane session or receiving runtime
- **THEN** consultation refuses without adopting, rewriting or repairing the history
- **AND** a substituted request identifier cannot broaden access

#### Scenario: History authority or storage fails
- **WHEN** credentials, Control Plane or storage cannot complete the check or read
- **THEN** an explicit error returns no content, never a successful empty or partial history
- **AND** an independent retry performs fresh authorization

#### Scenario: Workload attempts a private history read
- **WHEN** a service identity or an asserted person without their own credential requests history
- **THEN** access is refused without creating a run or inventing delegated M5a credentials
- **AND** the existing M4 invocation, retry and descendant authority rules remain unchanged

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

Turn admission SHALL require `can_read(user, execution_space)` and `can_use(execution_space, canonical_template)` together with applicable admission and lifecycle conditions. Subsequent operations SHALL enforce the resolved turn context locally and retain their resource-specific conditions. Service identity or platform governance roles SHALL NOT substitute for the person's content rights. Templates with unavailable dependencies SHALL remain unavailable.

#### Scenario: Bob reads fredlab but the template is disabled
- **WHEN** Bob requests execution in fredlab
- **THEN** template-use refusal prevents execution despite his space read permission

#### Scenario: A template has unavailable dependencies
- **WHEN** activation or execution is requested for that template
- **THEN** the system refuses rather than bypassing dependency enforcement

### Requirement: Turn authority is resolved once and enforced locally

Runtime SHALL obtain one complete authorized context through the existing Control
Plane resolver call at the start of each turn. All model invocations, retries,
structured calls, reused clients and descendants SHALL enforce that context locally
without additional HTTP, SQL or OpenFGA requests to refresh turn authority. They
SHALL NOT broaden its scope or treat a child/retry as a fresh authorization.
Missing or refused admission SHALL prevent the turn; no previous-turn context
SHALL substitute. M4 SHALL NOT introduce the previously proposed SQL authority
view, role or connection. Initial inference support SHALL be OpenAI-compatible;
unconnected providers SHALL fail explicitly.

Revocation, person/instance/template/source decommissioning and model withdrawal
after admission SHALL be observed at the next turn. An admitted turn MAY finish.
No five-minute revocation deadline or periodic authority refresh SHALL be imposed
for these changes. Explicit cancellation, terminal-run checks, execution limits
and resource-specific storage/service checks SHALL remain effective. A local
refusal SHALL NOT become a bypassable model/tool result.

#### Scenario: A tool-free Custom loses access before its next model call
- **WHEN** access is revoked after turn admission and another model call or retry occurs in that turn
- **THEN** it may proceed within the original resolved context without an additional authority read
- **AND** the next turn resolves current rights and refuses access as applicable

#### Scenario: One turn performs many model calls
- **WHEN** ten LLM calls, retries or descendant steps execute in one admitted turn
- **THEN** they share one complete turn-start resolution and make no extra authority-refresh requests
- **AND** a model or child target outside that context is refused locally

#### Scenario: Admission fails for the next turn
- **WHEN** the resolver refuses or cannot establish the next turn's complete authority
- **THEN** no inference starts and the previous turn's context is not reused

#### Scenario: A resource check refuses access during a turn
- **WHEN** a document or receiving service's own check refuses an operation
- **THEN** the turn context does not override that refusal or expand resource scope

### Requirement: JWT renewal does not renew authorization

Existing person/service credential renewal and trusted delegation SHALL remain supported independently of permission decisions. Renewing a token SHALL NOT broaden the admitted turn context, authorize a later turn, extend a terminal run, or trigger retries to bypass a refusal. No authorization check per SSE token or per JWT refresh SHALL be required.

#### Scenario: Credentials expire while Bob remains authorized
- **WHEN** an active run needs fresh outgoing credentials
- **THEN** its existing renewal mechanism can obtain them without refreshing or broadening the admitted turn context; local and resource-specific checks still apply

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
- **THEN** it enforces the admitted turn scope and current document-access facts before exposing content; a new turn requires fresh resolution

### Requirement: Departure has no automatic restoration

Revocation SHALL remove effective access in the applicable scope for subsequent
turn admissions. An already admitted turn MAY finish using its fixed context under
the accepted next-turn detection policy. The former five-minute active-run
revocation guarantee is superseded for these changes. Token renewal SHALL NOT
broaden that context, authorize a later turn or revive terminal authority.
A returning person SHALL undergo ordinary newcomer admission without automatic
restoration of previous access or runs, including when the identity subject is
reused. No reversible suspension feature SHALL be required for this journey.
Explicit cancellation, terminal cleanup and execution limits SHALL remain distinct.
Runtime/access cleanup SHALL NOT imply deletion of shared content, persisted
histories or audit evidence.

#### Scenario: Bob returns after departure
- **WHEN** Bob is admitted again after his access was revoked
- **THEN** his former memberships and delegated runs are not automatically restored

#### Scenario: A run has no further protected operations
- **WHEN** revocation occurs during an already-authorized generation
- **THEN** the admitted turn may finish subject to explicit cancellation and ordinary execution limits
- **AND** its context cannot authorize a later turn; no five-minute revocation guarantee is claimed

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
and models attached through trusted effective configuration, subject to the owning
organization's model restrictions. It SHALL NOT independently permit a model.
Weaver SHALL reuse the existing capability registry, configuration and model-selection/routing
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


### Requirement: Discovered reasoning preserves the Swift on/off journey

For mixed-capability model sources, Control Plane SHALL retain the boolean
`capabilities.reasoning` reported by discovery. Missing or invalid values SHALL
remain unknown; no configured model list or name-based aptitude inference is used.
Organization Manage SHALL control reasoning activation through the existing model
policy and revision boundary, initially off and only for permitted, selectable,
reasoning-capable offers. Removing model permission SHALL remove that activation.

The existing Models switch and chat Normal/Reasoning menu SHALL consume these
facts. The pod SHALL send `reasoning_effort: high` only when the actual selected
model is capable, organization-enabled and explicitly requested for this question.
Otherwise it SHALL omit the parameter. The admitted turn snapshot SHALL govern
calls, retries and descendants, without further authority reads; transport guards
SHALL reject changes to the effective setting. Native Mistral reasoning replay
SHALL retain both invocation and transport guards.

#### Scenario: Discovery, organization ceiling and question choice agree
- **WHEN** a discovered reasoning-capable model is permitted and reasoning-enabled
  and the user chooses reasoning for the question
- **THEN** the existing chat control is offered and the model receives high effort
- **AND** another model's permission or reasoning activation cannot authorize it

#### Scenario: No inference or implicit activation
- **WHEN** capability metadata is absent/false, organization activation is off,
  or the user does not explicitly request reasoning
- **THEN** the model request contains no reasoning effort
- **AND** removing permission and re-adding it does not restore reasoning activation
