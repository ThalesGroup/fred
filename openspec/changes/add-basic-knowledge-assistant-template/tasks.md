## 1. The template-side field

- [x] 1.1 Add `default_capabilities_config` (capability id → config values) to the agent definition models that already carry `default_mcp_servers` in `fred_sdk/contracts/models.py`; verify a definition declaring it round-trips through the model and one omitting it keeps today's behaviour
- [x] 1.2 Project the field onto the template summary in `agent_app.py` beside `default_capability_ids`; verify `GET` on the templates route returns the declared configuration for a template that has one
- [x] 1.3 Mirror the field on the control-plane template listing model; verify the control-plane response carries it unchanged from the pod
- [x] 1.4 Validate a declared default through the capability's own `validate_config` rather than storing it raw; verify a malformed default fails against the template with a message naming the capability, and does not produce a saveable instance

## 2. Frontend seeding

- [x] 2.1 Regenerate the API clients (`cd apps/frontend && make update-all-apis`) and commit them alongside the backend change; verify `default_capabilities_config` appears in both generated files and neither was hand-edited
- [x] 2.2 Add a `defaultCapabilityConfig` seeding helper beside `defaultCapabilitySelection`, narrowed through the same `can_use`-filtered advertised set; verify a default for a capability the team cannot use is neither seeded nor submitted
- [x] 2.3 Seed the form's `capabilityConfigValues` from it on template selection; verify a new agent from a template declaring `document_access` in corpus + attachments mode shows BOTH the team-resources and conversation-attachments packs on before any edit
- [x] 2.4 Verify the member can still change a seeded value and that the saved agent reflects their choice, not the template's

## 3. The knowledge assistant template

- [x] 3.1 Create `apps/fred-agents/fred_agents/basic_knowledge_assistant.py` with `agent_id = "fred.github.basic-knowledge-assistant"`, the eight default capabilities from design.md, the three `default_capabilities_config` slices (`document_access` corpus + attachments; `document_extract` and `document_summarize` with `require_confirmation: false`), `reasoning_enabled`/`reasoning_default_on` on, and `REASONING_SAFE_TOOL_SELECTION`; verify the definition instantiates and advertises what design.md lists
- [ ] 3.1b Verify no human-confirmation gate fires on a normal question: ask the agent about an identified document and confirm extraction runs without a proceed/cancel interrupt
- [x] 3.2 Add the EN and FR system prompts from design.md behind a `prompts.system` field so an operator can edit them; verify the FR variant mirrors the EN one and neither bakes in the runtime-injected global base prompt
- [x] 3.3 Add the EN and FR descriptions from design.md; verify both render in the template picker
- [x] 3.4 Register it in `registry.py` with its lineup comment, after `general_assistant` so the blank slate stays the default agent; verify `general_assistant` still declares no default capabilities and remains the first entry

## 4. Verification

- [x] 4.1 Add tests for the new field: declared config reaches the template summary, an absent declaration behaves as today, and an invalid declaration is refused; verify they fail without the implementation
- [x] 4.2 Add a frontend test that a template declaring `document_access` corpus + attachments seeds both packs on in a new agent form; verify it fails against the current seeding
- [x] 4.3 Run `make code-quality` from the monorepo root and `make test` in each touched project; verify both pass
- [ ] 4.4 **As a platform admin**, on a team enabled for none of the seven `ADMIN_GATED` capabilities, enable the template from `admin/features`; verify the "Enable all" dialog names the seven dependencies and grants them at the same scope in one confirmation
- [ ] 4.5 **As an ordinary team member** on that team, create an agent from the template and save without opening the capabilities view; verify it answers a corpus question, a question about a file attached to the conversation, and a wiki question, with no capability ticked by hand
- [x] 4.6 Run `/code-review` on the diff and address findings; verify no correctness finding remains open

## 5. Documentation and close-out

- [x] 5.1 Add dated entries to `RUNTIME-EXECUTION-CONTRACT.md` and `CONTROL-PLANE-PRODUCT-CONTRACT.md` for the template-summary field; verify both describe the same shape
- [x] 5.2 Document how a template declares default capability configuration in `docs/swift/authoring/AGENTS.md` (NOT `capabilities/AUTHORING.md` as first written: that file covers authoring a capability, and documents no template field at all); verify the example matches the shipped field name
- [x] 5.3 Record verification evidence in this change; verify `openspec validate --strict` passes
- [ ] 5.4 Archive the change once the implementation has merged; verify the capability spec lands under `openspec/specs/agent-template-defaults/`

## Verification evidence

Run 2026-09-18 on `feat/basic-knowledge-assistant-template`.

- `make code-quality` from the monorepo root — pass (exit 0), basedpyright
  `0 errors, 0 warnings, 0 notes` across every Python package.
- `make test`: fred-sdk 436 passed / 3 skipped; fred-runtime 1221 passed;
  fred-agents 84 passed; control-plane 1280 passed; frontend 2464 passed /
  9 skipped. 0 failures.
- New tests: 8 in `apps/fred-agents/tests/test_basic_knowledge_assistant_template.py`
  (registration, the four packs' capability set, corpus+attachments config, both
  confirmation gates off, reasoning pre-armed, every configured capability also
  activated, both prompt languages carrying `{response_language}`, and the blank
  slate still declaring no defaults); 9 in
  `apps/control-plane-backend/tests/test_capability_selection_1974.py` (payload
  parsing, rolling-upgrade tolerance, malformed and quarantined entries dropped,
  the seed/override/stored precedence, no seeding on update, reset ignoring the
  seed); 3 in `AgentFormModal.test.ts` (seeding, can_use narrowing, empty cases).
- `/code-review` on the working-tree diff — 4 findings, all fixed:
  - the template default also fired on UPDATE, so a capability ticked in the
    edit form without opening its options saved a confirmation gate OFF while
    the form showed it ON — the update call site now passes no template config,
    with two regression tests;
  - `reset_values` bypassing the seed is now stated as intended (a reset returns
    a capability to its own defaults) and pinned by a test;
  - the config map is now filtered for quarantined and application-namespace ids
    like the id list beside it;
  - the tabular id now uses `MCP_SERVER_KNOWLEDGE_FLOW_TABULAR`, with a note that
    it is the only default sourced from deployment-owned `mcp_catalog.yaml` and
    that a deployment lacking it fails pod boot loudly — the same contract
    `sentinel` already lives under.

Not covered by automated tests, and left as tasks 3.1b / 4.4 / 4.5: the live
checks that no confirmation modal fires on a normal question, that the admin
"Enable all" dialog grants the seven `ADMIN_GATED` dependencies in one
confirmation, and that a member can create the agent and get answers without
ticking anything.
