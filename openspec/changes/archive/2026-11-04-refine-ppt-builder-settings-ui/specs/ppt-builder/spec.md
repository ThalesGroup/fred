# Spec Delta

## MODIFIED Requirements

### Requirement: Built-in template and platform default

The system SHALL ship a real `.pptx` Fred template with example slides and its pre-computed analysis as the platform's initial default template; a test SHALL fail until that stored analysis is regenerated after an analysis rules change. The platform SHALL always have exactly one platform-wide default; an agent with no template of its own SHALL build on it through the same path as a customer template, and an agent's own template SHALL always win. A capability manager, platform admin or feature manager MAY replace it from Admin > Features (ppt_builder settings drawer) with a `.pptx` within the agent template size limit, stored in the capability's own table, analysed in the background, reviewable and re-runnable; other callers SHALL be refused with 403 on every write, and any authenticated user MAY read its status, summary and previews (the drawer read only). The Fred template SHALL never be removable: "Reset", after confirmation, deletes the replacement, any replacement being analysed and all pattern edits (the Fred template's included).

- A replacement SHALL take effect only once its analysis succeeds, the previous one then deleted; while pending, running or failed, agents keep the previous default with its edits and stay ready, and the drawer shows status, file name, failure and re-run.
- An analysis of the default SHALL never make an agent unready or suspended; a change SHALL reach every replica within 30 seconds plus one turn, with no database read on an ordinary turn.
- The labelling model SHALL be chosen among the vision-capable models offered without a team (models enabled for every team, profiles on every pod), or rules only, defaulting to the platform's default model (rules when it cannot read images); another model SHALL be refused with 422; the choice applies to the platform template only.
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
