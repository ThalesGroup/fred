## Decisions

- **Swift logic stays.** Only Weaver's visual and structural UI is ported; Weaver-only code (organizations, upload receipts, retry) is left out.
- **Pages opt out of the card through data attributes.** `data-shell-inset="none"` removes the card padding, `data-shell-card="none"` removes the card itself for pages that draw their own cards (chat, hosted applications).
- **Attachment chips change their look only.** File-type icon, colour per status, status on a second line, task detail on hover; swift's upload pipeline is unchanged.
