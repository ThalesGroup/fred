## Context

The manager already has a clipboard helper for history recovery and the generated URL dialog. It preserves the URL when writing fails and shows success only after the browser confirms the write.

## Goals / Non-Goals

**Goals:** Reuse that clipboard behavior immediately after link generation, without tying unrelated dialog controls to clipboard progress.

**Non-Goals:** Change token recovery, invitation validity, or browser clipboard permissions.

## Decisions

- Finish the generation mutation and show the URL before attempting the clipboard write. Reuse the existing copy path so automatic and manual attempts have the same success feedback and fallback.
- Keep clipboard writing independent of the global generation busy state. The URL and Close action remain available while the write settles.
- Ignore clipboard completions after the result is dismissed or a newer action starts, so a delayed browser response cannot reopen an old result.
- Apply Fred's existing monospace typography token to the generated URL input only; other form fields retain their current font.

## Risks / Trade-offs

- A browser can reject a write after the network request has completed. The result dialog retains a selectable URL, reports the clipboard failure, and offers Copy URL for a user-initiated retry.
