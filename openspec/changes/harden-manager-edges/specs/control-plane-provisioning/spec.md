## ADDED Requirements

### Requirement: Role subjects are validated before authorization writes
A space-role or platform-role grant or revocation SHALL refuse a subject that is not
a valid OpenFGA user identifier with 422, before capturing a guard or writing to
OpenFGA. A 409 conflict SHALL only report a concurrent authorization change.

#### Scenario: Malformed subject
- **WHEN** an authorized administrator grants a role to a subject containing whitespace, `:` or `#`
- **THEN** the API returns 422 and no tuple or guard revision changes

### Requirement: Revocation audit reports only removed roles
A space-role revocation of a role the target does not hold SHALL still succeed and
fence the organization guard, but SHALL emit no `authz.relation.revoked` audit event.
A revocation that removes a held role SHALL emit exactly one such event.

#### Scenario: Repeated revocation
- **WHEN** an administrator revokes the same held role twice
- **THEN** both requests return 204 and the audit stream contains one revocation event
