## Why

Each admission condition currently stacks a selected-path summary, a full-width picker button and every input. This makes short conditions unnecessarily tall and obscures multi-condition rules.

## What Changes

- Display field selection, comparison and operand together on desktop, with responsive stacking.
- Use a left-aligned account-field dropdown with direct root-text selection and an entry for the detailed session explorer.
- After field confirmation, ask in a separate popup whether to use the current verified account value or retain the entered operand.
- Keep a small case-sensitive toggle directly visible; remove manual path entry while retaining exact selection in the explorer.
- Use an accessible condition-specific removal icon, preserve at least one condition, and separate adding a condition from testing/saving.
- Hide operand counters until 90% of the existing limit, without hiding validation errors or changing input limits.

- Add a persisted allow/block mode at the top of the editor. Existing policies default to allow; block mode permits nonmatches, including missing/empty/incompatible claims. Independent user and team sources remain sufficient.
- Make preview outcomes readable with green/red semantic accents and a larger access-result heading.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-access-control`: compact, responsive and accessible admission condition editing.

## Impact

Frontend rule editor, its layout/translations and tests, an opt-in shared TextInput counter control, and existing UX guidance. The mode extends the shared policy contract and admission evaluation without new deployment configuration or migration. Delivery continues on issue #2965 and PR #2966. The developer approved this scope and the interactive proposal before implementation.
