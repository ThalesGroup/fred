## ADDED Requirements

### Requirement: A reply-only model call is never recovered into a tool call

When a middleware sends a model call with `tool_choice="none"`, the runtime SHALL leave that response as sent: tool-call text in it SHALL NOT be converted into a native tool call.

#### Scenario: Tool-call text after tool_choice none

- **GIVEN** a model call sent with `tool_choice="none"` and a registered tool
- **WHEN** the Mistral response holds that tool's name, the empty `reference` sentinel and valid JSON arguments
- **THEN** the response keeps no tool call and the agent loop ends on that reply
