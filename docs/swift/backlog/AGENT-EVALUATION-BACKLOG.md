# Agent Evaluation — Implementation Backlog

**RFC**: [`docs/rfc/AGENT-EVALUATION-RFC.md`](../rfc/AGENT-EVALUATION-RFC.md)

**Status**: Implementation started — EvalTrace HTTP path and external CLI prototype already exist

**Why this track exists**: Fred now has the first building blocks for external agent evaluation (`/agents/evaluate`, `EvalTrace`, and an external CLI prototype), but the RFC goal is broader: to build a durable, industrializable validation toolchain driven by datasets, execution traces, and external scoring tools, rather than in-process evaluators or one class per agent. This backlog tracks the remaining work to turn that strategy into a first-class validation surface.

---

## 0 Overview

### 0.1 Goal

Introduce a first-class agent evaluation toolchain for Fred that:

- evaluates agents through the same HTTP surface used in production
- captures a stable structured execution trace (`EvalTrace`)
- keeps scoring outside `fred-runtime`
- supports dataset-driven validation instead of one evaluator class per agent
- validates not only final text output, but also tool usage, retrieval grounding, failure modes, and latency/cost signals

This toolchain must make it easy to answer questions such as:

- did the agent answer correctly?
- did it call the expected tools?
- did it ground its answer in the retrieved context?
- did it degrade gracefully on failures?
- did a change regress behavior compared with a known baseline?

---

### 0.2 Why this matters

Today Fred has the core ingredients for evaluation, but not yet a complete validation product:

- `fred-runtime` knows how to execute and stream events
- agents already emit enough protocol information to derive an evaluation trace
- `/agents/evaluate` now exposes that trace directly in structured form
- an external CLI prototype (`fred-deepeval-cli`) can already evaluate and score one turn

What is still missing is the industrialized layer:

- stable datasets
- configurable validation profiles by agent type
- structured checks for tool usage and retrieval quality
- robust scoring workflows
- batch execution and baseline comparison
- documentation and team ergonomics

Without this layer, validation remains ad hoc and does not scale well across many agents.

---

### 0.3 Core decision

Keep the architecture split defined in the RFC:

1. `fred-runtime` owns execution and trace production
2. external tooling owns scoring, datasets, and reporting
3. agent-specific variability lives in datasets and validation profiles, not in one Python evaluator class per agent

This preserves the architectural rule:

- execution belongs to Fred
- scoring does not

---

## 1 Design rules

### 1.1 Evaluate through HTTP only

All validation flows must use the deployed/runtime HTTP path. No in-process evaluators should be introduced for this track.

### 1.2 EvalTrace is the evaluation unit

The primary artifact is not only the final text output, but the full execution trace. Validation logic must be able to inspect:

- `output`
- `error`
- `steps`
- `tools_called`
- `retrieval_context`
- `latency_ms`
- `token_usage`

### 1.3 Variability lives in datasets and profiles

Adding a new agent to the validation surface should require:

- a dataset
- optionally a validation profile

It must not require a new Python evaluator class.

### 1.4 No heavy scoring dependencies in `fred-runtime`

`fred-runtime` may contribute trace and protocol helpers, but not DeepEval, Promptfoo, HTML reporting, or other heavy scoring stacks.

---

## 2 Current implementation status

Shipped pieces:

- `POST /agents/evaluate` exists
- the `EvalTrace` contract exists and includes `steps`, `tools_called`, and `retrieval_context`
- `AgentPodClient.evaluate()` exists in `fred-runtime`
- `fred-deepeval-cli` exists as a standalone external project
- the CLI supports:
  - `evaluate`
  - outcome classification (`success`, `execution_error`, `degraded`, `hitl_blocked`)
  - `score`
- initial DeepEval integration works with a configurable judge model
- Makefile alignment with Fred conventions is in place
- unit tests exist for:
  - classification
  - CLI command flow
  - `EvalTrace -> LLMTestCase` adaptation

Remaining work before this track is considered complete:

- stabilize and document the evaluation contract
- add validation profiles and dataset-driven execution
- add structural checks beyond LLM-as-a-judge scoring
- define recommended metrics by agent type
- support batch execution and baseline workflows
- validate against real sample agents and realistic non-happy-path scenarios

---

## 3 Implementation plan

### Phase A — Runtime trace surface (`fred-runtime`)

This phase ensures the execution trace is a stable and trustworthy evaluation artifact.

