## Purpose

Team wiki browsing and page editing in the frontend: how the page tree keeps its state and where a page's title, location and deletion are edited.

## ADDED Requirements

### Requirement: Tree state is remembered per user and per team
The wiki tree SHALL be fully collapsed when no state is stored for the current user and team. Expanded pages and the last opened page SHALL be stored in browser localStorage, keyed by user and kept separately for each team. No state SHALL be shared across browsers or devices.

#### Scenario: First visit
- **WHEN** a user opens a team wiki for the first time in this browser
- **THEN** every page with children is collapsed in the tree

#### Scenario: Coming back to the wiki
- **WHEN** a user expands pages, opens a page, leaves the wiki and comes back without a page in the URL
- **THEN** the same pages are expanded and the last opened page is shown

#### Scenario: Last page no longer exists
- **WHEN** the stored last page has been deleted or renamed away
- **THEN** the wiki opens on the first page of the tree

#### Scenario: Another user in the same browser
- **WHEN** a different user signs in in the same browser
- **THEN** they get their own tree state, collapsed by default

### Requirement: The open page is visible in the tree
When a page is open, its ancestors SHALL be expanded in the tree, and that expansion SHALL be remembered like a manual one.

#### Scenario: Direct link to a nested page
- **WHEN** a user opens a link to a page nested under collapsed parents
- **THEN** its parents are expanded and the page is highlighted in the tree

### Requirement: Title, location and deletion are edited in edit mode
The reading view SHALL offer no rename, move or delete action. Edit mode of an ordinary page SHALL offer an editable title, a parent page selector (root or any valid move target) and a delete icon button in the error color with a "Delete page" tooltip that asks for confirmation. Saving SHALL apply the content and, when changed, the title and parent. The rules page edit mode SHALL keep a fixed title and offer neither parent nor delete.

#### Scenario: Rename and move while editing
- **WHEN** an editor changes the title and parent in edit mode and saves
- **THEN** the page has the new title, sits under the new parent, and edit mode closes

#### Scenario: Duplicate title
- **WHEN** the new title is already used by another page
- **THEN** an error is shown, edit mode stays open and the draft is kept

#### Scenario: Delete from edit mode
- **WHEN** an editor clicks the delete icon button and confirms
- **THEN** the page is deleted and the wiki root is shown

#### Scenario: Rules page
- **WHEN** an editor edits the rules page
- **THEN** the title is not editable and no parent selector or delete button is shown
