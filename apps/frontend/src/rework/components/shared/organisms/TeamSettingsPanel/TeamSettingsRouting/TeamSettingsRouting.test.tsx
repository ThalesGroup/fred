// @vitest-environment happy-dom
// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Locks in the read/write split (team_editor writes, team_admin reads), that
// the default-profile + per-agent override fields round-trip through the
// query result, that both profile pickers are scoped to the team's
// `can_use`-enabled models, that an incomplete override row is dropped
// rather than saved half-filled, and that a rejected PATCH surfaces the
// server's 400 detail inline.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  AgentTemplateSummary,
  AvailableModelProfileList,
  TeamRoutingPolicy,
  TeamWithPermissions,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  policy: undefined as TeamRoutingPolicy | undefined,
  availableModels: undefined as AvailableModelProfileList | undefined,
  agentTemplates: undefined as AgentTemplateSummary[] | undefined,
  updateRoutingPolicy: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useTeamRoutingPolicyQuery: () => ({ data: h.policy, isLoading: false }),
  useAvailableModelProfilesQuery: () => ({ data: h.availableModels, isLoading: false }),
  useUpdateTeamRoutingPolicyMutation: () => [h.updateRoutingPolicy, { isLoading: false }],
}));

vi.mock("../../../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery: () => ({ data: h.agentTemplates }),
}));

import TeamSettingsRouting from "./TeamSettingsRouting.tsx";

let container: HTMLDivElement;
let root: Root;

function render(ui: React.ReactElement) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(ui);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  h.updateRoutingPolicy.mockClear();
  h.policy = undefined;
  h.availableModels = undefined;
  h.agentTemplates = undefined;
});

const TEAM = { id: "team-1", name: "Team One", is_member: true, admins: [], permissions: [] } as TeamWithPermissions;

const ONE_MODEL: AvailableModelProfileList = {
  profiles: [{ profile_id: "chat.openai.gpt5", capability_id: "model__openai__gpt-5", name: "GPT-5" }],
};

const TWO_MODELS: AvailableModelProfileList = {
  profiles: [
    { profile_id: "default.chat.mistral", capability_id: "model__mistral__default", name: "Mistral" },
    { profile_id: "chat.openai.gpt5", capability_id: "model__openai__gpt-5", name: "GPT-5" },
  ],
};

const RICO_TEMPLATE = {
  template_id: "t1",
  source_runtime_id: "fred-agents",
  source_agent_id: "rico",
  display_name: "Rico",
  description: "",
} as AgentTemplateSummary;

// Select's trigger is a <button aria-haspopup="listbox">; plain action
// buttons ("Add override", "Save") carry no such attribute.
function selectTriggers(): HTMLButtonElement[] {
  return Array.from(container.querySelectorAll('button[aria-haspopup="listbox"]'));
}

function pressKey(el: Element, key: string) {
  act(() => {
    el.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  });
}

