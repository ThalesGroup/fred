## Purpose

Defines how Fred provides its user directory from Postgres when the Keycloak Admin API is not available.

## ADDED Requirements

### Requirement: The directory source is explicit

`security.user_directory` SHALL accept `keycloak` (default) and `local`. With `local`, no code path SHALL call the Keycloak Admin API, and the Keycloak admin client factory SHALL return its disabled marker without parsing the realm URL.

#### Scenario: Local directory never calls Keycloak

- **GIVEN** `user_directory: local`
- **WHEN** any user listing, search, lookup, count, import or role grant runs
- **THEN** no request is sent to a Keycloak Admin API

### Requirement: People are recorded when they authenticate

With `local`, an authenticated request from a person SHALL upsert that person's identity snapshot (id, username, email, first name, last name, last seen time) into the shared `users` table. Workload identities (service agents, delegation callers, client-credentials tokens) SHALL NOT be recorded. Writes SHALL be throttled per person, and a failed write SHALL be logged and SHALL NOT fail the request.

#### Scenario: First sign-in

- **GIVEN** a person who never signed in
- **WHEN** they call any authenticated control-plane endpoint
- **THEN** a `users` row with their id, username, email and names exists afterwards

#### Scenario: Service identity

- **GIVEN** a workload token carrying the `service_agent` role
- **WHEN** it calls an authenticated endpoint
- **THEN** no `users` row is created for it

#### Scenario: Store unavailable

- **GIVEN** the snapshot write fails
- **WHEN** a person calls an endpoint they are allowed to use
- **THEN** the request succeeds and a warning is logged

### Requirement: Directory reads are served from Postgres

With `local`, user listing, search, id-to-summary lookup, single-user details and the user count SHALL be served from the `users` table and SHALL return the same response shapes as the Keycloak directory. Ids unknown to the table SHALL keep the existing id-only fallback.

#### Scenario: Search a colleague

- **GIVEN** a person who has signed in before
- **WHEN** a team admin searches for part of their username or email
- **THEN** the person appears in the results with their names and email

#### Scenario: Unknown member id

- **GIVEN** a team member id absent from the `users` table
- **WHEN** team members are displayed
- **THEN** the member is returned with its id only, as today

### Requirement: Username resolution for declarative import uses Postgres

With `local`, bulk and single username resolution used by the `users.json` import SHALL be served from the `users` table. A username absent from the table SHALL be reported as unresolved exactly as the Keycloak path reports a missing username.

#### Scenario: Import after first sign-in

- **GIVEN** `alice` signed in once
- **WHEN** an import bundle grants a team role to `alice`
- **THEN** the grant is applied to her user id

#### Scenario: Import before first sign-in

- **GIVEN** `bob` never signed in
- **WHEN** an import bundle names `bob`
- **THEN** `bob` is reported as unresolved and no grant is written for him

### Requirement: Import never creates identities in local mode

With `local`, the import's identity-provisioning phase SHALL NOT create any account. An entry that is unresolved and carries identity-creation fields (such as `password`) SHALL cause the import to fail closed with the reason `managed_by_identity_provider`, before any authorization write, and the task error SHALL name the unresolved usernames.

#### Scenario: Bundle entry with a password for an unknown user

- **GIVEN** `user_directory: local` and a bundle entry `carol` with a `password`, where `carol` never signed in
- **WHEN** the import runs
- **THEN** the import fails with reason `managed_by_identity_provider` naming `carol`
- **AND** no team, role or OpenFGA relation from that bundle is written

#### Scenario: Bundle entry with a password for a known user

- **GIVEN** `user_directory: local` and a bundle entry `alice` with a `password`, where `alice` signed in before
- **WHEN** the import runs
- **THEN** `alice` resolves from Postgres, her grants are applied and no account is created

### Requirement: Role grants check existence in Postgres

With `local`, the existence check performed before granting a platform role SHALL return a definite answer from the `users` table.

#### Scenario: Unknown user

- **GIVEN** an id absent from the `users` table
- **WHEN** an administrator grants a platform role to it
- **THEN** the request fails with the existing 404 user-not-found response and no relation is written

### Requirement: Account lifecycle belongs to the identity provider

With `local`, creating a user SHALL be refused with HTTP 409 and the reason `managed_by_identity_provider`. Deleting a user SHALL keep the existing suspension-first behavior, SHALL skip the identity-provider deletion step, and SHALL succeed.

#### Scenario: Create user

- **GIVEN** `user_directory: local`
- **WHEN** an administrator calls the create-user endpoint
- **THEN** the response is 409 with `reason: managed_by_identity_provider`

#### Scenario: Delete user

- **GIVEN** `user_directory: local` and an existing person
- **WHEN** an administrator deletes them
- **THEN** the person is suspended and their next authorization decision is refused
- **AND** no identity-provider call is made

#### Scenario: Root protection still applies

- **GIVEN** `user_directory: local`
- **WHEN** an administrator deletes the bootstrap root or the wildcard subject
- **THEN** the existing refusals are returned unchanged

### Requirement: Recording a human identity precedes CGU acceptance

With `user_directory: local`, the first authenticated human control-plane request,
including `GET /user`, SHALL upsert the profile before CGU acceptance. The upsert
SHALL NOT accept CGU, change suspension status, grant permissions or join teams.
Existing throttling and logged non-fatal write failures SHALL be retained.

#### Scenario: Person leaves without accepting terms

- **GIVEN** a new authenticated person and required CGU version `v1`
- **WHEN** Fred loads `/user` and the person leaves without accepting
- **THEN** their profile exists in the local directory when storage is available
- **AND** the accepted CGU version remains unset
- **AND** subsequent CGU-protected API access returns HTTP 403 `user_not_accept_gcu`

#### Scenario: Profile refresh preserves acceptance

- **GIVEN** a person who already accepted the required version
- **WHEN** an authenticated request updates their identity snapshot
- **THEN** their acceptance and suspension state remain unchanged

#### Scenario: Untrusted and workload requests

- **GIVEN** a missing or invalid JWT, a workload or a delegated asserted person
- **WHEN** a request reaches the pre-CGU authentication path
- **THEN** no human profile is created by this snapshot mechanism
