## ADDED Requirements

### Requirement: Authorized resource browsing in the provisioned space journey

After selecting a personal, team or project space, Fred SHALL expose its existing Resources navigation and read folders and document metadata from control-plane using its generated contract. It SHALL retain the existing shared presentation and SHALL NOT mount control-plane, knowledge-flow, ingestion or conversation consumers. Organization context SHALL remain implicit and personal spaces SHALL use manager identifiers.

#### Scenario: Priya browses personal and collective resources
- **WHEN** admitted Priya opens her personal space or fredlab and then Resources
- **THEN** the UI lists only that space's root folders and documents
- **AND** opening a folder and using its breadcrumb or Back lists the corresponding parent contents
- **AND** an empty successful response shows the existing empty-folder message

#### Scenario: Document pagination
- **WHEN** a folder contains more documents than one UI page
- **THEN** Next and Previous traverse the name/id cursor pages without duplicates or omissions for unchanged data
- **AND** navigation to another folder or space resets pagination and never displays the previous scope's data
- **AND** the UI does not invent a total count or fetch the whole document collection

#### Scenario: Refusal, failure and revalidation
- **WHEN** current authorization or a list request fails, including when revisiting cached resources after revocation
- **THEN** the UI hides cached rows and distinguishes denied access from unavailable service and successful emptiness
- **AND** a retry reissues the current list requests

### Requirement: Folder filters belong to the authorized space

Manager folder and document listing SHALL enforce current personal admission, unique organization context and space read permission. A supplied parent/folder identifier SHALL belong to the requested space; a missing or foreign folder SHALL return 404 rather than a successful empty list. Admin and organization owner roles alone SHALL NOT grant content access; local members and effective editors/analysts SHALL retain their existing read semantics.

#### Scenario: Filter outside the requested space
- **WHEN** a reader supplies a nonexistent folder or a folder belonging to another space to either list endpoint
- **THEN** the endpoint returns 404 without exposing folder contents

#### Scenario: Direct API refusal and current grants
- **WHEN** a person without content read authority requests a list, including an organization's administrator or a reader whose grant has been revoked
- **THEN** the endpoint refuses the request and returns no rows
- **AND** an authorized content reader or editor still obtains only the requested space and folder's metadata
