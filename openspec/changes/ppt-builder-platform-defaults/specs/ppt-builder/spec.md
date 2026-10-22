## ADDED Requirements

### Requirement: Platform default template

The platform SHALL always have exactly one default template for ppt_builder. Its initial value SHALL be the Fred template shipped with the capability. A capability manager, platform admin or feature manager, MAY replace it from Admin > Features with a `.pptx` within the same size limit as an agent template. A replacement SHALL be stored in the capability's own database table, analysed in the background like an agent template, reviewable, and re-runnable. The Fred template SHALL never be removable: "Reset" deletes the replacement, any replacement being analysed and the manager's pattern edits, and the Fred template is the default again. Any other caller SHALL be refused on every write. Any authenticated user MAY read the default template's status, summary and slide previews. The default template SHALL be platform-wide: no team has its own.

#### Scenario: Fresh platform

- **WHEN** no capability manager has ever changed the default template
- **THEN** the drawer shows the Fred template as the platform default

#### Scenario: Capability manager replaces the default template

- **WHEN** a capability manager uploads a readable `.pptx` within the size limit in the ppt_builder settings drawer
- **THEN** the template is stored, its analysis starts in the background, and the drawer shows the file name and the analysis status until it succeeds or fails, saying that the previous template stays in use meanwhile

#### Scenario: Non-manager refused

- **WHEN** a user who is neither platform admin nor feature manager calls a default template write (replace, re-run, reset)
- **THEN** the request is refused with 403 and nothing changes

#### Scenario: Invalid upload

- **WHEN** the uploaded file is not a readable `.pptx` or exceeds the size limit
- **THEN** the upload is refused with an error shown in the drawer, and the current default template stays as it was

#### Scenario: Reset to the Fred template

- **WHEN** the manager chooses "Reset"
- **THEN** after a confirmation, the replacement, any replacement being analysed and the pattern edits are deleted, the Fred template becomes the default template again, and agents without a template of their own build on it

#### Scenario: No removal

- **WHEN** a capability manager looks for a way to leave the platform without a default template
- **THEN** no such action exists, in the drawer or in the API

#### Scenario: Settings action only where a platform panel exists

- **WHEN** a capability manager opens Admin > Features
- **THEN** the ppt_builder row shows a settings action that opens its drawer, and capabilities without a platform panel show none

#### Scenario: Other users see the drawer read only

- **WHEN** a user who is not a capability manager opens the ppt_builder drawer
- **THEN** it shows the default template and its status, without upload, re-run, vision, edit or reset actions

### Requirement: Platform template vision model

A capability manager SHALL choose the vision model that labels the platform default template, among the vision-capable models of the catalogue, or rules only. Until a manager chooses one, it SHALL be the platform's default model. The choice SHALL apply to the platform template only: agent templates keep their own labelling settings.

#### Scenario: Default choice

- **WHEN** a manager uploads a template without changing the vision model
- **THEN** its example slides are labelled by the platform's default model, or by rules only when that model cannot read images

#### Scenario: Manager changes the model

- **WHEN** the manager picks another vision model, or rules only, and re-runs the analysis
- **THEN** only the platform template is analysed again with that choice, and agent analyses are untouched

### Requirement: Platform template pattern edits

A capability manager SHALL review the slides of the platform default template in effect and adjust them as an author does for an agent template: rename a pattern, include or exclude it, change its type. These pattern edits SHALL be stored with the platform template and SHALL apply to every agent that builds on it. They SHALL be pruned against the template's analysis like an agent's: a re-analysis of the same file keeps the edits whose patterns still exist, and another file starts without edits.

#### Scenario: Manager edits a slide

- **WHEN** a capability manager excludes a pattern of the platform template in the review dialog and saves
- **THEN** agents without a template of their own no longer use that pattern, within the propagation bound

#### Scenario: Re-analysis keeps valid edits

