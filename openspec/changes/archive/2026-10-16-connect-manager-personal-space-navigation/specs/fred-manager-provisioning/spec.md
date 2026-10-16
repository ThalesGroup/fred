## ADDED Requirements

### Requirement: Personal space opens in the person's organization

Fred SHALL provide its existing personal-space navigation entry using manager
authority, with at most one personal space in the person's unique organization.
No separate creation button, organization selector or redesigned screen SHALL
be introduced. Personal-space identity SHALL come from its returned UUID and
personal owner, never a synthesized Python identifier.

#### Scenario: Priya opens her personal space after import
- **WHEN** Priya accepts the active terms after demo provisioning and has explicit personal-space creation eligibility and activates
  the existing personal-space entry in Demo
- **THEN** Fred opens her personal space, creating it if absent, and shows it
  through the existing selected-space detail and personal navigation presentation
- **AND** she retains navigation to fredlab with her admin, editor and analyst roles
- **AND** merely logging in, accepting terms or listing spaces creates no space

#### Scenario: Root without organization membership
- **WHEN** a platform-only root opens Home after bootstrap
- **THEN** the empty-membership view and authorized provisioning remain available
- **AND** no personal space, organization membership or content access is created

### Requirement: Repeated personal-space opening preserves current authority

`POST /fred-manager/v1/me/personal-space` SHALL require personal admission and
current read authority on the person's server-resolved organization. A supplied
organization identifier SHALL match that context. Creation SHALL additionally
require an explicit OpenFGA entitlement; organization membership alone SHALL NOT
provide it. It SHALL return 201 with a
new private space, or 200 with the same existing space when the caller currently
can read it. Reuse SHALL NOT write grants, repair revoked roles or replace an
inaccessible existing space. Creation SHALL retain the private member/editor
grants, no parent inheritance and the organization's revocation authority.
Concurrent opens SHALL create at most one committed space for that person and
organization. Dependency failure SHALL not be reported as successful opening.

#### Scenario: Repeat visit, reload and concurrent opening
- **WHEN** the same admitted person opens their personal space again, including
  two simultaneous requests within one organization
- **THEN** successful responses identify the same committed UUID
- **AND** only its first creation writes initial roles; reuse writes none

#### Scenario: Revoked roles remain revoked
- **WHEN** an administrator removes personal editor permission but leaves read access
- **THEN** reopening returns the space without restoring editor permission
- **WHEN** personal read access or organization read access is removed before the
  waiting opening request is authorized
- **THEN** opening is refused without restoring a role or creating a replacement

#### Scenario: Creation eligibility is absent or revoked
- **WHEN** a person without a personal space lacks its creation entitlement
- **THEN** opening cannot create the space or its initial roles
- **WHEN** the creation entitlement is revoked after a space exists
- **THEN** that revocation alone neither deletes the space nor changes its roles
- **AND** reuse still requires current organization and personal read authority

#### Scenario: Account changes during opening
- **WHEN** an opening request finishes after its originating account has changed
- **THEN** its completion does not select a space in the new context
- **AND** a failed opening exposes an error without fabricated success or silent retry

#### Scenario: Membership refresh is pending, failed or stale
- **WHEN** opening succeeds but the membership response has not confirmed the returned UUID
- **THEN** navigation retains the previous selection until the response confirms it
- **AND** failure or a response lacking the UUID shows an error and permits another explicit action

### Requirement: Memberships identify their managing organization

Each `/fred-manager/v1/me/spaces` item SHALL expose `organization_id` from its
canonical placement. Personal spaces SHALL retain no parent and a search path
containing only themselves. The organization field SHALL NOT imply inherited
permissions or an extension of personal content scope.

#### Scenario: Personal spaces remain private within each organization
- **WHEN** two people in distinct organizations list their spaces
- **THEN** each response is limited to the caller's organization and permissions
- **AND** neither personal path contains the organization or another space

### Requirement: Personal creation eligibility is explicit

The organization-only direct role `personal_space_creator` SHALL grant only
`can_create_personal_space`, without inheritance or content access. Organization
administrators SHALL manage it through existing role endpoints; bundles SHALL
use their existing role declarations. Its grant SHALL require direct organization
content membership, and the last such role SHALL not be removed while it remains.

#### Scenario: Eligibility is withheld or revoked
- **WHEN** an organization member lacks the creation role and has no personal space
- **THEN** opening a personal space is refused without writes
- **AND** removing that role from a person with an existing readable personal space does not prevent reuse

### Requirement: Personal eligibility model upgrades preserve existing data

When schema synchronization is enabled, startup SHALL upgrade only the exact
published predecessor model in the existing store and atomically publish its new
SQL model pointer. Ordinary loads and imports SHALL not publish models. Unknown
models SHALL be refused without resetting spaces or grants.

#### Scenario: Publication fails or overlaps
- **WHEN** two initializers run or SQL publication fails after the model POST
- **THEN** successful initializers converge on one pinned model
- **AND** failure leaves the previous SQL pointer usable for retry and preserves tuples
