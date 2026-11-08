## Why

The Weaver branch reworked the application shell and the chat layout. Swift users should get the same interface without Weaver's backend model.

Issue: #3484

## What Changes

- Pages render in one `surface-main` card on a `surface-container` background; navigation adapts to the input device; opened menus, dialogs and drawers take focus and give it back.
- Shared visual refinements: overlay blur, compact icon buttons, design tokens instead of raw radii and font sizes, clearer icons, theme-aware text selection.
- Chat: separate chat and viewer cards, a launcher rail outside them, a foldable navigation panel, half-width viewers and condensed attachment chips.

## Impact

Frontend only (`apps/frontend`), no API or configuration change. Two independent-to-review PRs: shell, then chat.
