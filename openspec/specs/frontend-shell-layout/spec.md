# frontend-shell-layout Specification

## Purpose
How the application shell lays out pages and the chat: one surface card per page, focus handoff to opened surfaces, the chat and viewer cards with their launcher rail, and attachment chip status.

## Requirements

### Requirement: Pages in one surface card

The frontend SHALL render each page inside one `surface-main` card on a `surface-container` background, scrolling inside the card, unless the page opts out with `data-shell-inset="none"` or `data-shell-card="none"`.

#### Scenario: Long content scrolls inside the card

- **WHEN** a page's content is taller than the window
- **THEN** only the card's content scrolls and the navigation stays in place

### Requirement: Focus follows opened surfaces

A menu, dialog or drawer opened from the keyboard SHALL receive focus, and SHALL return it to its trigger when closed.

#### Scenario: Escape returns focus

- **WHEN** a user opens the profile menu from the keyboard and presses Escape
- **THEN** focus is back on the profile button

### Requirement: Chat cards and launcher rail

The chat page SHALL show the conversation and an open viewer in separate cards, with the launcher rail outside them, and SHALL fold the navigation panel when a viewer opens only if the chat body is narrower than 900px.

#### Scenario: Wide screen keeps the navigation panel

- **WHEN** a viewer opens while the chat body is at least 900px wide
- **THEN** the navigation panel stays open and the viewer takes half of the chat body

### Requirement: Attachment chip status

An attachment chip SHALL show its file-type icon, a colour for its status, its ingestion status under the name, and the task detail on hover or keyboard focus without an acknowledge action.

#### Scenario: Failed ingestion

- **WHEN** the user hovers the status of a failed attachment
- **THEN** the failure detail appears next to the chip and offers no acknowledge button
