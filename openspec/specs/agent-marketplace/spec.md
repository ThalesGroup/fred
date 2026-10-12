# agent-marketplace Specification

## Purpose
Lets a team publish one of its agents to an organization-wide marketplace as a snapshot, shows whether the published version is current, and lets other users discover and import it into their own spaces.

## Requirements

### Requirement: Only an editor publishes, within the team's settings

The control-plane SHALL publish an agent only when the caller holds `team_editor` on the agent's team, publication is enabled for the team, the team is public, and the agent's template is public. A new publication SHALL also require the team's published count to be below its agents quota; republishing a published agent SHALL NOT be limited by the quota. Agents of a personal space MUST NOT be published. Publish and Republish SHALL be offered in the agent card's more menu to editors only; they MUST be absent for other users and in personal spaces, and greyed out with a tooltip when the quota is reached, the team is private, or the template is not public. User-facing text MUST NOT use the word "template".

#### Scenario: Editor publishes from the card

- **WHEN** an editor of a public team with publication enabled and whose quota is not reached chooses Publish in the more menu of an agent on a public template and confirms the warning dialog
- **THEN** the agent is published and appears in the agents marketplace

#### Scenario: Non-editor sees no publish action

- **WHEN** a member or a team admin who is not an editor opens an agent card's more menu
- **THEN** no Publish or Republish action is shown, and a direct publish request fails with 403

#### Scenario: Agent type reserved to platform administrators

- **WHEN** an editor opens the more menu of an agent built on a non-public template
- **THEN** Publish is greyed out with the tooltip "This agent uses an agent type reserved to platform administrators: it cannot be published." (fr: "Cet agent repose sur un type d'agent réservé aux administrateurs de la plateforme : il ne peut pas être publié."), and a direct request fails

#### Scenario: Private team

- **WHEN** an editor of a private team opens an agent card's more menu
- **THEN** Publish is greyed out with a tooltip saying that private teams cannot publish, and a direct request fails

#### Scenario: Personal space

- **WHEN** a user opens the more menu of an agent of their personal space
- **THEN** no publish action is shown, and a direct request fails

#### Scenario: Quota reached

- **WHEN** a team has as many published agents as its quota and an editor opens the more menu of an unpublished agent
- **THEN** Publish is greyed out with a tooltip saying the quota is reached, and a direct request fails

#### Scenario: Republish above a lowered quota

- **WHEN** the quota was lowered below the team's published count and an editor republishes a published agent
- **THEN** the republication is accepted and the published count does not change

#### Scenario: Publish after a removal counts against the quota

- **WHEN** a removed agent is published again while the team's quota is reached
- **THEN** the action is labelled "Publish", greyed out with the quota reason, and a direct request fails

### Requirement: Every publication goes through the warning dialog

Every publication and republication SHALL open the same dialog. It SHALL warn that the agent's configuration becomes visible to every user of the organization and, when the agent has configuration files, that anyone who imports it receives a copy of its files (naming them); show the team's quota usage ("3 of 5 published"); and link to the Help Center. Counts and dates in the feature's texts SHALL use the locale's plural forms and date format. The confirm action MUST stay disabled until the user ticks an "I understand" checkbox.

#### Scenario: Confirm disabled until acknowledged

- **WHEN** an editor opens the dialog and has not ticked the checkbox
- **THEN** the confirm action is disabled and nothing is published

#### Scenario: Quota usage shown

- **WHEN** an editor of a team with 3 published agents and a quota of 5 opens the dialog
- **THEN** it shows "3 of 5 published"

### Requirement: Publication stores a snapshot

Publishing SHALL store a snapshot of the agent; the marketplace MUST show and import the snapshot, never the live agent. The snapshot SHALL carry what a copy of the agent to another team carries: public settings kept, team-bound settings (libraries, documents, folders) reset, configuration files captured. A later change of the agent MUST NOT change the snapshot until it is republished.

#### Scenario: Team-bound settings reset

- **WHEN** an editor publishes an agent restricted to a team library
- **THEN** the snapshot has no library restriction and keeps the agent's other settings

#### Scenario: Configuration file captured

- **WHEN** an editor publishes an agent whose capability holds a configuration file
- **THEN** the snapshot contains that file, and importing it never reads the publishing team's files

#### Scenario: Capability that cannot be exported

- **WHEN** the agent's pod cannot export one of its capabilities
- **THEN** the publication fails with a message naming that capability, and no snapshot is stored or replaced

### Requirement: The agent card shows its marketplace state in a bottom bar

