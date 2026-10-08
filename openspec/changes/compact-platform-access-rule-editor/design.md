## Context

See proposal.md for motivation. The existing editor already owns bounded conditions, asynchronous preview/save, revision conflicts and exact path editing. Shared Fred controls and theme tokens must remain authoritative.

## Goals / Non-Goals

**Goals:** improve condition scanning and responsive layout while retaining all editing and feedback semantics.

**Non-Goals:** change preview identity, picker projection, token handling, resource authorization or deployment configuration.

## Decisions

- Use three layout columns on desktop. On narrower screens put the field above comparison/operand, then stack all three when necessary. Reuse shared Select and TextInput rather than introduce custom controls. Use container width for reflow because the navigation consumes viewport space.
- Replace the duplicate selected-path paragraph and picker button with the shared text dropdown. Offer observed root string attributes through the existing metadata exclusion policy, preserve any selected literal path, and retain the detailed session explorer as a menu entry.
- Confirm current-value reuse in a separate dialog using only the current actor's verified bounded claims, never catalog values. Keep the existing operand when declined; escape regex literals and enforce operand limits before copying.
- Keep a small case toggle directly visible. Remove manual path entry; the detailed explorer retains exact nested and literal dotted-key selection.
- Use localized all/any choices, condition-specific removal labels and a separate add action. Keep test/save/reload together below the list.
- Add an opt-in TextInput counter visibility flag, defaulting to existing behavior. The editor shows the operand counter at 90% of its existing limit; compact mode removes an empty hint row only when no error is present.

- Show a green/red result panel based on effective admission, with a larger heading and a separate condition-match explanation.

## Risks / Trade-offs

- Long keys or narrow viewports could overflow: verify actual layout, full accessible names and stacking at narrow available content widths. The global shell has no mobile navigation collapse; do not hide its DOM for evidence.
- Keep field confirmation and value copying separate; preserve draft-only changes and prevent unavailable or oversized examples from being copied.
- Shared input changes could affect consumers: preserve defaults and verify hidden counters retain native maxlength and error associations.
- UI changes could regress draft/concurrency semantics: leave request/state logic intact and replay the editor regression suite.
