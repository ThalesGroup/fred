# Spec Delta

## MODIFIED Requirements

### Requirement: Example slides are labelled by a vision model

The system SHALL render each example slide to an image with its slots numbered and ask a vision-capable model for the slide's kind, label, the purpose of each slot, the maximum number of items and whether the slide is reusable. Geometry and capacities SHALL stay those of the deterministic analysis.

- When enabled, labelling SHALL use Knowledge Flow's configured `vision_model`, independently of the agent's chat model and team model routing; the capability settings SHALL offer no model selector.
- With "Use a vision model" off, the analysis SHALL make no model call, label by rules only, and run again because the setting changed.
- When Knowledge Flow has no configured vision model, the toggle SHALL be shown disabled and off with a message that slides are labelled by rules.
- The capability SHALL own its slide-specific prompt, parse and validate the answer; Knowledge Flow SHALL only perform the bounded vision-model call.

#### Scenario: Vision label incompatible with the slots

- **WHEN** the model's kind needs slots the slide does not have (`bullets` without a body slot, `cover` without a title slot, `cards` without a repeated group)
- **THEN** the slide keeps its heuristic kind, takes the model's label and slot purposes, and the rejection is logged and shown as a pattern warning

#### Scenario: Vision unavailable or invalid

- **WHEN** a vision call fails or its answer is malformed
- **THEN** the slide keeps its heuristic kind and label, is marked as heuristically labelled, and the analysis still completes

#### Scenario: Vision model is centrally configured

- **GIVEN** a chat model with no vision declaration and Knowledge Flow with a configured vision model
- **WHEN** an editor enables vision labelling
- **THEN** the toggle remains available and the configured Knowledge Flow model labels slides without any chat-model selection

#### Scenario: Previously selected vision model

- **GIVEN** a saved agent or platform template with a legacy vision-profile selection
- **WHEN** its settings are read or its template is re-analysed
- **THEN** the selection is ignored, no model selector is shown, and an enabled vision toggle uses Knowledge Flow's configured model

#### Scenario: No configured Knowledge Flow vision model

- **WHEN** an editor opens vision settings while Knowledge Flow has no configured vision model
- **THEN** the toggle is disabled and off with a rules-only explanation; an existing saved vision-enabled preparation reports the missing configuration clearly until corrected

### Requirement: Analysis runs in the background

The system SHALL complete the agent save without waiting for template analysis, persist the input, status and result durably across replicas through the shared capability-preparation lifecycle, and expose the analysis status to the agent form.

- A save SHALL store the template, record a pending analysis keyed by the agent, capability, template hash, labelling setting and rules version, and return; the same input and settings with a succeeded current analysis SHALL be kept as is.
- While the analysis is pending or running the form SHALL show it in progress, then the summary and thumbnails; the agent SHALL be unavailable, with the reason, on the team agents page and not selectable in the chat agent picker; the card and form SHALL say, in the user's language, that the template is being read and the agent will be available again automatically in a few minutes (a generic "available again in a few minutes, nothing to do" when several capabilities declare what they prepare).
- On success the agent SHALL become available without another save when every required capability preparation has succeeded and no other availability rule blocks it. A failed analysis SHALL not be reported as ready.
- A save, create or copy SHALL never make a preparing agent available, even briefly. A preparation result SHALL NOT clear or replace a suspension made while it was in flight.
- A copied agent's analysis SHALL use the destination's template copy and the same Knowledge Flow vision service when vision is enabled.
- A failed analysis SHALL leave the agent unavailable, the form showing the error and a retry action; retry SHALL run from the stored template without requiring a remembered model handle.
- The build tool reached before the analysis succeeded SHALL build nothing and return that the analysis is not ready; a deck SHALL be rendered on the template its analysis was made from, never a newer file with an older inventory.
- A config save or copy by a user who cannot edit the team's agents, a readiness check by one who cannot use them, and analysis status or thumbnail reads by a non-editor SHALL be refused before accessing team-scoped services.
- Concurrent analysis SHALL be bounded independently of serving chat turns and SHALL NOT rely on an individual pod's heavy-job slots for correctness.

#### Scenario: Interrupted analysis recovers

- **WHEN** the worker running an analysis stops before finishing
- **THEN** another worker retries from the durable template after its lease expires, without a new save or process-local model handle; the agent remains unavailable until the current analysis succeeds

#### Scenario: Analysis rules change

