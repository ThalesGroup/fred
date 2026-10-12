## ADDED Requirements

### Requirement: Optional daily quotas per user

Fred SHALL let a deployment cap, per user and per UTC calendar day, the number of searches and the number of page reads independently. Each cap SHALL be optional and absent by default. A request over its cap MUST be refused before any network access with `quota_exceeded`, recorded as a failed activity that does not consume quota.

#### Scenario: Search quota reached
- **WHEN** a user has already made the configured number of searches today (UTC)
- **THEN** the next search returns `quota_exceeded` without contacting the provider, and page reads remain available

#### Scenario: Remaining quota shown
- **WHEN** a capped operation succeeds
- **THEN** its result carries the cap and the remaining count for today, shown in the trace detail

#### Scenario: No quota configured
- **WHEN** neither cap is set
- **THEN** no request is ever refused for quota and results carry no quota

#### Scenario: New day
- **WHEN** UTC midnight passes
- **THEN** the user's counts start again from zero