#### A.1 EvalTrace contract stabilization

- [ ] Confirm and document the canonical `EvalTrace` schema fields and naming
- [ ] Decide which fields are mandatory vs optional in the external contract
- [ ] Clarify whether `tools_called` and `retrieval_context` are always present, even when empty
- [ ] Add explicit tests for `execution_error`, `degraded`, `hitl_blocked`, and successful RAG/tool-use traces
- [ ] Document how `finish_reason`, `usage`, and `latency_ms` are derived

#### A.2 Runtime protocol validation

- [ ] Validate that `/agents/evaluate` remains consistent with `/agents/execute/stream`
- [ ] Ensure all relevant SSE event kinds are faithfully represented in `EvalTrace`
- [ ] Add regression tests around tool-call ordering, node errors, and final output extraction

---

### Phase B — External CLI foundation (`fred-deepeval-cli`)

This phase turns the current prototype into a stable validation console.

#### B.1 CLI ergonomics

- [ ] Finalize the command surface for:
  - `evaluate`
  - `score`
- [ ] Add robust error handling for scorer/model failures
- [ ] Return stable JSON outputs even when one metric fails
- [ ] Standardize exit codes across evaluation and scoring commands
- [ ] Improve README and environment-template guidance
- [ ] Define a stable CLI output schema for `evaluate` and `score`
- [ ] Guarantee a clear, structured, versionable JSON output suitable for future UI consumption
- [ ] Explicitly separate in CLI output:
  - raw trace
  - outcome/status
  - metrics
  - structural checks
  - scoring errors
  - run metadata

#### B.2 Output strategy

- [ ] Keep JSON as the canonical CLI output contract
- [ ] Add or plan an optional human-readable terminal rendering for developer convenience
- [ ] Ensure the human-readable rendering never replaces the machine-friendly JSON contract
- [ ] Document how the JSON output is intended to power future reporting or UI layers

#### B.3 Judge model configuration

- [ ] Replace hard-coded provider assumptions with a provider-agnostic judge-model factory
- [ ] Support at least:
  - LiteLLM / Mistral
  - OpenAI
- [ ] Document the required environment variables for each provider
- [ ] Record the recommended Mistral judge model for structured-output scoring
- [ ] Add unit tests for provider selection logic

---

### Phase C — Validation profiles and structural checks

This phase adds Fred-specific validation logic beyond generic LLM metrics.

#### C.1 Validation profile model

- [ ] Introduce profile-driven validation by agent type (e.g. `rag`, `sql`, `workflow`, `assistant`)
- [ ] Define a profile schema supporting:
  - required tools
  - required retrieval context
  - required final outcomes
  - metric sets
  - optional deterministic assertions

#### C.2 Structural checks

- [ ] Add checks for required tool usage
- [ ] Add checks for forbidden or missing tool usage
- [ ] Add checks for empty retrieval context when retrieval is expected
- [ ] Add checks for expected `outcome` classes (`success`, `hitl_blocked`, etc.)
- [ ] Add checks for expected step kinds and workflow transitions
- [ ] Decide which structural failures are hard-fail vs score-penalty

#### C.3 Default profile policy by agent type

- [ ] Define the default profile for RAG agents
- [ ] Define the default profile for SQL agents
- [ ] Define the default profile for workflow/HITL agents
- [ ] Define the default profile for general assistants

---

### Phase D — Metrics strategy

This phase defines which metrics matter for which agent type.

#### D.1 RAG metrics

- [ ] Establish the default RAG metric set:
  - `AnswerRelevancy`
  - `Faithfulness`
  - `Contextual Precision`
  - `Contextual Recall`
- [ ] Add tests and examples for traces with non-empty `retrieval_context`

#### D.2 SQL metrics

- [ ] Define SQL validation as a mix of:
  - deterministic result assertions
  - tool-usage assertions
  - optional LLM-as-a-judge metrics
- [ ] Clarify when `Faithfulness` is meaningful for SQL answers

#### D.3 Workflow / HITL metrics

- [ ] Define which parts are metric-based vs structurally asserted
- [ ] Treat `awaiting_human`, risk gates, and degraded paths as first-class validation artifacts

#### D.4 Custom criteria

- [ ] Evaluate whether `GEval` or equivalent criteria-based scoring should be added for Fred-specific policies
- [ ] Define at least one example custom criterion for tool-using agents

---

