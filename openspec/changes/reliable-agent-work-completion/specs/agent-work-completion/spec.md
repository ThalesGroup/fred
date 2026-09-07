## Purpose

Defines the observable, black-box contract a Fred agent must satisfy when given a precise, multi-step prompt over a corpus: it completes every requested step, keeps durable private working state, and returns only deliverables it actually and verifiably produced.

## ADDED Requirements

### Requirement: Retain and complete the full ordered objective
When a user prompt gives a complete, ordered, multi-step procedure, the agent SHALL retain every numbered step and requested deliverable for the duration of the task and SHALL NOT silently drop, shorten, or skip any step while completing the turn.

#### Scenario: Long-running turn does not lose the original instruction
- **GIVEN** a user prompt listing an ordered set of steps and at least two requested deliverables
- **WHEN** the agent executes multiple tool calls whose combined output is large enough that older conversation content would ordinarily be trimmed
- **THEN** every step and every requested deliverable from the original prompt is still addressed in the final answer, and none is silently omitted

#### Scenario: Partial completion is reported, not hidden
- **GIVEN** a step in the ordered procedure cannot be completed because a required input is genuinely absent
- **WHEN** the agent reaches the point where that step would be performed
- **THEN** the agent states the exact limitation for that step and continues every other unaffected step, rather than abandoning the whole task or silently omitting the step from its final answer

### Requirement: No gratuitous request for permission to continue
When the original prompt already authorizes the full ordered procedure, the agent SHALL proceed through all steps without pausing to ask whether it should continue, except where the canonical human-in-the-loop mechanism is genuinely triggered by a gated capability.

#### Scenario: Agent does not stop between authorized steps
- **GIVEN** a prompt that explicitly authorizes working through all steps without intermediate confirmation
- **WHEN** the agent completes one step and the next step does not require capability approval
- **THEN** the agent proceeds directly to the next step instead of asking the user whether to continue

#### Scenario: Genuine approval gate still pauses correctly
- **GIVEN** the same fully-authorizing prompt
- **WHEN** a step invokes a capability that requires human approval under the existing human-in-the-loop mechanism
- **THEN** the agent pauses using that existing mechanism only, and does not invent a second confirmation step of its own

### Requirement: Explicit continuation or re-planning after a recoverable tool failure
After a tool call fails in a recoverable way, the agent SHALL either retry with corrected input, continue with the remaining unaffected steps, or explicitly report the failure as a distinct limitation — and SHALL NOT treat a recoverable tool failure as reason to abandon the rest of the ordered objective.

#### Scenario: Recoverable failure does not stop the whole task
- **GIVEN** an ordered multi-step task is in progress
- **WHEN** one step's tool call fails in a way that does not affect the inputs of later steps
- **THEN** the agent continues the remaining steps and reports the one failure explicitly in its final answer, rather than ending the turn early or silently continuing as if that step had succeeded

#### Scenario: Resume after an approval pause continues the same plan
- **GIVEN** an ordered multi-step task pauses on a human-in-the-loop approval mid-way through
- **WHEN** the human approves and the turn resumes
- **THEN** the agent continues the same ordered objective from where it paused, rather than restarting the task from the beginning or losing track of already-completed steps

### Requirement: Untrusted tool failures never leak raw exception text or wrapper content
When a tool call's only failure signal is `status == "error"` without Fred's own typed,
user-facing error result, the agent SHALL present only a bounded, generic failure message
for that call, and SHALL NOT surface the underlying exception representation, any
LLM-directed instruction, path, URL, token, or other raw wrapper content — in either the
per-call tool result or the final answer.

#### Scenario: An untyped tool failure exposes only a generic message
- **GIVEN** a tool call fails and produces only a raw, uncaught-exception representation
  with no typed, user-facing Fred error result
- **WHEN** the agent reports that failure, in the per-call tool result and, if it carries
  the failure, the final answer
- **THEN** both expose only the bounded generic failure message, and neither contains the
  exception text, any secret, token, path, or wrapper-specific instruction from the
  underlying representation

#### Scenario: A typed Fred error result may still be shown
- **GIVEN** a tool call fails and produces Fred's own typed, user-facing error result
- **WHEN** the agent reports that failure
- **THEN** the agent may present that result's rendered error text, with Fred's internal
  presentation prefix removed

#### Scenario: A typed error result is shown even when raw message content differs
- **GIVEN** a tool call fails with a typed, user-facing Fred error result present, and the
  underlying message's raw content is a different, more sensitive string than that
  result's own rendered text
- **WHEN** the agent reports that failure
- **THEN** both the per-call tool result and the final answer present only the typed
  result's own rendered text, and never the raw message content

### Requirement: Durable private working state across turns
The agent SHALL be able to persist private working/planning material (such as notes, an extracted checklist, or intermediate findings) so that the same authorized agent binding can read it back in a later turn, without exposing the model's private reasoning as the basis for that persistence or as an oracle for whether the task succeeded.

#### Scenario: Private working file survives to a later turn
- **GIVEN** the agent writes a private working file while performing a multi-step task
- **WHEN** a later turn in the same authorized session, team, user, and agent-instance context asks the agent to continue
- **THEN** the agent can read back the previously written private working file and continue the task using its content