- **WHEN** the manager re-runs the analysis of the same file and it succeeds
- **THEN** the edits whose patterns still exist apply to the new analysis, and the others are dropped

#### Scenario: New file starts without edits

- **WHEN** another file replaces the platform template and its analysis succeeds
- **THEN** it applies with no pattern edits

### Requirement: Replacing the default never blocks agents

A replacement default template SHALL take effect only once its analysis has succeeded. While it is pending, running or failed, agents without a template of their own SHALL keep building on the previous default template: the previous replacement with its pattern edits, or the Fred template when there was none. An analysis of the default template SHALL never make an agent unready or suspended. A change SHALL reach every replica within a bounded delay, 30 seconds plus one turn by default, with no database read on an ordinary turn.

#### Scenario: Analysis pending

- **WHEN** a replacement default template is still being analysed
- **THEN** agents without a template of their own keep building on the previous default template, and stay ready

#### Scenario: Analysis failed

- **WHEN** the replacement's analysis fails
- **THEN** agents keep building on the previous default template, stay ready, and the drawer shows the failure with a re-run action

#### Scenario: Replacement succeeds

- **WHEN** the replacement's analysis succeeds
- **THEN** it becomes the default template in effect, and the previous one is deleted

#### Scenario: Propagation across replicas

- **WHEN** the default template changes on one replica
- **THEN** every replica builds on the new default within the propagation bound

### Requirement: Agent form shows the platform default

When an agent has no template of its own, the agent form SHALL show the default template in effect, and its read-only review SHALL show that template's slides, with the manager's pattern edits. When a replacement is in effect, the form SHALL say that the template was set by the administrator, with its file name. The author MAY still upload a template of the agent's own.

#### Scenario: Replaced default in effect

- **WHEN** an author opens the capability card of an agent with no template, and a replacement default template is in effect
- **THEN** the card reads "Template set by the administrator" (fr: "Template défini par l'administrateur") with the file name, and the review shows that template's slides, read only

#### Scenario: Fred template in effect

- **WHEN** the default template in effect is the Fred template
- **THEN** the card shows the Fred template as today

### Requirement: Pattern edits apply only to the agent's own template

Pattern edits (overrides) SHALL apply only to the template they were made on. An agent without a template of its own SHALL build with no pattern edits of its own, whichever default template is in effect; the platform template's edits apply to it.

#### Scenario: Agent goes back to no template

- **WHEN** an agent with pattern edits on its own template removes that template and saves
- **THEN** its pattern edits are dropped, and the default template in effect is used with only the platform's edits

## MODIFIED Requirements

### Requirement: Built-in Fred template when none is configured

The system SHALL ship a real `.pptx` template with example slides and its pre-computed analysis, as the platform's initial default template. An agent with no template of its own SHALL build on the platform default template in effect, through the same assignment and rendering path as a customer template: the replacement once its analysis has succeeded, else the Fred template.

#### Scenario: Agent without template

- **WHEN** an agent enables the capability without uploading a template, and the platform default is the Fred template
- **THEN** the tool is available at once and builds decks from the built-in template's example slides

#### Scenario: Agent without template, replaced default

- **WHEN** an agent has no template of its own and a replacement default template's analysis has succeeded
- **THEN** the tool builds decks from that template's example slides

#### Scenario: Agent template wins

- **WHEN** an agent has its own template
- **THEN** it builds on its own template whatever the platform default is

#### Scenario: Built-in deck read by the rules

- **WHEN** the built-in deck is analysed without a vision model
- **THEN** its agenda is a list of up to seven numbered entries, its section slides read as `section` with a number zone that never takes the subtitle, each timeline milestone carries its date as the item's number, its table takes up to five columns, its statement slides read as `quote`, and each item slide removes an unused item with its card, tile or dot

#### Scenario: Built-in analysis kept current

- **WHEN** the analysis rules change
- **THEN** a test fails until the built-in template's stored analysis is regenerated
