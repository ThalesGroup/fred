# Spec Delta

## MODIFIED Requirements

### Requirement: Analysis runs in the background

The system SHALL start an agent template's bounded upload and durable analysis when its author selects the file, for both creation and editing. Save SHALL adopt the selected preparation without waiting for its analysis, and status and results SHALL remain durable across replicas.

- The selected template SHALL be uploaded for a temporary draft owned by the author and team, then prepared by the shared worker with the current analysis settings and rules version. The form SHALL distinguish uploading, queued/running, succeeded and failed states.
- Save SHALL atomically attach the current draft asset and preparation to the agent only when its file, capability, team, runtime and analysis settings still match the form. A succeeded current result SHALL remain succeeded; a pending or running result SHALL continue without a duplicate analysis. Save without a draft SHALL retain the existing bounded multipart upload path for compatible clients.
- Closing or cancelling the form before Save SHALL leave a saved agent unchanged and create no agent during creation. Abandoned drafts SHALL expire and their assets and results SHALL be reclaimed. A draft SHALL never make an unsaved agent selectable or change a saved agent's readiness.
- Selecting a replacement or changing an analysis setting SHALL supersede the previous draft revision. Only the latest revision may be adopted; an older result SHALL NOT become the agent's active inventory. A failed draft SHALL be retryable without saving the agent.
- While an adopted analysis is pending or running the form SHALL show it in progress, then the summary and thumbnails; the agent SHALL be unavailable, with the reason, on the team agents page and not selectable in the chat agent picker; the card and form SHALL say, in the user's language, that the template is being read and the agent will be available again automatically in a few minutes (a generic "available again in a few minutes, nothing to do" when several capabilities declare what they prepare).
- On success the agent SHALL become available without another save when every required capability preparation has succeeded and no other availability rule blocks it. A failed analysis SHALL not be reported as ready.
- A save, create or copy SHALL never make a preparing agent available, even briefly. A preparation result SHALL NOT clear or replace a suspension made while it was in flight.
- A copied agent's analysis SHALL use the destination's template copy and the same Knowledge Flow vision service when vision is enabled.
- A failed adopted analysis SHALL leave the agent unavailable, the form showing the error and a retry action; retry SHALL run from the stored template without requiring a remembered model handle.
- The build tool reached before the analysis succeeded SHALL build nothing and return that the analysis is not ready; a deck SHALL be rendered on the template its analysis was made from, never a newer file with an older inventory.
- Draft upload, status, retry, adoption and cleanup SHALL enforce the author's team editing permission and draft ownership; config save or copy by a user who cannot edit the team's agents, readiness check by one who cannot use them, and analysis status or thumbnail reads by a non-editor SHALL be refused before accessing team-scoped services.
- Concurrent analysis SHALL be bounded independently of serving chat turns and SHALL NOT rely on an individual pod's heavy-job slots for correctness.

#### Scenario: Selection starts preparation before Save

- **GIVEN** an author creating or editing an agent with PPT Builder active
- **WHEN** they select a valid `.pptx` file
- **THEN** the form shows upload progress immediately and the worker receives a durable preparation once transfer completes, without an agent save

#### Scenario: Save adopts a running draft

- **GIVEN** a draft whose upload completed and analysis is running
- **WHEN** the author saves the agent with matching settings
- **THEN** Save returns without waiting for analysis and the same preparation continues as the agent's current revision

#### Scenario: Save adopts a completed draft

- **GIVEN** a draft whose analysis succeeded under the current settings and rules
- **WHEN** the author saves the agent
- **THEN** the agent uses that result without running the analysis again

#### Scenario: Abandoned creation or edit

- **WHEN** the author selects a template and closes the form before saving
- **THEN** no agent is created or changed, and the unused draft and its objects are eventually removed

#### Scenario: Replacement or settings change overtakes a draft

- **GIVEN** an upload or analysis already in progress
- **WHEN** the author selects another file or changes an analysis setting
- **THEN** the form tracks only the new current revision and Save cannot adopt the older result

#### Scenario: Draft failure and retry

- **WHEN** upload or analysis of a selected template fails before Save
- **THEN** the form shows the failure and offers a retry or replacement without changing the saved agent

#### Scenario: Draft access is scoped

- **WHEN** another user or team requests a draft's status, result, retry or adoption
- **THEN** the request is refused without exposing the template or its analysis

#### Scenario: Interrupted analysis recovers

- **WHEN** the worker running an analysis stops before finishing
- **THEN** another worker retries from the durable template after its lease expires, without a new save or process-local model handle; an adopted agent remains unavailable until the current analysis succeeds

#### Scenario: Analysis rules change

- **GIVEN** an agent whose succeeded analysis was produced by older analysis rules
- **WHEN** its readiness is checked, a turn reads the analysis, or the agent is saved
- **THEN** the agent stays available on the stored analysis and one re-run starts in the background from the stored template, without a user token or remembered model handle; concurrent checks start no second one, and the form shows it as being read again, then the new result without a reload
- **AND** when the re-run fails the stored analysis stays in use, no re-run starts automatically again, and the form says saving or retrying re-runs it

#### Scenario: A newer template overtakes the analysis

- **WHEN** an editor uploads another template before the old analysis completes
- **THEN** the old result cannot become the agent's active inventory and the newer template remains the pending revision
