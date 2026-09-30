## Context

See `proposal.md` for the user outcome. The merged occurrence contract identifies a tool-raised pause with the raising `tool_call_id`; runtime admission validates `(interrupt_id, occurrence_id)` and history pairs plural requests and responses. ReAct and Deep both call `ReActRuntimeToolResolver` and `ReActToolBinder`, then compose the platform middleware frame. The current `HitlPrompt` submits a choice or text, never both, and `_write_turn_history` writes no response row when a resume has neither value. These are the two frontend and persistence gaps the skip path exposes.

## Goals / Non-Goals

**Goals:**

- Mount one pure question tool in the shared ReAct/Deep tool path and return a deterministic answer to the matching tool call.
- Keep malformed answers retryable by validating them before the single-use resume claim starts.
- Preserve a skipped decision in durable history so reload does not resurrect its prompt.

**Non-Goals:**

- Refactor the approval gate or implement its comment field and card redesign; those belong to change 3.
- Add question expiry, a per-turn question cap, sub-agent waits, or a Graph LLM-facing `ask_user` tool.

## Decisions

### Mount through the shared runtime tool path

Add a platform `ask_user` spec to `ReActRuntimeToolResolver` only when `RuntimeContext.ask_user` is explicitly true. Its schema exposes `question`, `choices`, and `allow_free_text`; a LangChain-injected tool call id is hidden from the model and becomes `HumanInputRequest.occurrence_id`. `ReActToolBinder` keeps the existing tracing and `ToolMessage` pairing. A runtime-name collision with a capability or provider tool fails during resolution instead of silently replacing either tool. A dedicated tool that calls `interrupt()` before any external effect is replay safe; pausing inside an arbitrary business tool is not.

The alternative of a capability-owned question tool would require every agent author to opt in and would not deliver the epic's default availability. A second tool binder for Deep would risk parity drift.

### Bound and describe choices

`AskUserArgs.choices` has a maximum of four entries. Its model-facing schema and tool description ask the agent to select the most relevant options before calling; a longer call fails validation before any pause, rather than dropping choices. The limit belongs to `ask_user`, not the shared human-input request used by other HITL flows. Managed chat renders each optional choice description below its label within the same selectable button; buttons grow to fit the text.

### Use one answer shape for the tool and Graph helper

The resumed value is an object with `choice_id`, `text`, or `skipped: true`. The tool returns a stable JSON result: `{"status":"answered","choice_id":...,"text":...}` with absent values omitted, or `{"status":"skipped"}`. It validates the selected id against its own offered options and never turns typed text into an option id. A shared SDK parser yields a typed answer; Graph's existing `choice_step()` remains a compatibility wrapper returning `str | None`, while a new helper exposes the complete answer for new Graph callers. Existing bare-string Graph resumes remain readable.

Admission validates the pending `agent_question` prompt and answer before acquiring the single-use claim. An invalid option, a blank required text answer, or a mixed skip and answer is refused while the pause stays pending. The tool also validates defensively after `interrupt()` returns. Tool-approval prompts keep their current `proceed`/`cancel` parser.

Returning a plain answer string was rejected because a choice plus comment and a skip would be ambiguous to the model and to history.

### Keep answer identity and history truthful

The platform sets `stage="agent_question"` on the request; the model cannot set it. The frontend uses this stage to show the skip action only for agent questions. It sends a selected id and optional text together. A skip sends only `{"skipped":true}`. Add an optional `skipped` flag to `HitlResponsePart` and persist a response row even when choice and text are absent. History reconstruction treats that row as the answer to its `occurrence_id` and renders a localized skipped response. JSONB parts need no database migration; old rows load with `skipped=false`.

Reusing `cancel` for skip was rejected: cancel belongs to the tool approval gate, whereas an unanswered business question is a normal result the agent may reason about.

### Apply the composer switch to new turns

Control plane appends a platform-owned `ask_user_toggle` descriptor at prepare-execution with `params.default=true`, alongside the reasoning control. The frontend stores the toggle per session and sends `RuntimeContext.ask_user` only when the control is offered. `None` means no interactive control and does not mount the tool; `false` means the person disabled future questions. A pending `agent_question` resume keeps the tool available to finish that turn even if the composer switch is now off; the switch applies to the next new turn. This follows the existing per-session control transport while avoiding a stranded checkpoint.

An always-mounted tool with an "unavailable" result was rejected because a model could repeatedly waste calls outside chat. Removing a tool in the middle of a pending resume was rejected because it would make an already displayed question unanswerable.

## Risks / Trade-offs

- Agent-authored question and option text can reflect untrusted source content and may resemble a platform instruction. The epic accepts this risk and reuses shared HITL visuals. This change must preserve text rendering without HTML interpretation; the larger visual redesign remains change 3.
- A default-on question tool can prolong a turn indefinitely. The existing lifecycle work owns expiry, recovery, and any question cap; this change adds no implicit timeout that would discard a pending answer.
- The shared binder may not pass an injected call id through its current `args_schema` wrapper. Before broad implementation, a focused installed-LangGraph test must prove the id reaches the tool and remains stable across replay. If that seam fails, keep one shared ReAct/Deep binding path and revise this design before writing a separate executor branch.

## Migration Plan

The new runtime context field and response flag are optional. Older clients send no `ask_user` flag, so no tool is mounted. Existing approval prompts and persisted rows keep their current behavior. Deploy SDK/runtime and control plane before exposing the composer control; roll back by withdrawing the control and leaving pending questions answerable on resume until resolved. Regenerate backend OpenAPI and frontend clients with the contract change, and write the required operator migration note.
