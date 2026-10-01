## Context

See proposal.md. `AskUserArgs` already rejects more than four choices. `ask_user` creates the `HumanInputRequest`, whose `free_text` value controls both resume validation and the rendered card. The ReAct event bridge retains a failed tool result for final-answer safety, but currently also emits that result after a later HITL interrupt. Managed chat renders choices and a separate `TextArea` from the request fields.

## Goals / Non-Goals

**Goals:** Keep the request and UI aligned, preserve choice-plus-comment answers, and ensure a paused turn has no stale final answer.

**Non-Goals:** Raise the four-choice limit, change tool approval cards, or change the HITL wire schema.

## Decisions

1. In `ask_user`, make `HumanInputRequest.free_text` true whenever there are at least two choices. Keep the model argument for zero- and one-choice questions. This also makes stored pause state and server-side answer validation agree. Merely showing an input in the frontend would create a text answer that the backend rejects.
2. For agent questions with choices and free text, render a labeled text input as the last row inside the choice column, with a fixed gray "Other" / "Autre" label beside the editable area. Match the choice outline, width and height with scoped CSS, and render the question through the shared sanitized `MarkdownRenderer`. Keep the Send action and existing optional comment behavior when an option is selected. Text-only questions retain the multiline `TextArea`; approval cards are unchanged.
3. Track whether a valid human interrupt was emitted during a ReAct stream. Finish collecting stream metadata and sibling events, but omit `FinalRuntimeEvent` for the paused turn. This leaves ordinary all-failed tool rounds on the current safe-error path.

## Risks / Trade-offs

- A single-line field is less spacious for long answers. Keep its full value and input length check; the text-only form remains multiline.
- Pauses persisted before the change may have `free_text=false`. Render from the persisted request so their UI only offers answer forms the checkpoint accepts. New multiple-choice pauses always carry `free_text=true`.

## Migration Plan

Normal runtime and frontend deployment is sufficient. Existing checkpoints keep their stored answer form. Rollback restores the previous question presentation and choice policy; no data migration is required.
