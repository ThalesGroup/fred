# Platform Access Control Specification

## Purpose

Control platform admission using a configured IdP attribute and administrator-managed user and team exceptions, including bounded demonstration-team enrollment.

## Requirements

### Requirement: Admission policy is deployment-configured and opt-in

The system SHALL accept an enablement switch, a JWT claim path, an acceptance regex and `supportLink` in deployment configuration. The claim path SHALL address nested keys unambiguously. Matching SHALL use the complete string value, or any complete string element in a string array, from a signature-verified human access token. Missing, empty or incompatible values SHALL not match. Invalid regexes, unsafe support URLs and incomplete enabled configuration SHALL be rejected before serving requests. Omitted enablement SHALL preserve existing deployment behavior.

#### Scenario: Configured nested attribute matches

- **WHEN** filtering is active and the verified token's configured nested attribute matches the entire regex
- **THEN** that person is eligible for platform admission without an individual exception

#### Scenario: Attribute does not establish eligibility

- **WHEN** the configured attribute is absent, has an incompatible type, or only contains a partial regex match
- **THEN** the system SHALL require another admission source

#### Scenario: Configuration omitted or invalid

- **WHEN** enablement is omitted
- **THEN** the new admission policy SHALL not change existing behavior
- **WHEN** enablement is true but a required setting or valid regex is missing
- **THEN** startup SHALL fail explicitly

### Requirement: Admission sources are independent of resource permissions

When filtering is active, the system SHALL admit a non-suspended person if their verified attribute matches, they have a current individual exception, or they are a current member of an authorized team, including a Free team. Ordinary public-team visibility SHALL not count as membership. Admission SHALL neither grant a platform role nor extend team or resource permissions. Account suspension and required CGU acceptance SHALL still apply.

#### Scenario: New non-matching person is refused

- **WHEN** a new person has no matching claim, individual exception or eligible membership
- **THEN** normal platform access SHALL return HTTP 403 with `detail="platform_access_denied"`

#### Scenario: One source is removed while another remains

- **WHEN** a person's individual exception is removed but another valid admission source remains
- **THEN** admission SHALL remain available through that other source

#### Scenario: Visibility and admission are different

- **WHEN** a person can view a public authorized team but is not its member
- **THEN** that visibility SHALL not grant platform admission

#### Scenario: Admitted person is suspended or lacks resource permission

- **WHEN** an otherwise eligible person is suspended or requests a resource they cannot access
- **THEN** the existing suspension or resource refusal SHALL remain effective

### Requirement: Platform administrators manage live exceptions

Only people holding the existing platform-management permission SHALL read or modify the platform access administration surface. It SHALL provide paginated individual exception management using Fred's local users, team authorization and Free-team controls, the filtering state, and the effective admission sources with associated team identifiers. Team administrators and team managers SHALL not obtain this authority through their existing roles. Removing an individual exception SHALL not remove an identity or revoke independent team sources.

#### Scenario: Administrator authorizes a Fred user or team

- **WHEN** a platform administrator adds an existing Fred user or authorizes an existing team
- **THEN** eligible users SHALL be admitted on their next request without restart or JWT renewal

#### Scenario: Unauthorized administrative call

- **WHEN** a team administrator, team manager or ordinary person calls an access administration endpoint
- **THEN** the system SHALL refuse the call and leave admission state unchanged

#### Scenario: Administrator sees provenance

- **WHEN** an administrator lists allowed users
- **THEN** individual entries SHALL identify manual or T0 origin and derived entries SHALL identify each authorized or Free team

### Requirement: T0 grandfathering is an explicit fixed snapshot

The system SHALL provide an administrator-triggered preview and one atomic import of existing human users in Fred's database before filtering activation. Known current claim matches SHALL not require individual entries; unknown classifications SHALL be included conservatively so missing profile data does not lock out existing users. T0 entries SHALL be individually removable. Import completion SHALL fix the population; later registrations SHALL not be grandfathered by a retry, restart or upgrade.

#### Scenario: Existing user without a stored attribute

- **WHEN** an administrator imports T0 and an existing Fred human has no reliable attribute classification
- **THEN** that user SHALL receive a removable T0 exception

#### Scenario: Removed entry and later registration stay excluded

- **WHEN** T0 has completed, one imported exception is removed, and another person registers afterward
- **THEN** neither a repeated import request nor restart SHALL restore the removed entry or admit the later registration

#### Scenario: Concurrent imports

- **WHEN** two administrators attempt T0 import concurrently
- **THEN** only one fixed snapshot SHALL commit and the other request SHALL report the completed state

### Requirement: Free-team links admit only their authenticated caller

A platform administrator SHALL be able to enable Free enrollment and obtain an opaque revocable link for one existing non-personal team. A signed-in person otherwise denied by admission filtering SHALL be able to use that link to join that team. A successful enrollment SHALL grant only the existing member relation to the caller, retain CGU and suspension checks, and expose the Free-team admission source in administration. The enrollment surface SHALL not reveal directories, normal product bootstrap or arbitrary private-team data.

