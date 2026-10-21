## ADDED Requirements

### Requirement: An explicit local profile deploys the complete manager ingestion path

The documented k3d ingestion profile SHALL use the production Fred chart and the existing factory deployment mechanism to configure original storage, manager orchestration, Knowledge Flow processing and isolated result storage together. It SHALL preserve required instance services and credentials when values are merged. Prerequisites and the application command SHALL have one documented entry point; missing prerequisites SHALL produce an actionable failure without deleting existing data.

The profile SHALL align with Swift's configured `<bucket_name>-documents` bucket and `<document_uid>/input/` and `<document_uid>/output/` roots. The separate `<bucket_name>-objects` bucket SHALL retain its existing generic-object purpose. Raw and derived SHALL describe content roles without introducing new bucket names or requiring production copies. New processing outputs SHALL retain immutable generation-specific keys beneath `output/` and SQL-controlled publication. A conflicting existing storage binding SHALL be refused without silently moving, adopting or deleting data.

#### Scenario: The developer deploys the ingestion profile
- **WHEN** the documented prerequisites and selected profile are applied to a supported dedicated k3d installation
- **THEN** the existing Resources UI can store and process a PDF through manager and the required Knowledge Flow workers
- **AND** every advertised processing profile has a matching worker queue consumer

#### Scenario: A prerequisite is missing
- **WHEN** a required bucket, credential, workload identity or exported processing contract is absent or inconsistent
- **THEN** validation or startup identifies the missing prerequisite without reporting ingestion readiness
- **AND** existing documents and infrastructure are not reset or silently reassigned

#### Scenario: A previous Rust installation uses different storage coordinates
- **WHEN** the Swift-aligned profile is selected against a database bound to different storage coordinates
- **THEN** validation or startup explains the conflicting storage binding
- **AND** the previous data remains unchanged pending an explicit operator migration or reset decision

#### Scenario: A documents bucket contains content outside manager ownership
- **WHEN** inventory, orphan cleanup, generation cleanup or local reset encounters existing Swift content or another installation's objects
- **THEN** absence from manager's catalog does not authorize deleting or adopting those objects
- **AND** deletion requires proven ownership and the applicable document/generation lifecycle state

#### Scenario: Processing is retried in the Swift-aligned layout
- **WHEN** a worker retries or an older generation completes after a newer attempt
- **THEN** its writes cannot overwrite the original or another generation's artifacts
- **AND** only a verified authorized publication changes the visible result

### Requirement: Ingestion workloads receive only their documented storage privileges

The profile SHALL enforce separate original and processing-result storage privileges through distinct application identities. Knowledge Flow SHALL have no direct access to manager originals through any credential available in its pod. The manager API SHALL have no write/delete access to processing results. The manager orchestration worker and frontend SHALL receive no object-store credentials. Infrastructure administrator credentials SHALL NOT be mounted in these application workloads. Vector persistence SHALL use a restricted identity and separate manager index; retained legacy accesses SHALL be explicitly scoped.

The shared documents bucket SHALL NOT be treated as proof of object-level isolation. Provider-specific object and listing permissions SHALL be verified before the profile is accepted. Incompatible legacy maintenance access SHALL be isolated or disabled; an unavailable enforcement mechanism SHALL be reported as an unresolved acceptance condition without silently broadening privileges or changing the selected physical layout.

#### Scenario: Knowledge Flow attempts to bypass manager original access
- **WHEN** a Knowledge Flow workload uses any of its supplied storage credentials to read, list, replace or delete manager originals
- **THEN** the object store refuses the operation
- **AND** the authorized original-read protocol through manager remains usable

#### Scenario: The manager tries to mutate processing output
- **WHEN** the manager API's result-storage identity attempts to write or delete a result
- **THEN** the object store refuses the operation while allowing verification and authorized previews

#### Scenario: The profile is rendered over ordinary instance values
- **WHEN** an operator inspects the resulting pod credential references and storage policies
- **THEN** no inherited administrator credential defeats the documented workload restrictions
- **AND** SQL, identity, authorization, model and observability dependencies retain the required configuration

### Requirement: Deployed processing policy matches the effective workers

The processing contract SHALL be generated from the selected worker implementation and effective configuration, carry verifiable provenance, and be refreshed when either changes. Manager and workers SHALL agree on profiles and queue routing. Validation SHALL reject an explicitly selected stale or mismatched contract before accepting new processing work. Updating the contract SHALL cause affected consumers to reload it through deployment rollout.

#### Scenario: A worker profile changes
- **WHEN** the selected worker image or effective processing profile configuration changes
- **THEN** the operator procedure regenerates the contract and rolls its consumers
- **AND** a prior incompatible contract cannot silently route new work

### Requirement: Operators can reconstruct the persisted result of a PDF ingestion

The deployment documentation SHALL identify original bytes, generated artifacts, the published manifest, vectors and temporary files, including their owners and lifetime. It SHALL explain the configured physical keys and logical document/folder placement without conflating them. Read-only inspection SHALL correlate one document across SQL, object storage, vectors and Temporal without exposing credentials. Success SHALL require the manager's verified publication and the existing authorized download/preview journey.

#### Scenario: A PDF reaches successful publication
- **WHEN** the operator follows the documented journey for one test PDF
- **THEN** the original hash matches the uploaded file and the published manifest identifies the durable outputs and vector generation
- **AND** the operator can distinguish temporary or abandoned output from published content

#### Scenario: A workflow or worker fails
- **WHEN** processing fails or a worker restarts during the test
- **THEN** the original remains intact and the persisted status explains the outcome
- **AND** retry preserves the document identity and does not require uploading the source again

### Requirement: Resource and production-parity claims have bounded evidence

The profile SHALL declare transfer, storage, time and concurrency bounds and account for all simultaneously served worker roles. Its validation record SHALL distinguish measured results from estimates and identify document sizes, counts, profiles and concurrency. Documentation SHALL identify local transport, topology and capacity differences from production. A passing single-document journey SHALL NOT be presented as a scalability or full production-readiness result.

Production storage-parity claims SHALL require evidence for the deployed GCS/S3NS interface and authorization/protection semantics. A successful local S3-compatible-provider test SHALL NOT substitute for that evidence, and missing provider validation SHALL be stated explicitly.

#### Scenario: The operator reviews worker sizing
- **WHEN** reviewing a deployment with multiple worker roles or replicas
- **THEN** the resource explanation includes the combined permitted activities and their temporary-storage budgets
- **AND** any concurrent test report records its actual fixture, deployment and measurement limits
