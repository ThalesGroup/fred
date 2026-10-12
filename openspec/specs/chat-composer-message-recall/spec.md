# chat-composer-message-recall Specification

## Purpose
Let a person bring back a message they already sent in the current conversation into the chat composer with the arrow keys, to resend or adjust it without retyping.

## Requirements

### Requirement: Arrow keys recall sent messages of the current conversation

The chat composer SHALL let the person browse the messages they sent in the current conversation with ArrowUp and ArrowDown. Browsing SHALL start only from an empty composer whose `/` command menu is closed, and SHALL continue while the composer still shows a recalled message unchanged and the menu stays closed. ArrowUp SHALL show the previous sent message, from the newest to the oldest; ArrowDown SHALL show the next one, and ArrowDown past the newest SHALL empty the composer. The caret SHALL be placed at the end of the recalled text. Consecutive identical messages SHALL be recalled once. The list SHALL come from the conversation shown on the page and SHALL NOT be stored in the browser.

#### Scenario: Recall the last message
- **WHEN** the composer is empty, the command menu is closed and the person has sent "Summarize the report" then "Translate it to French" in this conversation
- **AND** the person presses ArrowUp
- **THEN** the composer shows "Translate it to French" with the caret at the end

#### Scenario: Go back and forth
- **WHEN** the composer shows the recalled "Translate it to French" unchanged
- **AND** the person presses ArrowUp, then ArrowDown, then ArrowDown again
- **THEN** the composer shows "Summarize the report", then "Translate it to French", then is empty

#### Scenario: Oldest message reached
- **WHEN** the composer shows the oldest sent message unchanged
- **AND** the person presses ArrowUp
- **THEN** the composer keeps showing the oldest message

#### Scenario: Nothing to recall
- **WHEN** the conversation has no sent message, or the person presses ArrowDown in an empty composer
- **THEN** the composer stays empty and the key has no other effect

#### Scenario: Another conversation
- **WHEN** the person opens another conversation and presses ArrowUp in its empty composer
- **THEN** only messages sent in that conversation are recalled

### Requirement: Recall stays out of the way of editing

The arrow keys SHALL keep their usual caret behaviour whenever the composer holds text that is not an unchanged recalled message, whenever the `/` command menu is open, and whenever a modifier key (Shift, Ctrl, Alt, Meta) is held or a text composition (IME) is in progress. A disabled composer SHALL NOT recall anything.

#### Scenario: Edited recalled text
- **WHEN** the person recalls "Translate it to French" and types " please"
- **AND** presses ArrowUp
- **THEN** the caret moves within the text and the composer content is unchanged

#### Scenario: Draft in progress
- **WHEN** the composer holds a draft the person typed
- **AND** the person presses ArrowUp
- **THEN** the caret moves within the draft and no message is recalled

#### Scenario: Command menu open
- **WHEN** the person types `/` and the command menu lists entries
- **AND** presses ArrowUp
- **THEN** the menu moves its highlight and no message is recalled

### Requirement: Command messages are recalled as typed

A message sent through a `/command` SHALL be recalled as the line the person typed: `/` followed by the command name, then a space and the appended text when there was any. It SHALL NOT be recalled as the expanded prompt. The command menu SHALL open only on text the person typed: a recalled line SHALL NOT open it, and the first keyboard edit of that line SHALL let it open as usual. Only the message text SHALL be recalled; attachments and turn options SHALL stay as they are.

#### Scenario: Command with appended text
- **WHEN** the person sent `/summary focus on risks`, where `/summary` expands to a library prompt
- **AND** recalls it with ArrowUp
- **THEN** the composer shows `/summary focus on risks`, not the prompt text

#### Scenario: Command alone
- **WHEN** the person sent `/summary` with nothing after it
- **AND** recalls it with ArrowUp
- **THEN** the composer shows `/summary`

#### Scenario: A recalled command does not open the menu
- **WHEN** the person recalls `/summary`
- **THEN** the command menu stays closed and ArrowUp keeps recalling earlier messages

#### Scenario: Typing on a recalled command opens the menu
- **WHEN** the composer shows the recalled `/summary`
- **AND** the person deletes its last character with Backspace
- **THEN** the command menu opens on `/summar` as it does for typed text

#### Scenario: Attachments not recalled
- **WHEN** the recalled message was sent with an attached file
- **THEN** only its text appears in the composer and the current attachments are unchanged
