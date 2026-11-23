## ADDED Requirements

### Requirement: Knowledge Flow supports positional predict rerankers

Knowledge Flow SHALL accept two remote reranker providers: `rerank` for indexed results and `predict` for positional scores. The `predict` provider SHALL call `<base_url>/models/<name>:predict` for a configured model name, send the query and document strings with the selected reranker credential in the `apikey` header, and interpret each finite numeric `predictions` score as applying to the document at the same input position. It SHALL preserve the existing authorization, result limits, and explicit remote failure behavior.

#### Scenario: Successful predict ranking
- **WHEN** an enabled search has visible candidates and the configured predict service returns one finite numeric prediction for each submitted document
- **THEN** Knowledge Flow returns the requested number of visible hits ordered by those scores, with each hit's original identity and metadata intact

#### Scenario: Missing or invalid predict response
- **WHEN** the predict service fails, omits predictions, returns a different number of scores, or returns a nonnumeric or nonfinite score
- **THEN** Knowledge Flow returns the existing distinguishable reranker failure and does not use the local CrossEncoder

#### Scenario: Existing remote protocol remains available
- **WHEN** a deployment selects the existing `rerank` provider
- **THEN** Knowledge Flow continues to use its indexed-results `/rerank` protocol and existing authentication behavior

#### Scenario: No remote provider selected
- **WHEN** no `reranker_model` is configured
- **THEN** Knowledge Flow continues to use the local CrossEncoder without requiring a remote credential
