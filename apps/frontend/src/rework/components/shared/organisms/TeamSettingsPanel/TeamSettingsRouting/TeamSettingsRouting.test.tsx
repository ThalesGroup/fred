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

// TEAM-05, #2118 + #2167: locks in the read/write split (team_editor writes,
// team_admin reads §6), that the default-profile + operation-rule fields
// round-trip through the query result, that both profile pickers are scoped
// to the team's `can_use`-enabled models (§13), and that a rejected PATCH
// surfaces the server's 400 detail inline (§7.2 write-time validation
// errors).

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
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

// Select's trigger is a <button aria-haspopup="listbox">; plain action
// buttons ("Add rule", "Save") carry no such attribute.
function selectTriggers(): HTMLButtonElement[] {
  return Array.from(container.querySelectorAll('button[aria-haspopup="listbox"]'));
}

function pressKey(el: Element, key: string) {
  act(() => {
    el.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  });
}

describe("TeamSettingsRouting", () => {
  it("renders the stored default profile id and operation rules", () => {
    h.policy = {
      team_id: "team-1",
      version: 1,
      chat_default_profile_id: "default.chat.mistral",
      operation_rules: [{ rule_id: "r1", operation: "planning", purpose: null, target_profile_id: "chat.openai.gpt5" }],
    };
    h.availableModels = TWO_MODELS;
    render(<TeamSettingsRouting team={TEAM} canWrite={true} />);

    const triggers = selectTriggers();
    expect(triggers[0].textContent).toContain("Mistral (default.chat.mistral)");
    expect(triggers[1].textContent).toContain("GPT-5 (chat.openai.gpt5)");

    const inputs = container.querySelectorAll("input");
    expect((inputs[0] as HTMLInputElement).value).toBe("planning");
  });

  it("disables every field and hides the save/add controls for a read-only caller (team_admin)", () => {
    h.policy = { team_id: "team-1", version: 1, chat_default_profile_id: "chat.openai.gpt5", operation_rules: [] };
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
    h.policy = { team_id: "team-1", version: 0, chat_default_profile_id: null, operation_rules: [] };
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
      operation_rules: [],
    };
    h.availableModels = ONE_MODEL;
    render(<TeamSettingsRouting team={TEAM} canWrite={true} />);

    expect(selectTriggers()[0].textContent).toContain("chat.openai.gpt4o-legacy");
  });

  it("adding a rule appends one empty row", () => {
    h.policy = { team_id: "team-1", version: 0, chat_default_profile_id: null, operation_rules: [] };
    h.availableModels = ONE_MODEL;
    render(<TeamSettingsRouting team={TEAM} canWrite={true} />);

    const addButton = Array.from(container.querySelectorAll("button")).find((b) => b.textContent?.includes("addRule"))!;
    act(() => {
      addButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    // operation + purpose text inputs for the new row.
    expect(container.querySelectorAll("input")).toHaveLength(2);
    // default-profile select + the new row's target-profile select.
    expect(selectTriggers()).toHaveLength(2);
  });

  it("save PATCHes the picked default profile id and current rows", async () => {
    h.policy = { team_id: "team-1", version: 0, chat_default_profile_id: null, operation_rules: [] };
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
      updateTeamRoutingPolicyRequest: { chat_default_profile_id: "chat.openai.gpt5", operation_rules: [] },
    });
  });

  it("shows the server's 400 detail inline when the save is rejected", async () => {
    h.policy = { team_id: "team-1", version: 0, chat_default_profile_id: null, operation_rules: [] };
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

  it("renders a 422 array-shaped detail as a readable message, not [object Object]", async () => {
    h.policy = { team_id: "team-1", version: 0, chat_default_profile_id: null, operation_rules: [] };
    h.availableModels = ONE_MODEL;
    h.updateRoutingPolicy.mockReturnValue({
      unwrap: () =>
        Promise.reject({
          status: 422,
          data: {
            detail: [
              {
                loc: ["body", "operation_rules", 0, "rule_id"],
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

  it("assigns a non-empty rule_id to a newly added override rule on save", async () => {
    h.policy = { team_id: "team-1", version: 0, chat_default_profile_id: null, operation_rules: [] };
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

    const calls = h.updateRoutingPolicy.mock.calls as unknown as Array<
      [{ updateTeamRoutingPolicyRequest: { operation_rules: { rule_id: string }[] } }]
    >;
    const lastCall = calls[calls.length - 1][0];
    const rules = lastCall.updateTeamRoutingPolicyRequest.operation_rules;
    expect(rules).toHaveLength(1);
    expect(rules[0].rule_id.length).toBeGreaterThan(0);
  });
});
