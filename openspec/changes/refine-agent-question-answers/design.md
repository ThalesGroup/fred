## Context

See proposal.md. `AskUserArgs` already rejects more than four choices. `ask_user` creates the `HumanInputRequest`, whose `free_text` value controls both resume validation and the rendered card. The ReAct event bridge retains a failed tool result for final-answer safety, but currently also emits that result after a later HITL interrupt. Managed chat renders choices and a separate `TextArea` from the request fields.

## Goals / Non-Goals

**Goals:** Keep the request and UI aligned, preserve choice-plus-comment answers, and ensure a paused turn has no stale final answer.

**Non-Goals:** Raise the four-choice limit, change tool approval cards, or change the HITL answer payload schema.

## Decisions

1. In `ask_user`, make `HumanInputRequest.free_text` true whenever there are at least two choices. Keep the model argument for zero- and one-choice questions. This also makes stored pause state and server-side answer validation agree. Merely showing an input in the frontend would create a text answer that the backend rejects.
2. For agent questions with choices and free text, render a labeled text input as the last row inside the choice column, with a fixed gray "Other" / "Autre" label beside the editable area. Match the choice outline, width and height with scoped CSS, and render the question through the shared sanitized `MarkdownRenderer`. Keep the Send action and existing optional comment behavior when an option is selected. Text-only questions retain the multiline `TextArea`; approval cards are unchanged.
3. Track whether a valid human interrupt was emitted during a ReAct stream. Omit `FinalRuntimeEvent` for the paused turn so a prior failed tool cannot become its answer. After collecting sibling updates, attach accumulated sources, UI parts, model usage, and context size once to `AwaitingHumanRuntimeEvent`; persist them on a metadata-only row before request deduplication and combine them with the resumed final in managed chat. Continue reading older request rows that already carry metadata. The pause keeps no answer content. Ordinary all-failed tool rounds retain their safe-error path.

4. Mistral completed-message recovery still requires the exact typed reference marker, a registered tool name, bounded content, and validation of every call. Validate the public `tool_call_schema` first, rejecting model-supplied injected fields, then the full input schema with a temporary `tool_call_id` so question-level validators still run. Reject recovery for other hidden fields. Permit literal CR/LF inside quoted JSON strings while rejecting other raw control characters. Keep unmarked text and other malformed JSON ineligible for recovery.

## Risks / Trade-offs

- A single-line field is less spacious for long answers. Keep its full value and input length check; the text-only form remains multiline.
- Pauses persisted before the change may have `free_text=false`. Render from the persisted request so their UI only offers answer forms the checkpoint accepts. New multiple-choice pauses always carry `free_text=true`.
- The saved history flattens provider content, and no local trace store is available for the reported exchange. Tests reconstruct the typed-marker content shape and verify both ReAct and Deep routing after a prior answer.

## Migration Plan

Normal runtime and frontend deployment is sufficient. Existing checkpoints keep their stored answer form. Rollback restores the previous question presentation and choice policy; no data migration is required.
