## Context

The existing editor creates a blank condition for a null policy and immediately appends another blank on Add. Its account-field Select can open an existing own-session JSON picker indirectly. That picker already defaults to root text fields, supports a separate observed-name source and limits values to the current verified administrator. The editor already has a versioned save mutation, but its action and generic feedback appear below the condition list. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:** make creation and persistence explicit while preserving exact paths, bounded predicates, draft revision conflicts and actor safeguards.

**Non-Goals:** changing admission evaluation, enabling filtering automatically, clearing a stored policy with an empty draft, changing invitation administration, or introducing another token/policy endpoint.

## Decisions

- Reuse PlatformAccessClaimPicker directly for add and edit, with distinct pending-add/edit context. Keep the blue JSON keys and root-text default. Append only on confirmation, then reuse PlatformAccessValuePrompt. Canceling a picker performs no draft mutation; canceling optional value reuse keeps the already confirmed field.
- Load null policies with zero local conditions; saved policies retain their actual list. Allow removing the last local condition, but keep Test/Save disabled for empty drafts and explain the nonempty requirement. Backend validation and activation remain authoritative. Keeping a fabricated row would defeat the requested creation flow; treating an empty list as an authorization policy would change security semantics.
- Replace only the account-field Select with readable path text and an accessible edit icon. Keep comparison and allow/block selectors and global AND/OR, with the existing visible case switch. Own values stay modal-only rather than being copied into field labels.
- Move the existing filled Save rule control into a responsive editor header near the title, with an unsaved/saving/saved status and persistence hint. Keep preview and discard/reload as separate draft actions. Use the existing save handler and returned revision; do not introduce autosave or a second persistence path. Page filtering/user/team switches retain their existing immediate behavior and are distinguished from rule drafts.
- Freeze adoption of background policy refresh while field selection is pending, retaining the original revision for confirmation/save. Cancel releases the modal and can adopt newer server state. Preserve generation invalidation and existing dirty-draft conflict handling.
- Reuse home-page ButtonGroup with tab semantics and associated panels for Rules, Users, Teams and links, and Activation. Keep the rule editor mounted in a hidden panel so navigation does not discard its draft; keep selection and paging in the page owner. Put T0 import with Users and the existing filtering control in the final Activation view. The population dry run is a separate pending refinement; this presentation change does not invent population classifications or change activation safeguards.
- Use existing typography tokens: body-large for ordinary content, body-medium for secondary explanations, title-large for section headings and title-medium for condition headings. Apply the same scale to portaled picker/value/link content. Remove repeated discovery explanation from the editor because the picker already describes its observed source; keep exception, delegated-evidence, revocation, validation and error guidance.

## Risks / Trade-offs

- An empty local draft could look like admission was cleared: show an explicit draft-empty message, block Test/Save, and retain the stored policy until a valid save succeeds.
- Picker cancellation or background refresh could add an unintended row or overwrite edits: cover add/edit cancellation and revision races with focused regression tests.
- Own-token screenshots may contain personal values: use real local accounts and crop/mask personal fields; keep generic claims and no tokens/credentials in public artifacts.

## Migration Plan

Deploy or roll back the frontend normally. Update the existing operator note to record no new operator action; there is no new migration or backend/configuration change.