- **GIVEN** an agent whose succeeded analysis was produced by older analysis rules
- **WHEN** its readiness is checked, a turn reads the analysis, or the agent is saved
- **THEN** the agent stays available on the stored analysis and one re-run starts in the background from the stored template, without a user token or remembered model handle; concurrent checks start no second one, and the form shows it as being read again, then the new result without a reload
- **AND** when the re-run fails the stored analysis stays in use, no re-run starts automatically again, and the form says saving or retrying re-runs it

#### Scenario: A newer template overtakes the analysis

- **WHEN** an editor uploads another template before the old analysis completes
- **THEN** the old result cannot become the agent's active inventory and the newer template remains the pending revision

### Requirement: Built-in template and platform default

The system SHALL ship a real `.pptx` Fred template with example slides and its pre-computed analysis as the platform's initial default template; a test SHALL fail until that stored analysis is regenerated after an analysis rules change. The platform SHALL always have exactly one platform-wide default; an agent with no template of its own SHALL build on it through the same path as a customer template, and an agent's own template SHALL always win. A capability manager, platform admin or feature manager MAY replace it from Admin > Features (ppt_builder settings drawer) with a `.pptx` within the agent template size limit, stored in durable shared storage, analysed in the background, reviewable and re-runnable; other callers SHALL be refused with 403 on every write, and any authenticated user MAY read its status, summary and previews (the drawer read only). The Fred template SHALL never be removable: "Reset", after confirmation, deletes the replacement, any replacement being analysed and all pattern edits (the Fred template's included).

- A replacement SHALL take effect only once its analysis succeeds, the previous one then deleted; while pending, running or failed, agents keep the previous default with its edits and stay ready, and the drawer shows status, file name, failure and re-run.
- An analysis of the default SHALL never make an agent unready or suspended; a change SHALL reach every replica within 30 seconds plus one turn, with no database read on an ordinary turn.
- The platform template SHALL use Knowledge Flow's configured `vision_model` when vision labelling is enabled, or rules only when disabled; the settings SHALL offer no model selector and SHALL not depend on the platform chat default.
- A capability manager SHALL review and edit (rename, include/exclude, re-kind) the patterns of the default in effect, the Fred template included; edits apply to every agent on it within the propagation bound; a re-analysis of the same file keeps edits whose patterns exist, another file starts without; the Fred template's edits are kept but not applied while a replacement is in effect.
- Pattern edits SHALL apply only to the template they were made on: an agent without its own template has no edits of its own, and one that removes its template drops its edits.
- The agent form SHALL show the default in effect with a read-only review; with a replacement, "Template set by the administrator" (fr: "Template défini par l'administrateur") with its file name.
- Admin > Features SHALL put the settings action in its own rightmost table column for every capability kind; a row SHALL show the gear only when that capability exposes a platform settings panel, and leave the cell empty otherwise.
- Both agent form layouts SHALL offer an explicit action to return from a saved agent template to the platform default. The pending form SHALL clear any staged replacement and template-specific edits, show the default immediately, and persist the choice only on Save. Other `ppt_builder` settings SHALL remain unchanged.

#### Scenario: Built-in deck read by the rules

- **WHEN** the built-in deck is analysed without a vision model
- **THEN** its agenda lists up to seven numbered entries, section slides are `section` with a number zone that never takes the subtitle, each timeline milestone carries its date as number, its table takes up to five columns, statement slides are `quote`, and each item slide removes an unused item with its card, tile or dot

#### Scenario: Analysis failed

- **WHEN** a replacement default's analysis fails
- **THEN** agents keep building on the previous default and stay ready, and the drawer shows the failure with a re-run action

#### Scenario: Settings action belongs to supported rows

- **WHEN** Admin > Features lists capabilities with and without a platform settings panel
- **THEN** the rightmost Settings column shows a gear for each supported row, no gear for other rows, and the team-management action remains in its own column

#### Scenario: Return a saved agent to the platform template

- **GIVEN** an agent with its own saved template and pattern edits
- **WHEN** its author chooses the return-to-platform action and saves the agent
- **THEN** the agent no longer selects its own template, its template-specific edits are removed, and it builds on the current platform default (or the built-in template when no replacement is active)

#### Scenario: Cancel a pending return to the platform template

- **GIVEN** an agent with its own saved template
- **WHEN** its author chooses the return-to-platform action but closes the form without saving
- **THEN** the saved agent keeps its own template

#### Scenario: Unsaved replacement is distinct from saved override

- **GIVEN** an agent with its own saved template and another file selected in the form
- **WHEN** its author clears only the selected file
- **THEN** the saved template remains selected in the form; choosing the return-to-platform action instead clears both the selected file and the saved override in the pending form