The team agent card SHALL show the agent's marketplace state in a bottom bar, pinned to the card's bottom edge and built from the same component as the marketplace card's Like/Import bar. The bar SHALL appear on every card of the team Agents page while the team can publish (publication enabled, public team, not the personal space), and on none otherwise:
- **Not published** (or hidden): a muted "Not published" label only; editors publish from the card's more menu.
- **Published:** the like count and the import count.
- **Modified, not republished:** a warning-coloured state, with the counters kept, saying the marketplace still shows the previous version.
- **Removed:** a state that opens a popover with the reason, the date, the platform admin's reason message if any, and a "Hide" button.

Members who are not editors SHALL see only the Published state; Modified and Removed SHALL be visible to editors and the team admin only.

#### Scenario: Not published bar per role

- **WHEN** a team that can publish shows an agent that is not published
- **THEN** every member sees the "Not published" label only, and editors find Publish in the card's more menu

#### Scenario: Team that cannot publish

- **WHEN** publication is disabled for the team, the team is private, or it is the personal space
- **THEN** no card of the Agents page shows the bar

#### Scenario: Member sees only Published

- **WHEN** a member who is not an editor views a modified published agent
- **THEN** the bar shows Published with its counters, without the modified state

### Requirement: Published agents stay editable and show when they differ

Editors SHALL keep editing, duplicating and copying published agents. A save that changes a published agent SHALL put its bar in the Modified state; a save that changes nothing MUST NOT, and a save made while a publication is in progress SHALL still show as Modified once that publication completes. Republishing SHALL return it to Published.

#### Scenario: Editor modifies a published agent

- **WHEN** an editor saves a change to a published agent's instructions
- **THEN** the save succeeds, the snapshot is unchanged, and the bar shows "Modified, not republished" with the counters

#### Scenario: Save without change

- **WHEN** an editor saves a published agent without changing anything
- **THEN** the bar still shows Published

#### Scenario: Republish clears the state

- **WHEN** an editor republishes a modified agent
- **THEN** the snapshot matches the agent and the bar shows Published

#### Scenario: Republication fails

- **WHEN** a republication fails for any reason (a capability no longer installed on the pod, a capability unable to prepare its configuration, a missing or unreadable configuration file, an unreachable pod)
- **THEN** the previous snapshot stays published unchanged, the editor sees the error, and the bar stays "Modified, not republished"

### Requirement: Editors are offered to republish after their own changes

Right after an editor saves a change to a published agent, the Agents page SHALL open a dialog proposing to republish, with the explicit choices "Publish" and "Ignore"; a click on the scrim MUST NOT close it. "Publish" SHALL open the warning dialog. "Ignore" SHALL leave the agent Modified. The same proposal SHALL open when an editor reactivates an agent that was removed because it was deactivated; when the quota is reached, it SHALL show the greyed quota reason instead of an active "Publish".

#### Scenario: Editor saves a published agent

- **WHEN** an editor saves a change to a published agent
- **THEN** back on the Agents page the republish proposal opens and stays open on a scrim click

#### Scenario: Ignore

- **WHEN** the editor chooses "Ignore"
- **THEN** the dialog closes and the bar shows "Modified, not republished"

#### Scenario: Reactivation proposal at quota

- **WHEN** an editor reactivates an agent removed by its deactivation while the team's quota is reached
- **THEN** the proposal opens with "Publish" greyed out and the quota reason

### Requirement: Entries are removed manually or automatically

An editor or the team admin of the agent's team, and a platform admin, SHALL be able to remove an entry from the marketplace; any other caller MUST be refused. A platform admin MAY add a free-text reason; nothing else is blocked and an editor may publish again. The control-plane SHALL remove the entry automatically when the agent is deactivated, suspended (including a capability or template revoked from its team) or deleted, when publication is disabled for the team, and when the team becomes private. A user action that removes entries MUST state how many before it is confirmed. Deactivating or deleting a published agent SHALL be confirmed through the critical confirmation dialog (Cancel as the filled primary action, the confirming verb in error text style); it is allowed to every editor.

#### Scenario: Team admin removes

- **WHEN** the team admin, who is not an editor, removes an entry from the more menu
- **THEN** the agent is no longer in the marketplace and stays in the team unchanged

#### Scenario: Platform admin removes with a reason

- **WHEN** a platform admin who is not a member of the team removes an entry with the reason "Outdated instructions"
- **THEN** the agent is no longer in the marketplace and the Removed popover shows that reason

#### Scenario: Member cannot remove

