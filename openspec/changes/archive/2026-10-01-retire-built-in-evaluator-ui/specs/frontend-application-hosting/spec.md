## ADDED Requirements

### Requirement: Evaluation is provided by a hosted application

Fred SHALL expose evaluation functionality through a registered hosted application. Fred MUST NOT render built-in evaluation screens in team settings or issue evaluator-specific requests from Activity, task rehydration or task event subscriptions. The removal MUST preserve application admission, permissions, reusable shared UI components and evaluation data.

#### Scenario: Team settings navigation
- **WHEN** a user opens team settings
- **THEN** the navigation contains no built-in Evaluations entry and the remaining sections retain their existing access rules

#### Scenario: Old settings URL
- **WHEN** a team member follows a legacy settings/evaluations URL
- **THEN** Fred applies the existing unknown-section redirect to that team's Members settings without loading evaluator screens

#### Scenario: Activity is independent of evaluator availability
- **WHEN** a user opens team Activity
- **THEN** Fred queries its control-plane and knowledge-flow task services without querying the external evaluator

#### Scenario: External evaluator remains usable
- **WHEN** the evaluator is registered and admitted for a team
- **THEN** users can open it through Apps under the existing host protocol and permission checks

#### Scenario: Reload does not reconnect to evaluator tasks
- **WHEN** a user reloads Fred
- **THEN** task rehydration only queries Fred's own task services and does not subscribe to evaluator task events