### Phase E — Dataset-driven evaluation

This phase moves the project from one-off prompts to reusable validation suites.

#### E.1 Dataset format

- [ ] Define the canonical dataset schema (`id`, `agent_id`, `question`, `expected_output`, `tags`, etc.)
- [ ] Document how datasets attach to validation profiles
- [ ] Add at least one dataset per initial agent family

#### E.2 Batch runner

- [ ] Add support for scoring a whole dataset file, not just one prompt
- [ ] Emit one structured result object per case
- [ ] Support summary statistics:
  - pass rate
  - mean score
  - failures by category
- [ ] Define an aggregated JSON format directly consumable by a validation UI
- [ ] Include in that output:
  - global agent quality view
  - metric-level detail
  - per-case detail
  - structural failures
  - run metadata (agent, judge provider, judge model, date, dataset)

#### E.3 Baseline / regression workflow

- [ ] Define how evaluation outputs are stored and compared
- [ ] Add a simple baseline comparison mode
- [ ] Decide whether baseline comparison belongs in the CLI or in a higher-level harness

---

### Phase F — Sample-agent and live-stack validation

This phase proves the tooling on realistic, nontrivial agents.

#### F.1 `fred-samples` integration

- [ ] Validate `fred.samples.assistant` end-to-end
- [ ] Validate `fred.samples.bank_transfer.graph` including HITL behavior
- [ ] Validate `fred.samples.postal_tracking.graph` including MCP-backed tool usage
- [ ] Validate at least one team/graph sample with multi-step delegation

#### F.2 Environment matrix

- [ ] Run validation in a no-security local stack
- [ ] Run validation in a Keycloak-enabled stack
- [ ] Document the minimum environment variables needed for evaluation and scoring

---

### Phase G — Documentation and adoption

This phase makes the validation toolchain understandable and reusable by the team.

#### G.1 Docs

- [ ] Add one implementation/design doc describing the validation stack
- [ ] Document:
  - `EvalTrace`
  - validation profiles
  - dataset format
  - metrics per agent type
  - judge-model configuration
  - canonical CLI JSON output
- [ ] Add examples for:
  - one RAG agent
  - one SQL/tool agent
  - one workflow/HITL agent

#### G.2 Team workflow

- [ ] Document “how to add a new agent to validation”
- [ ] Document “how to debug a failing validation”
- [ ] Document “when to use deterministic assertions vs LLM-based metrics”
- [ ] Document how CLI JSON output can be reused by future UI/reporting layers

---

## 4 Resolved decisions

| Decision                  | Chosen answer                                           |
| ------------------------- | ------------------------------------------------------- |
| Execution path            | HTTP only                                               |
| Evaluation unit           | `EvalTrace`, not only final output                      |
| Scoring location          | external tooling, not `fred-runtime`                    |
| Agent variability         | datasets and validation profiles                        |
| Runtime dependency policy | no heavy scorer dependencies in `fred-runtime`          |
| CLI output contract       | JSON is canonical; human-readable rendering is optional |

---

## 5 Open questions

- [ ] Should the long-term harness live under `developer_tools/eval/` as proposed in the RFC, or continue to evolve from `fred-deepeval-cli`?
- [ ] Should Promptfoo become the primary batch harness, or should the standalone CLI remain the main operator surface?
- [ ] Which judge model should be the default for structured-output DeepEval scoring in the Mistral path?
- [ ] Which structural validations should be strict blockers vs soft score penalties?

---

## 6 Progress

| Phase                          | Status      | Notes                                                                      |
| ------------------------------ | ----------- | -------------------------------------------------------------------------- |
| RFC                            | Draft       | Strategy defined; implementation backlog still in progress                 |
| A – Runtime trace surface      | In progress | `/agents/evaluate` + `EvalTrace` exist; contract still needs stabilization |
| B – External CLI foundation    | In progress | `fred-deepeval-cli` prototype exists with `evaluate` and `score`           |
| C – Validation profiles        | Not started | structural checks not yet modeled as profiles                              |
| D – Metrics strategy           | Not started | first metrics exist, but no agreed policy per agent type                   |
| E – Dataset-driven evaluation  | Not started | local fixtures exist; no general dataset runner yet                        |
| F – Live validation            | Not started | local ad hoc validation exists; no documented sample matrix yet            |
| G – Documentation and adoption | Not started | documentation and team workflow layer still missing                        |
