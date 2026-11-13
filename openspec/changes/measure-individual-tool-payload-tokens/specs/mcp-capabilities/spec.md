## MODIFIED Requirements

### Requirement: Tabular details do not attribute full model usage to an individual tool

The tabular tool drawer MUST NOT label complete model prompt/completion counters as an individual tool's tokens, including requesting, following, historical or shared model-response usage. For a supported tabular call with verified tool-specific measurements, the drawer SHALL show `Tokens envoyés` for all parameters sent by the model to that tool and `Tokens reçus` for its complete model-visible returned content. Each count SHALL use the actual model's verified tokenizer and retain model/tokenizer identity and provenance. Missing, unsupported or unverified measurements SHALL be explicitly unavailable, never estimated, derived from neighboring model requests, copied from model totals or replaced with zero. The drawer SHALL retain status, duration, SQL, colored five-row results with every returned column, complete supported copying and the compact preview notice, without the rejected model-usage paragraph.

#### Scenario: One returned row and large model context
- **GIVEN** a query returns one row and the following model response reports 59260 input and 12426 output tokens
- **WHEN** the user opens the tool details
- **THEN** those global model counters are not displayed as tool consumption
- **AND** the two tool badges show only independently verified parameter/result counts or their unavailable states
- **AND** SQL, returned content, status and duration remain visible without a model-usage paragraph

#### Scenario: Independent parameter and complete-result counts
- **GIVEN** the model sends a fully captured parameter payload and receives a complete tool result
- **WHEN** those contents are counted with the verified tokenizer for that model
- **THEN** each tool badge displays its corresponding exact content count with tooltip provenance
- **AND** unrelated conversation context, shared tool schemas, reasoning and protocol framing are excluded

#### Scenario: Preview does not change measurement
- **GIVEN** a query returns 200 rows and 20 columns but the drawer shows five rows with all 20 columns
- **WHEN** the tool response is measured
- **THEN** the received count covers the complete model-visible response, not the preview or a clipped cell
- **AND** copying still retrieves the complete recorded response

#### Scenario: Live updates and reload
- **WHEN** an executed tool's counts arrive through live events and the conversation is subsequently reloaded on another instance
- **THEN** the same counts and model/tokenizer identity are retained for that session/exchange/call ID
- **AND** requesting or following model totals are never substituted

#### Scenario: Missing, empty or unsupported measurement
- **WHEN** raw parameters, verified tokenizer identity or a completed result are unavailable
- **THEN** the affected direction is unavailable while tool execution and inspection continue
- **AND** a genuine empty payload is zero only when its verified tokenizer measured zero
- **AND** old history is not silently retokenized using an assumed model

#### Scenario: Missing or zero model usage
- **WHEN** model-response usage has missing, invalid or zero counters
- **THEN** those values do not supply either individual tool count
- **AND** each tool badge relies only on its own verified payload measurement or remains unavailable

#### Scenario: Shared model response
- **WHEN** one model response requests several tools with different parameter/result contents
- **THEN** each call receives its own content counts by call ID without borrowing another call's count
- **AND** existing model usage and conversation billing remain unchanged

#### Scenario: Bounded work across concurrent calls
- **WHEN** supported tools produce large results concurrently
- **THEN** token measurement does not block the asynchronous execution path, perform per-call downloads or rely on process-local attribution for correctness
- **AND** a measurement failure does not fail the tool or invent a count