- **WHEN** a member who is neither editor nor team admin requests removal
- **THEN** the request fails with 403 and the agent stays published

#### Scenario: Editor deactivates a published agent

- **WHEN** an editor deactivates a published agent
- **THEN** the critical confirmation dialog states that the agent will be removed from the marketplace, and on confirmation the agent is deactivated and removed

#### Scenario: Capability revoked

- **WHEN** a platform admin prepares to revoke a capability used by two published agents of a team
- **THEN** the confirmation states that 2 agents will be removed from the marketplace, and on confirmation they are suspended and removed

#### Scenario: Team made private

- **WHEN** a team admin changes a public team with 3 published agents to private
- **THEN** the confirmation states that 3 agents will be removed from the marketplace, and on confirmation they are removed

### Requirement: Removed state shows why until hidden or published again

After an automatic removal or a platform admin's removal, the bar SHALL show the Removed state. A removal by anyone in the team (an editor or the team admin) SHALL show no Removed state. The popover's "Hide" SHALL clear the state for everyone in the team and SHALL be offered only to editors and the team admin. No banner SHALL appear in the agent form. Publishing again SHALL return the bar to Published.

#### Scenario: Suspended agent

- **WHEN** a published agent is suspended because a capability was revoked
- **THEN** its bar shows Removed, and the popover shows the reason and the date

#### Scenario: Editor hides the state

- **WHEN** an editor or the team admin chooses "Hide" in the popover
- **THEN** the Removed state disappears for every member of the team, and the likes and imports of the entry are kept

#### Scenario: Member cannot hide

- **WHEN** a member who is neither editor nor team admin opens the popover
- **THEN** no "Hide" button is shown and a direct request fails with 403

#### Scenario: Removal by the team

- **WHEN** an editor or the team admin removes an entry
- **THEN** the bar shows no Removed state

### Requirement: Concurrent marketplace changes do not overwrite each other

Publishing, republishing and removing the same entry SHALL be serialized and checked against the entry version the caller saw. A request based on an outdated version MUST fail with 409, and the card SHALL refresh.

#### Scenario: Republish and remove at the same time

- **WHEN** two editors send a republication and a removal based on the same entry version
- **THEN** the first one applies, the second fails with 409, and the second editor's card shows the current state

### Requirement: Marketplace page lists published snapshots

