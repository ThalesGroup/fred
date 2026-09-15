## Purpose

Prove, on a running deployment and from the admin's own browser, that an agent
turn whose work outlives the credential it was handed can still call platform
services as the person afterwards — and make that proof fail loudly while the
runtime cannot renew a delegated credential.

## ADDED Requirements

### Requirement: The turn runs on the signed-in session's captured credential

The credential-expiry check SHALL capture the signed-in session's current access
token once, after ensuring the session is fresh, and SHALL supply that single
value as the credential for the one agent turn under test. Every other call the
run makes — enrollment, execution preparation and cleanup — SHALL use the live
session, which the browser continues to refresh normally. The captured
credential SHALL NOT appear in any step report. The check SHALL require no
password and no realm configuration change.

#### Scenario: The session refreshes while the run is being prepared

- **WHEN** the browser replaces the session's token between capture and the turn
- **THEN** the turn still runs on the captured credential, and no report contains it

#### Scenario: No realm is configured

- **WHEN** the deployment runs without a realm
- **THEN** the check is reported as skipped with that reason and creates nothing

#### Scenario: The session's remaining lifetime is unknown or already elapsed

- **WHEN** the session cannot be refreshed, or reports no usable remaining lifetime
- **THEN** the check fails with a readable reason, exposes no underlying cause, and creates nothing

### Requirement: Hold sized from the captured lifetime and bounded

The check SHALL set the agent's hold to the captured credential's remaining
lifetime plus a margin, and SHALL skip with the reason when that exceeds the
supported maximum. The harness agent SHALL support a per-instance hold,
configured by an integer tuning field clamped to the same maximum, executed
before its call. A hold of zero SHALL leave the agent's behavior unchanged.
During a hold the agent SHALL emit periodic events on the live channel so the
execution stream stays alive, and SHALL emit one status marking the hold's end.

#### Scenario: The remaining lifetime exceeds the bound

- **WHEN** the captured credential's remaining lifetime plus the margin is above the maximum hold
- **THEN** the check is reported as skipped with that reason and enrolls no agent instance

#### Scenario: An instance is enrolled with a hold

- **WHEN** a turn runs against an instance whose hold is set
- **THEN** the agent waits that long, emitting heartbeats while it waits and one status when the hold ends

### Requirement: Authenticated calls as the person, with no corpus fixture

In its access-check mode the harness agent SHALL make one authenticated metadata
call as the person before the hold and one after it, SHALL emit a status for
each, and SHALL NOT read documents or invoke retrieval. The check SHALL create
no library, document, prompt or session.

#### Scenario: The metadata call answers with nothing to report

- **WHEN** the authenticated call returns no matching metadata
- **THEN** the call still counts as succeeded, because acceptance of the credential is what it proves

#### Scenario: The authenticated call is refused

- **WHEN** a call as the person is refused
- **THEN** the agent ends the turn with a fixed message that distinguishes an expired credential from any other refusal, carrying no upstream response text

### Requirement: One temporary agent instance, removed by the run

The check SHALL enroll one agent instance for the run, carrying the hold and the
access-check mode, and SHALL delete it when the run ends however it ends,
treating an instance that is already gone as deleted. Enrolling SHALL NOT remove
any other instance of the same template, so nothing collects an instance whose
run never reached its teardown.

#### Scenario: The run is cancelled after the instance exists

- **WHEN** the run is cancelled once the instance has been enrolled
- **THEN** no turn is started and the instance is deleted

#### Scenario: The run is cancelled while the instance is being created

- **WHEN** creation is interrupted by cancellation
- **THEN** the step is reported as cancelled, not as a creation that failed

#### Scenario: The run is interrupted before its teardown

- **WHEN** the page is closed or reloaded while a run is in flight
- **THEN** the instance that run created stays, to be deleted by hand from the admin's personal agents

#### Scenario: Deletion is refused

- **WHEN** deleting the instance fails for a reason other than it being gone
- **THEN** the step fails telling the admin to remove the temporary instance, exposing no upstream detail

### Requirement: Verdict tied to actual expiry

The check SHALL pass only when all of the following are observed: the first
authenticated call succeeded; the hold ended at least a fixed tolerance after
the captured credential's recorded expiry; the call after the hold succeeded
after the hold ended; and the credential was observed to be renewed. Any run
missing one of these SHALL be reported as failed, naming it as inconclusive
where the run demonstrated nothing. A refusal SHALL be reported with one fixed
explanation, whether it arrives as an execution error or as the turn's final
text, and SHALL carry no upstream response text or credential value. A turn
refused before it started SHALL NOT be reported as expiry during execution.

#### Scenario: Renewal is not available

- **WHEN** the call after the hold is refused because the credential expired
- **THEN** the step fails with the fixed expiry explanation and the instance is still deleted

#### Scenario: Renewal works

- **WHEN** the call after the hold succeeds and the credential is observed to have been renewed
- **THEN** the step passes, stating that authenticated access survived expiry

#### Scenario: The call succeeded but no renewal was observed

- **WHEN** the call after the hold succeeds while the credential in hand never changed
- **THEN** the step fails as inconclusive, because the original credential may simply still be accepted

#### Scenario: The hold did not outlast the credential

- **WHEN** the hold ended before the recorded expiry, or the first authenticated call was never observed
- **THEN** the step fails as inconclusive, naming which evidence is missing

#### Scenario: The turn was refused at admission

- **WHEN** the execution request itself is rejected
- **THEN** the step fails saying the turn never started, which does not demonstrate expiry during execution

### Requirement: Placement on the self-test page

The check SHALL be its own sub-section of the authorization self-test, with its
own action and step report, running as the signed-in account and asking for no
password. The page SHALL run one self-test at a time, so its action is
unavailable while any run on the page is in flight.

#### Scenario: Another run on the page is in flight

- **WHEN** a self-test is already running on the page
- **THEN** the credential-expiry action is unavailable until it finishes

### Requirement: The credential is proven before the wait

The agent SHALL make the authenticated call once before any waiting, in a stage
of its own so that the result reaches the stream before the wait begins rather
than with it. The check SHALL report that evidence as its own step, marked as
soon as it arrives, and SHALL mark it failed when it never arrives. The step
that creates the run's temporary agent SHALL name the template it is enrolled
from and what kind of agent that is.

#### Scenario: The credential is accepted before the wait

- **WHEN** the agent's first authenticated call succeeds
- **THEN** the pre-expiry step is reported as passed while the wait is still running

#### Scenario: The first call never succeeded

- **WHEN** no evidence of that first call arrives
- **THEN** the pre-expiry step is reported as failed and the run is inconclusive

### Requirement: Accepted before it starts

Because the run lasts until the session's credential expires and cannot clean up
after a page that closes, the action SHALL first present a notice the admin
accepts or dismisses, and SHALL start nothing until it is accepted. The notice
SHALL state how long the run will wait, derived from the same remaining lifetime
the run sizes its hold from, that the page must stay open until it ends, and
that closing the page early leaves one temporary agent to delete by hand. Where
the remaining lifetime is unknown, the notice SHALL still be shown, without a
figure.

#### Scenario: The admin accepts the notice

- **WHEN** the admin starts the check and accepts the notice
- **THEN** the run begins, having quoted the wait it will take

#### Scenario: The admin dismisses the notice

- **WHEN** the admin dismisses the notice
- **THEN** nothing is created and no run begins