describe("TeamSettingsRouting", () => {
  it("renders the stored default profile id and agent overrides", () => {
    h.policy = {
      team_id: "team-1",
      version: 1,
      chat_default_profile_id: "default.chat.mistral",
      agent_profile_overrides: { rico: "chat.openai.gpt5" },
    };
    h.availableModels = TWO_MODELS;
    h.agentTemplates = [RICO_TEMPLATE];
    render(<TeamSettingsRouting team={TEAM} canWrite={true} />);

    const triggers = selectTriggers();
    // [0] default profile · [1] the row's agent · [2] the row's target profile
    expect(triggers[0].textContent).toContain("Mistral (default.chat.mistral)");
    expect(triggers[1].textContent).toContain("Rico");
    expect(triggers[2].textContent).toContain("GPT-5 (chat.openai.gpt5)");
    // No free-text inputs left in the row — agent and profile are both pickers.
    expect(container.querySelectorAll("input")).toHaveLength(0);
  });

  it("disables every field and hides the save/add controls for a read-only caller (team_admin)", () => {
    h.policy = {
      team_id: "team-1",
      version: 1,
      chat_default_profile_id: "chat.openai.gpt5",
      agent_profile_overrides: {},
    };
    h.availableModels = ONE_MODEL;
    render(<TeamSettingsRouting team={TEAM} canWrite={false} />);

    selectTriggers().forEach((trigger) => expect(trigger.disabled).toBe(true));
    expect(Array.from(container.querySelectorAll("button")).some((b) => b.textContent?.includes("addRule"))).toBe(
      false,
    );
    expect(
      Array.from(container.querySelectorAll("button")).some(
        (b) => b.textContent === "rework.teamSettings.routing.save",
      ),
    ).toBe(false);
  });

  it("shows an explanatory message instead of a picker when the team has no enabled models", () => {
    h.policy = { team_id: "team-1", version: 0, chat_default_profile_id: null, agent_profile_overrides: {} };
    h.availableModels = { profiles: [] };
    render(<TeamSettingsRouting team={TEAM} canWrite={true} />);

    expect(selectTriggers()).toHaveLength(0);
    expect(container.textContent).toContain("rework.teamSettings.routing.emptyState");
  });

  it("a stale profile id no longer enabled for the team still renders as a flagged option instead of vanishing", () => {
    h.policy = {
      team_id: "team-1",
      version: 1,
      chat_default_profile_id: "chat.openai.gpt4o-legacy",
      agent_profile_overrides: {},
    };
    h.availableModels = ONE_MODEL;
    render(<TeamSettingsRouting team={TEAM} canWrite={true} />);

    expect(selectTriggers()[0].textContent).toContain("chat.openai.gpt4o-legacy");
  });

  it("adding an override appends one empty row with no agent or profile picked", () => {
    h.policy = { team_id: "team-1", version: 0, chat_default_profile_id: null, agent_profile_overrides: {} };
    h.availableModels = ONE_MODEL;
    render(<TeamSettingsRouting team={TEAM} canWrite={true} />);

    const addButton = Array.from(container.querySelectorAll("button")).find((b) => b.textContent?.includes("addRule"))!;
    act(() => {
      addButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    // default-profile select + the new row's agent + target-profile selects.
    expect(selectTriggers()).toHaveLength(3);
  });

  it("save PATCHes the picked default profile id and current overrides", async () => {
    h.policy = { team_id: "team-1", version: 0, chat_default_profile_id: null, agent_profile_overrides: {} };
    h.availableModels = ONE_MODEL;
    render(<TeamSettingsRouting team={TEAM} canWrite={true} />);

    const defaultTrigger = selectTriggers()[0];
    pressKey(defaultTrigger, "ArrowDown"); // open, active = "use deployment default" (current value)
    pressKey(defaultTrigger, "ArrowDown"); // move to the one available model
    pressKey(defaultTrigger, "Enter");

    const saveButton = Array.from(container.querySelectorAll("button")).find(
      (b) => b.textContent === "rework.teamSettings.routing.save",
    )!;
    await act(async () => {
      saveButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      await Promise.resolve();
    });

    expect(h.updateRoutingPolicy).toHaveBeenCalledWith({
      teamId: "team-1",
      updateTeamRoutingPolicyRequest: { chat_default_profile_id: "chat.openai.gpt5", agent_profile_overrides: {} },
    });
  });

  it("shows the server's 400 detail inline when the save is rejected", async () => {
    h.policy = { team_id: "team-1", version: 0, chat_default_profile_id: null, agent_profile_overrides: {} };
    h.availableModels = ONE_MODEL;
    h.updateRoutingPolicy.mockReturnValue({
      unwrap: () =>
        Promise.reject({ status: 400, data: { detail: "Team 'team-1' may not use profile id(s) ['ghost']." } }),
    } as never);
    render(<TeamSettingsRouting team={TEAM} canWrite={true} />);

    const saveButton = Array.from(container.querySelectorAll("button")).find(
      (b) => b.textContent === "rework.teamSettings.routing.save",
    )!;
    await act(async () => {
      saveButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.textContent).toContain("may not use profile id(s) ['ghost']");
  });

  it("round-trips an agent-scoped override and saves it keyed by agent_id", async () => {
    h.policy = {
      team_id: "team-1",
      version: 1,
      chat_default_profile_id: null,
      agent_profile_overrides: { rico: "chat.openai.gpt5" },
    };
    h.availableModels = ONE_MODEL;
    h.agentTemplates = [RICO_TEMPLATE];
    h.updateRoutingPolicy.mockReturnValue({ unwrap: () => Promise.resolve() } as never);
    render(<TeamSettingsRouting team={TEAM} canWrite={true} />);

    // the row's agent select resolves the id to the agent's display name
    expect(selectTriggers()[1].textContent).toContain("Rico");

    const saveButton = Array.from(container.querySelectorAll("button")).find(
      (b) => b.textContent === "rework.teamSettings.routing.save",
    )!;
    await act(async () => {
      saveButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      await Promise.resolve();
    });

    const calls = h.updateRoutingPolicy.mock.calls as unknown as Array<
      [{ updateTeamRoutingPolicyRequest: { agent_profile_overrides: Record<string, string> } }]
    >;
    const overrides = calls[calls.length - 1][0].updateTeamRoutingPolicyRequest.agent_profile_overrides;
    expect(overrides).toEqual({ rico: "chat.openai.gpt5" });
  });

  it("renders a 422 array-shaped detail as a readable message, not [object Object]", async () => {
    h.policy = { team_id: "team-1", version: 0, chat_default_profile_id: null, agent_profile_overrides: {} };
    h.availableModels = ONE_MODEL;
    h.updateRoutingPolicy.mockReturnValue({
      unwrap: () =>
        Promise.reject({
          status: 422,
          data: {
            detail: [
              {
                loc: ["body", "agent_profile_overrides"],
                msg: "String should have at least 1 character",
                type: "string_too_short",
              },
            ],
          },
        }),
    } as never);
    render(<TeamSettingsRouting team={TEAM} canWrite={true} />);

    const saveButton = Array.from(container.querySelectorAll("button")).find(
      (b) => b.textContent === "rework.teamSettings.routing.save",
    )!;
    await act(async () => {
      saveButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.textContent).toContain("String should have at least 1 character");
    expect(container.textContent).not.toContain("[object Object]");
  });

  it("blocks save and shows an error for a row with an agent picked but no profile", async () => {
    h.policy = { team_id: "team-1", version: 0, chat_default_profile_id: null, agent_profile_overrides: {} };
    h.availableModels = ONE_MODEL;
    h.agentTemplates = [RICO_TEMPLATE];
    h.updateRoutingPolicy.mockReturnValue({ unwrap: () => Promise.resolve() } as never);
    render(<TeamSettingsRouting team={TEAM} canWrite={true} />);

    const addButton = Array.from(container.querySelectorAll("button")).find((b) => b.textContent?.includes("addRule"))!;
    act(() => {
      addButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    // triggers: [0] default profile · [1] new row's agent · [2] new row's profile (left unset)
    const [, agentTrigger] = selectTriggers();
    pressKey(agentTrigger, "ArrowDown");
    pressKey(agentTrigger, "Enter");

    const saveButton = Array.from(container.querySelectorAll("button")).find(
      (b) => b.textContent === "rework.teamSettings.routing.save",
    )!;
    await act(async () => {
      saveButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      await Promise.resolve();
    });

    expect(h.updateRoutingPolicy).not.toHaveBeenCalled();
    expect(container.textContent).toContain("rework.teamSettings.routing.agentOverrides.incompleteRow");
  });

  it("does not block save on a fully untouched blank row (just silently excluded)", async () => {
    h.policy = { team_id: "team-1", version: 0, chat_default_profile_id: null, agent_profile_overrides: {} };
    h.availableModels = ONE_MODEL;
    h.updateRoutingPolicy.mockReturnValue({ unwrap: () => Promise.resolve() } as never);
    render(<TeamSettingsRouting team={TEAM} canWrite={true} />);

    const addButton = Array.from(container.querySelectorAll("button")).find((b) => b.textContent?.includes("addRule"))!;
    act(() => {
      addButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    const saveButton = Array.from(container.querySelectorAll("button")).find(
      (b) => b.textContent === "rework.teamSettings.routing.save",
    )!;
    await act(async () => {
      saveButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      await Promise.resolve();
    });

    expect(h.updateRoutingPolicy).toHaveBeenCalledWith({
      teamId: "team-1",
      updateTeamRoutingPolicyRequest: { chat_default_profile_id: null, agent_profile_overrides: {} },
    });
  });

  it("saves a complete row's override once both an agent and a profile are picked", async () => {
    h.policy = { team_id: "team-1", version: 0, chat_default_profile_id: null, agent_profile_overrides: {} };
    h.availableModels = ONE_MODEL;
    h.agentTemplates = [RICO_TEMPLATE];
    h.updateRoutingPolicy.mockReturnValue({ unwrap: () => Promise.resolve() } as never);
    render(<TeamSettingsRouting team={TEAM} canWrite={true} />);

    const addButton = Array.from(container.querySelectorAll("button")).find((b) => b.textContent?.includes("addRule"))!;
    act(() => {
      addButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    // triggers: [0] default profile · [1] new row's agent · [2] new row's profile
    const [, agentTrigger, profileTrigger] = selectTriggers();
    pressKey(agentTrigger, "ArrowDown");
    pressKey(agentTrigger, "ArrowDown");
    pressKey(agentTrigger, "Enter");
    pressKey(profileTrigger, "ArrowDown");
    pressKey(profileTrigger, "Enter");

    const saveButton = Array.from(container.querySelectorAll("button")).find(
      (b) => b.textContent === "rework.teamSettings.routing.save",
    )!;
    await act(async () => {
      saveButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      await Promise.resolve();
    });

    const calls = h.updateRoutingPolicy.mock.calls as unknown as Array<
      [{ updateTeamRoutingPolicyRequest: { agent_profile_overrides: Record<string, string> } }]
    >;
    const overrides = calls[calls.length - 1][0].updateTeamRoutingPolicyRequest.agent_profile_overrides;
    expect(overrides).toEqual({ rico: "chat.openai.gpt5" });
  });
});
