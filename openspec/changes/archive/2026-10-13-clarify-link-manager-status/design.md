## Context

The control-plane link list already derives Suspended from the team's disabled Link access flag for links that are neither revoked nor expired. The frontend dims those rows but hides their status text, and the current platform-access-control spec explicitly requires that hidden presentation.

## Goals / Non-Goals

**Goals:** Make the disabled state understandable without changing link lifecycle behavior or existing actions.

**Non-Goals:** Add a Suspended filter, change the control-plane response, or alter invitation validity.

## Decisions

- Use the existing server-derived status and show its localized label in the Status column. Keep the existing row dimming and lifecycle filter options.
- Show one localized notice above the controls only while Link access is disabled. A notice explains the team-level cause even when the list has no active links.
- Refresh the team's Link access setting while the manager is open, so the notice and creation controls follow changes made by another administrator.
- Reuse the existing localized Joined users label for links without a note, while keeping the note-specific title for noted links. Remove the unused No note translations.

## Risks / Trade-offs

- The notice occupies some vertical space in the modal. Keep it concise and retain the bounded table height.