#### Scenario: Chain-of-thought is not the completion oracle
- **GIVEN** the agent produces internal reasoning while working through a task
- **WHEN** the task's completion is evaluated
- **THEN** completion is judged only by the durable private working state, the tool/file evidence, and the final answer — never by inspecting or requiring persistence of the model's private chain-of-thought

### Requirement: User deliverables are real, verified files
The agent SHALL present a file to the user as a deliverable only after a write operation for that file has actually succeeded, and only through a durable, Fred-authorized reference that resolves to that written content.

#### Scenario: A deliverable is only claimed after a verified write
- **GIVEN** the agent is asked to generate and return a downloadable file
- **WHEN** the underlying write operation completes successfully
- **THEN** the agent's final answer includes a reference to that file only after receiving confirmation the write succeeded, and that reference resolves to the actual written content

#### Scenario: A filename in prose is never sufficient
- **GIVEN** the agent describes a file it intends to produce
- **WHEN** the agent has not received confirmation that the corresponding write succeeded
- **THEN** the agent's final answer SHALL NOT present that filename, a synthetic download URL, or any other unverified reference as if the file already exists

### Requirement: Truthful behavior on generation, write, or link failure
When file generation, a write operation, or link creation fails, the agent SHALL report the failure explicitly and SHALL NOT fabricate a filename, a download link, an attachment, or any other success claim for that failed operation, while still completing and returning results for every other unaffected part of the task.

#### Scenario: A failed write yields no fabricated link
- **GIVEN** a write operation for a requested deliverable fails
- **WHEN** the agent produces its final answer
- **THEN** the final answer states that the deliverable could not be produced and why, and contains no link, filename, or attachment reference for that failed deliverable

#### Scenario: One failed deliverable does not block the others
- **GIVEN** a task requests two deliverables and only one fails to write
- **WHEN** the agent produces its final answer
- **THEN** the successfully written deliverable is presented with its verified reference, and the failed one is reported as a stated limitation, in the same answer

### Requirement: Deliverables survive history persistence and reload
A deliverable reference presented to the user SHALL remain present and resolvable after the conversation is persisted and later reloaded (for example after a page reload), not only while the answer is being streamed live.

#### Scenario: Reload preserves the deliverable reference
- **GIVEN** the agent's final answer includes a reference to a successfully written deliverable
- **WHEN** the conversation is reloaded from persisted history in a later session
- **THEN** the same deliverable reference is present in the reloaded conversation and still resolves to the file

### Requirement: Source-grounded answers with honest gap reporting
When the task requires extracting or comparing facts found in the corpus, the agent SHALL attribute claims to the retrieved sources that support them, and SHALL report a required fact as missing rather than inventing a plausible value when the corpus does not actually contain supporting evidence for it.

#### Scenario: Claims are attributed to retrieved sources
- **GIVEN** the agent extracts a fact used in its final answer
- **WHEN** that fact is presented to the user
- **THEN** it is attributed to the corpus source(s) that actually support it

#### Scenario: A genuine evidence gap is reported, not filled
- **GIVEN** the corpus does not contain evidence for a fact the task asks the agent to determine
- **WHEN** the agent produces its final answer
- **THEN** the agent explicitly reports that evidence as missing rather than inventing a value to fill the gap

### Requirement: ReAct is the mandatory initial supported runtime
The agent-work-completion contract defined by this capability SHALL hold for the existing supported ReAct agent runtime without requiring any other runtime to be enabled.

#### Scenario: The contract is provable on ReAct alone
- **GIVEN** a deployment with only the existing supported ReAct agent runtime enabled
- **WHEN** the reference multi-step corpus scenario is run against it
- **THEN** every requirement in this capability can be verified without enabling any other agent runtime

### Requirement: Identical black-box expectations extend to Deep Agents when supported
If and when a Deep Agents runtime is separately made a supported profile for a deployment, it SHALL be held to the same observable requirements defined in this capability — objective retention, no gratuitous continuation prompts, truthful failure behavior, durable private state, and verified deliverables — evaluated the same way as for ReAct, without introducing a second, different public contract.

#### Scenario: Deep Agents reuses the same acceptance scenario
- **GIVEN** a deployment where Deep Agents is enabled as a supported profile
- **WHEN** the same reference multi-step corpus scenario used to verify ReAct is run against the Deep Agents runtime
- **THEN** it is evaluated against the same requirements and scenarios defined in this capability, with no separate or weaker Deep-specific acceptance contract

### Requirement: Bounded reliability across repeated runs
Under a fixed, supported model and agent configuration, the agent-work-completion contract SHALL hold with a stated minimum success rate across repeated runs of the reference scenario, and reliability SHALL be measured rather than assumed from a single run.

#### Scenario: Repeated runs meet a stated reliability bar
- **GIVEN** a fixed supported model and agent configuration
- **WHEN** the reference multi-step corpus scenario is run multiple times in immediate succession
- **THEN** the semantic/planning requirements of this capability are met in at least the stated minimum proportion of runs, and the truthful-artifact and isolation requirements are met in every run

#### Scenario: Reliability is not achieved by an unbounded loop
- **GIVEN** the reference scenario is run to measure reliability
- **WHEN** tool calls, model calls, elapsed time, and token usage are recorded for each run
- **THEN** those counts stay within a stated bound, so a high success rate cannot be explained by the agent retrying indefinitely
