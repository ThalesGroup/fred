## ADDED Requirements

### Requirement: Chat model precedence includes the user's choice and the instance recommendation

For a managed chat turn the chat model SHALL be resolved with this precedence,
highest first:
1. the platform operator binding;
2. the pod's ops-authored per-agent override;
3. the user's per-conversation choice;
4. the agent instance's recommended model;
5. the team default;
6. the pod default.

There SHALL be no team per-template level. The control-plane effective-chat-model
read and the pod SHALL apply the same order.

#### Scenario: User choice beats the instance recommendation

- **GIVEN** an instance recommending model A, a team default B, and a user
  choice C, all usable by the team
- **WHEN** the turn is resolved
- **THEN** the turn runs on C

#### Scenario: Instance recommendation beats the team default

- **GIVEN** an instance recommending A and a team default B, with no user choice
- **WHEN** the turn is resolved
- **THEN** the turn runs on A

#### Scenario: Ops override and platform binding still win

- **GIVEN** a user choice C and either a pod YAML override for the agent or a
  platform binding
- **WHEN** the turn is resolved
- **THEN** the turn runs on the override or binding, and C is ignored

### Requirement: Client and stored choices are validated by the pod

The user's per-turn choice, a chat profile id forwarded by the client, and the
instance recommendation SHALL each be accepted only if the profile exists in
the pod catalog, declares the chat capability, its model is in the team's
`can_use` models for the turn, and its model is not disabled by the team. The
team-disabled set SHALL reach the pod only through server-resolved data, never
from request content. An invalid value SHALL be ignored and logged,
and resolution SHALL continue with the next level. It SHALL never fail the
turn.

#### Scenario: Spoofed choice of a model the team cannot use

- **GIVEN** a team whose `can_use` models exclude model X
- **WHEN** a turn arrives with a user choice naming a profile of X
- **THEN** the pod ignores the choice and never runs the turn on X

#### Scenario: Choice of a profile unknown to the pod

- **WHEN** a turn arrives with a user choice naming an unknown or non-chat profile
- **THEN** the pod ignores the choice and the turn proceeds on the next level

#### Scenario: Choice of a team-disabled model

- **GIVEN** model B is allowed by the platform but disabled by the team
- **WHEN** a turn arrives with a user choice naming a profile of B
- **THEN** the pod ignores the choice and runs the turn on the next level

#### Scenario: Recommendation of a team-disabled model

- **GIVEN** an instance whose stored recommendation names model B, which the
  team has since disabled
- **WHEN** a turn without a user choice is resolved
- **THEN** the turn runs on the team default

#### Scenario: Team default found disabled

- **GIVEN** a team default whose model appears in the team-disabled set
- **WHEN** a turn falls through to the team default
- **THEN** the turn fails closed with a model-not-usable error instead of
  substituting another model

#### Scenario: Recommendation of a revoked model

- **GIVEN** an instance recommending a model the team can no longer use
- **WHEN** a turn without a user choice is resolved
- **THEN** the turn runs on the team default

### Requirement: The instance recommendation is trusted server-side data

The instance recommendation SHALL reach the pod only through the
server-resolved instance tuning, never from request content.

#### Scenario: Request body cannot set the recommendation

- **WHEN** a turn's runtime context carries a field claiming an instance
  recommendation
- **THEN** the pod uses only the recommendation from the server-resolved tuning

### Requirement: Reasoning runs only on an explicit choice within the platform ceiling

For a managed instance turn, the models allowed to reason SHALL be exactly the
models whose reasoning a platform admin enabled; no agent-level setting SHALL
narrow them. A turn without a managed instance SHALL have an empty ceiling. A
turn SHALL reason only when it carries `reasoning: true` and its model is within
the ceiling. A false or absent reasoning value SHALL run without reasoning.

#### Scenario: Composer leaves the row on

- **WHEN** a managed turn carries reasoning true on a reasoning-enabled model
- **THEN** the model is called with its ops-authored reasoning settings

#### Scenario: Admin disabled reasoning for the model

- **WHEN** the turn carries reasoning true on a model outside the ceiling
- **THEN** the model is called without reasoning settings

#### Scenario: Non-composer caller sends no reasoning value

- **WHEN** an OpenAI-compatible or evaluation turn carries no reasoning value
- **THEN** the model is called without reasoning settings

### Requirement: The user's choice applies to the top-level agent only

The user's choice SHALL apply to the chat model of the agent the user talks to,
on managed-instance turns only: a direct template run SHALL ignore it.
Agents invoked through the agent registry SHALL keep their own resolution.
Native sub-agents that share the parent's chat model client SHALL use the
parent's model.

#### Scenario: Graph child invoked through the registry

- **GIVEN** a user choice C on a parent Graph agent
- **WHEN** the parent invokes a child through the registry
- **THEN** the child's model is resolved without C

#### Scenario: Direct template run

- **WHEN** a direct template run (no agent instance) sends a chat profile choice
- **THEN** the choice is not bound and the model resolves without it