#### Scenario: Denied external person joins a Free team

- **WHEN** a non-matching person signs in through a valid Free-team link and meets suspension and CGU requirements
- **THEN** they SHALL become a member of that team and gain admission through that Free-team source

#### Scenario: Link cannot select another person or stronger role

- **WHEN** enrollment requests name another person, another team or an administrative role
- **THEN** the request SHALL not grant that identity, team or role

#### Scenario: Ordinary authorized team stays closed

- **WHEN** an administrator authorizes a team without enabling Free enrollment
- **THEN** its existing joining policy SHALL remain unchanged and denied people SHALL not use its ordinary join endpoint to bypass admission

#### Scenario: Old or disabled link is refused

- **WHEN** a link is invalid, rotated, or belongs to a team whose Free flag was removed or whose registry entry was deleted
- **THEN** enrollment SHALL be refused without granting membership or admission

### Requirement: Team-derived admission follows current state

Admission derived from a team SHALL require both a current authorization or Free flag and current membership. Removing Free SHALL invalidate its enrollment links and its derived admission source, while keeping existing membership and independent admission sources intact. Disabling and later re-enabling Free SHALL not reactivate old links. Revoking team authorization, leaving the team or deleting the team SHALL withdraw the corresponding source on subsequent requests.

#### Scenario: Free is removed

- **WHEN** the administrator removes Free from a person's only eligible team
- **THEN** their next normal platform request SHALL be refused unless another admission source exists

#### Scenario: Membership is removed

- **WHEN** a person leaves or is removed from an authorized or Free team
- **THEN** that team's source SHALL no longer grant admission, including with the same JWT

### Requirement: Admission is enforced at backend boundaries

The same authoritative policy and exception state SHALL govern normal direct and delegated human requests across participating backends and replicas. A workload acting for a person SHALL be checked against the person's current admission, not the workload's claim or service role. Pure service operations SHALL retain existing service authentication and authorization. Admission checks SHALL not be skipped by JWT decoding caches, unavailable stores or eventual membership caches. Shared-state failures SHALL fail closed with HTTP 503, not be presented as a definitive policy denial.

#### Scenario: Direct API or cached token cannot bypass removal

- **WHEN** a person's last exception is removed and they call another backend or replica with an already decoded JWT
- **THEN** the next request SHALL use current admission state and be refused

#### Scenario: Delegated person loses admission

- **WHEN** a workload calls on behalf of a person whose last admission source was withdrawn
- **THEN** the call SHALL be refused even if the workload remains authorized as a service

#### Scenario: Claim-derived delegated eligibility is stale

- **WHEN** a delegated person's only evidence is an expired or incompatible verified attribute observation
- **THEN** that observation SHALL not establish eligibility

#### Scenario: Admission authority unavailable

- **WHEN** configured admission state or required membership checks cannot be read reliably
- **THEN** normal human platform requests SHALL fail closed with HTTP 503

### Requirement: Refusal and enrollment screens remain reachable

The frontend SHALL display a standalone localized platform-access refusal page for `platform_access_denied`, with a contact-support message and the configured `supportLink`. The support link SHALL be available before protected product bootstrap succeeds. Other authentication, CGU, resource-permission and transient service errors SHALL retain their existing handling. The valid Free enrollment route and narrowly scoped self-status/identity and CGU operations SHALL remain reachable to authenticated denied people without admitting normal product access.

#### Scenario: Denied bootstrap displays support

- **WHEN** protected bootstrap or another normal request returns `platform_access_denied`
- **THEN** the browser SHALL display the refusal page without needing a successful protected bootstrap or entering a redirect loop

#### Scenario: Different error remains distinct

- **WHEN** a request returns 401, a CGU refusal, another resource 403 or an admission-authority 503
- **THEN** the frontend SHALL not convert it into the platform-access refusal page

### Requirement: Activation and migration are explicit

Enabling the feature configuration SHALL expose its administration while leaving filtering inactive until an explicit administrator action. Activation SHALL be refused if the acting administrator would be denied by the resulting policy. Existing root bootstrap safeguards SHALL remain intact. Simultaneous activation of the legacy file gate and the new admission feature SHALL be rejected explicitly. Shared admission state, imported entries and membership SHALL survive restarts and temporarily disabling filtering.

#### Scenario: Upgrade does not silently activate filtering

- **WHEN** operators deploy the new feature and its empty admission tables
- **THEN** filtering SHALL remain inactive until an administrator prepares exceptions and explicitly activates it

#### Scenario: Administrator would lock themselves out

- **WHEN** an administrator tries to activate filtering or withdraw their last admission source through access-policy administration
- **THEN** the change SHALL be refused with an actionable explanation

#### Scenario: Conflicting whitelist modes

- **WHEN** deployment configuration enables the new feature while a nonempty legacy file gate is active
- **THEN** startup SHALL refuse the conflicting configuration explicitly
