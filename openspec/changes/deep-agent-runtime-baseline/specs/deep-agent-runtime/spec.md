## Purpose

Defines the observable baseline behavior of Fred's Deep agent runtime: correct dispatch to the Deep
planner, capability wiring, and observability parity with the ReAct runtime.

## ADDED Requirements

### Requirement: Deep agent definitions dispatch to the Deep agent runtime

A turn on an agent configured with a Deep agent definition SHALL be planned by the Deep agent
runtime. It SHALL NOT fall through to the plain ReAct-only runtime.

#### Scenario: A Deep-defined agent executes a turn

- **WHEN** a user turn is executed on an agent configured with a Deep agent definition
- **THEN** the turn is planned by the Deep agent runtime
- **AND** the per-exchange log signal names the Deep agent runtime, not the plain ReAct runtime

### Requirement: A Deep agent turn carries the agent's selected capability

The Deep agent runtime SHALL expose the tools, MCP prompt groups and middleware declared by the
agent's selected capability to the compiled Deep agent graph, the same way the ReAct runtime does
for a ReAct-defined agent.

#### Scenario: A selected capability's tool is available on a Deep turn

- **GIVEN** a Deep agent with a capability selected that declares a tool
- **WHEN** the agent's turn requires that tool
- **THEN** the tool is available to the Deep agent's compiled graph
- **AND** its invocation succeeds the same way it would on a ReAct-defined agent with the same
  capability selected

### Requirement: A Deep agent turn emits the same observability signal as ReAct

A Deep agent turn SHALL emit the same LLM call/response log lines, tool-call latency KPI, and
`agent.tool.invocation.*` audit events that a ReAct agent turn emits for equivalent activity.

#### Scenario: Tool invocation is logged, metered and audited

- **WHEN** a Deep agent turn invokes a bound tool
- **THEN** an LLM call/response log pair is emitted for the model round trip
- **AND** an `agent.tool.invocation.started`/`agent.tool.invocation.completed` audit event pair is
  emitted for the tool call
- **AND** the tool-call latency KPI is recorded

### Requirement: Runtime-provided safe filesystem tools are bound without a capability

The Deep agent runtime SHALL bind `ls`, `read_file`, `write_file`, `edit_file`, `glob`, and `grep`
to its standard conversation-scoped backend even when the agent has no optional filesystem
capability selected. The runtime SHALL keep `execute` unavailable; binding any safe filesystem
operation SHALL NOT authorize it.

#### Scenario: No filesystem capability selected

- **GIVEN** a Deep agent with no optional filesystem capability selected
- **WHEN** the agent's turn is planned
- **THEN** the six safe filesystem operations use the runtime-provided conversation backend
- **AND** the model is told that `execute` is unavailable
- **AND** a call to `execute` is blocked before it can run

#### Scenario: A partial filesystem surface is selected

- **GIVEN** a Deep agent whose selected tools add or replace some safe filesystem operations
- **WHEN** the agent's turn is planned
- **THEN** the standard and explicitly bound safe filesystem operations remain available by exact
  model-visible name
- **AND** the model is told that `execute` is unavailable
- **AND** a call to the Deep agent library's internally registered `execute` tool is blocked before
  it can execute
