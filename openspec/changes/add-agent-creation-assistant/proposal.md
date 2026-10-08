## Why

Creating an agent asks for a system prompt. People who are not comfortable with AI do not know what to write, so they leave the default, write one vague sentence, or give up. The platform knows how an agent's final instructions are assembled and which capabilities can be turned on; it can write a good first prompt for them.

Tracking: [#3009](https://github.com/ThalesGroup/fred/issues/3009)

## What Changes

- **"Creation assistant" in the agent form header.** One tonal button, in create and edit modes, opens a dialog once a template is chosen. The user describes in their own words what the agent should do: role, mission, audience, constraints.
- **One model call drafts the agent.** The template's pod asks a chat model for:
  - a short name, a short role and a one-sentence description, in the user's language, always within the form's limits;
  - a system prompt written for this platform's agents: role, mission, audience and tone, method, sources and accuracy, answer format, rules and limits; concise Markdown, in the user's language;
  - the capabilities to turn on, chosen among those the team may use on that template, the smallest set that covers the mission.
- **The prompt fits how agents are assembled.** It never repeats what the platform already adds (tool list, tool usage rules, house style), never names the platform, and never contains the reserved prompt tags.
- **The user picks what to keep.** Every proposal (prompt, name, role, description, each capability) has a checkbox, all ticked by default; applying writes only the ticked ones and asks for confirmation before replacing a value already in the form. Nothing is saved until the agent is.
- **Admins tune it.** The admin **Platform prompts** page has a **Creation assistant** tab to override its instructions (the meta-prompt), restore the default, and choose which chat model it uses (default: the platform's default model). The created agent's own model is never chosen by the assistant.
- **Endpoints.**
  - Control plane: `POST /control-plane/v1/teams/{team_id}/agent-templates/{template_id}/draft-agent`, gated like creating an agent.
  - Pod: `POST /agents/creation-assistant/draft`, called by the control plane with the user's token.
  - Control plane: `GET`/`PUT`/`DELETE /control-plane/v1/admin/platform/creation-assistant`, gated like the platform prompt.
  - Control plane: `GET /control-plane/v1/teams/{team_id}/creation-assistant/settings`, read by the pod with the caller's token. Every team editor (`can_update_agents`) can therefore read the admin's meta-prompt override and model id: admins must not put confidential notes in the meta-prompt.

## Capabilities

### New Capabilities

- `agent-creation-assistant`: drafting an agent (name, role, description, system prompt, capability selection) from a plain-language description. Covers who may use it, which capabilities can be recommended, what the draft must and must not contain, how it is applied, the admin settings (meta-prompt, model), failures, and what is observed.

### Modified Capabilities

None.

## Impact

- **SDK:** wire models in `fred_sdk.contracts.agent_draft`; `strip_reserved_prompt_tags` in `prompt_utils`.
- **Runtime:** the pod route, the `creation_assistant` module with its meta-prompt, `RoutedChatModelFactory.build_chat_for_profile()`.
- **Control plane:** the route, a relay module, template resolution shared with agent enrollment, an entry in `authz-endpoint-matrix.yaml`.
- **Frontend:** the header button and dialog in the agent form (`AgentFormModal/CreationAssistantDialog/`), a `tonal` variant of the `Button` atom, fr and en strings, the Help Center agents and administration pages; the shared modals leave Escape and Tab to the topmost one (`isTopmostModal`, `alertdialog` included): `ConfirmationDialog` takes focus on Cancel and traps Tab, `DialogPrimitive` and `FullPageModal` yield to it; a read-only `PromptEditor` stays keyboard-focusable.
- **Docs:** `CONTROL-PLANE-PRODUCT-CONTRACT.md` and `RUNTIME-EXECUTION-CONTRACT.md` §8 dated entries, a migration note.
- **Database:** one control-plane table, `creation_assistant_settings` (single row: meta-prompt override, model profile; Alembic `93427a5fe874`). No configuration change: without an admin choice the pod's default chat profile is used.
- **Admin UI:** the platform prompt page becomes **Platform prompts** with two tabs (`PlatformSystemPromptPane`, `CreationAssistantPane`).