Every authenticated user SHALL be able to list the agents marketplace, newest first by first publication date (a republication does not change the order), with a text search that also matches team names, and a team filter set by clicking a card's team name and removable from a chip. Each card SHALL be a marketplace variant of the agent card, without chat, enable toggle or more menu, showing the snapshot's name, description and publishing team, plus the shared bottom bar with a Like button and total counter (pressed when the user already likes it), an Import icon and counter, and "Updated on <date>" (the current version's publication date). The author SHALL be the team only, with its current name; no person is shown. The page SHALL show an explanatory empty state when there is no agent and when no agent matches the search.

#### Scenario: Any user lists the marketplace

- **WHEN** an authenticated user who belongs to no publishing team opens the agents marketplace
- **THEN** every published snapshot is listed, newest first

#### Scenario: Search without result

- **WHEN** a search matches no agent
- **THEN** the page shows the no-result empty state with a short explanation

#### Scenario: Renamed team

- **WHEN** a publishing team is renamed
- **THEN** its entries show the new name

### Requirement: Likes belong to a version, imports accumulate

A user SHALL be able to like a published entry once, without importing it and including their own team's entries, and to remove their like. The Like button SHALL show a pressed state (`aria-pressed`, filled icon) when the user likes the entry. Each like SHALL record the publication version it was given on and when; each successful import SHALL be recorded per destination with its version and date. Removing a like MUST NOT erase its history. The card SHALL show the total likes; the detail SHALL show "N likes, including M since the update of <date>". The import count SHALL be cumulative across versions. Likes and imports SHALL be kept when the entry is removed or republished, and deleted only with the agent.

#### Scenario: Toggle like

- **WHEN** a user likes an entry and then clicks Like again
- **THEN** the total increases by one, then returns to its previous value

#### Scenario: Likes since the update

- **WHEN** an entry has 4 likes from its first version and is republished, then liked by 1 more user
- **THEN** the card shows 5 likes and the detail shows "5 likes, including 1 since the update of <date>"

#### Scenario: Counters survive removal

- **WHEN** an entry with 4 likes and 7 imports is removed and later republished
- **THEN** it shows 4 likes and 7 imports

### Requirement: Marketplace agents are read-only

A marketplace agent SHALL only be viewed and imported: no chat, change or file download. The control-plane MUST NOT expose any endpoint that returns a snapshot file's content. The detail SHALL be a read-only summary: identity (name, description, icon, team), what it can do (capabilities in plain language), instructions, configuration files (name and size), counters, and an Import action.

#### Scenario: Detail returns file metadata only

- **WHEN** a user opens the detail of an entry that holds a configuration file
- **THEN** the response and the summary show the file's name and size, and no content or download link

#### Scenario: Import is the only action

- **WHEN** a user views an entry's detail
- **THEN** no chat, edit or download action is offered

### Requirement: Import copies a snapshot into the caller's spaces

A user SHALL be able to import a published snapshot into one or more destinations: their personal space and the teams where they can update agents, except the entry's publishing team. Before confirmation, the import dialog SHALL list in plain language, per destination, the capabilities the agent will lose there. Each destination SHALL be handled on its own. A destination where the template is not enabled MUST be refused; capabilities the destination cannot use SHALL be dropped. The imported agent SHALL keep the snapshot's name when it is free in the destination, otherwise take the first free `<name> (<word> <n>)` name, n from 1, `<word>` being `copie` for a French UI and `copy` for an English one. The dialog SHALL state "Your copy will be independent: updates made by <team> will not reach it." (fr: "Votre copie sera indépendante : les mises à jour de <équipe> ne lui parviendront pas.") and SHALL then show, per destination, the result and what to reconfigure (libraries, documents and the capabilities' own notices).

#### Scenario: Losses shown before confirming

- **WHEN** a user selects a destination that cannot use one of the snapshot's capabilities
- **THEN** the dialog names that capability as lost for that destination before confirmation

#### Scenario: Name kept or suffixed

- **WHEN** a user imports a snapshot into a team without an agent of that name and into a team with one
- **THEN** the first team's agent keeps the name and the second's is named `<name> (copy 1)` (`<name> (copie 1)` for a French user) or the next free number

#### Scenario: Publishing team excluded

- **WHEN** an editor of the publishing team opens the import dialog
- **THEN** the publishing team is not listed as a destination

#### Scenario: Template not enabled

- **WHEN** one destination has not enabled the snapshot's template
- **THEN** that destination is refused and the others still receive their copy

#### Scenario: Result screen

- **WHEN** an import into a team succeeds
- **THEN** the dialog shows "Imported into <team>" and lists what to reconfigure there

### Requirement: Platform admin sets agents marketplace settings with a default and team overrides

A platform admin SHALL be able, in an admin "Marketplaces" section, to set a default "publication enabled" switch (off unless changed) and a default agents quota (5 unless changed), which every team without an override follows, including teams created later. For each team the admin SHALL be able to override the switch, the quota, or both, and to put the team back to Default. A quota MUST be an integer of at least 1. Team members, including the team admin, MUST NOT change these settings. For each team the section SHALL show the published agents count. A quota lowered below a team's published count SHALL keep the existing entries and block new publications. Whenever a change turns a team's effective switch from on to off (team override, back to Default, or the default itself), the team's published agents SHALL be removed; the confirmation MUST state how many, summed over the affected teams. When that count is zero the change SHALL apply without confirmation; when it cannot be previewed, it SHALL still be confirmed.

#### Scenario: Defaults

- **WHEN** a platform admin opens the section on a platform where nothing was ever set
- **THEN** the default switch is off, the default quota is 5, and every team follows Default

#### Scenario: Invalid quota

- **WHEN** a platform admin saves an empty quota or a quota below 1, as default or as override
- **THEN** the save is refused

#### Scenario: Team override and back to Default

- **WHEN** a platform admin overrides a team's quota to 3 and later puts it back to Default
- **THEN** the team's quota is 3, then follows the default again

#### Scenario: Future team follows the default

- **WHEN** default publication is enabled and a new team is created
- **THEN** publication is enabled for the new team without any override

#### Scenario: Team admin cannot change settings

- **WHEN** a team admin who is not a platform admin requests a change of the team's marketplace settings
- **THEN** the request fails with 403

#### Scenario: Default publication disabled

- **WHEN** a platform admin disables default publication while two teams follow Default with 3 published agents in total, and confirms "3 agents will be removed from the marketplace"
- **THEN** those entries are removed, the teams' members keep their roles, and teams overridden to on are unchanged

#### Scenario: Nothing to remove

- **WHEN** a platform admin disables publication for a team with no published agent
- **THEN** the change applies without a confirmation
