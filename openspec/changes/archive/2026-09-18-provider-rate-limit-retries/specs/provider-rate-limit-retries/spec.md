## Purpose

Recover transient provider throttling during agent model calls without repeating completed tools or obscuring failures.

## ADDED Requirements

### Requirement: Bounded observable model retries
ReAct and Deep parent turns SHALL retry provider 429 model calls at most four times in total, with jitter and a 60-second retry scheduling budget. Every failed attempt SHALL emit a throttle counter and log, and every model attempt SHALL remain traced. Existing transport timeouts SHALL continue to bound provider I/O.

#### Scenario: Recovery
- **WHEN** a model call is throttled and then succeeds within the retry bounds
- **THEN** the turn continues without repeating already completed tools or outer input preparation

#### Scenario: Exhaustion
- **WHEN** no retry fits the remaining budget or all attempts fail
- **THEN** the turn fails with a readable rate-limit message without the provider payload

#### Scenario: Cancellation and other failures
- **WHEN** a call or backoff is cancelled or a non-429 failure occurs
- **THEN** the failure propagates without another model attempt

### Requirement: Shared throttle detection and provider hints
Agent retries and document extraction SHALL share detection. Explicit non-429 status SHALL take precedence over message fallback. Finite nonnegative numeric and valid HTTP-date Retry-After hints SHALL be honored when affordable; invalid hints SHALL use fallback backoff.

#### Scenario: Provider delay
- **WHEN** a provider specifies a usable delay within the remaining scheduling budget
- **THEN** the retry waits at least that delay, with jitter

#### Scenario: Unaffordable delay
- **WHEN** a provider hint exceeds the remaining scheduling budget
- **THEN** the call fails without retrying earlier than the provider requested
