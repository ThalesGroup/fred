## Why

Re-sending or adjusting an earlier message means retyping it. Terminals and most chat tools recall earlier input with the arrow keys, and Fred's composer has no equivalent. Tracked in #3038.

## What Changes

- In the managed chat composer, ArrowUp recalls the person's previous sent message of the current conversation when the composer is empty and the `/` command menu is closed. Repeated presses go further back, ArrowDown goes forward, and ArrowDown past the newest message returns to an empty composer.
- Once the recalled text is edited, the arrows move the caret again as usual.
- A message sent through a `/command` is recalled as its typed line (`/command` plus the appended text), not as the expanded prompt.
- Only the text is recalled: attachments and turn options are left as they are.
- The list comes from the conversation already loaded in the page; nothing is stored in the browser.

## Capabilities

### New Capabilities
- `chat-composer-message-recall`: recalling sent messages of the current conversation into the chat composer with the arrow keys.

### Modified Capabilities
None.

## Impact

- Frontend only: `ManagedChatPage` (a small recall hook fed by the thread's user turns) and `RichInputField` (one optional key handler, called after the command menu's).
- No backend, API or stored-data change: each user turn already carries its text and, for a command turn, the command descriptor (`command`, `appended_text`).
- Docs: `docs/swift/ux/COMPONENT-UX.md` (composer keyboard), fr/en Help Center `features/chat.md` (one short paragraph on the arrow keys).
- Migration note: impact `none`.
