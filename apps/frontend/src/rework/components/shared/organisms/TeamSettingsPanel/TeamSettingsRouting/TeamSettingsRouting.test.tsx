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

// TEAM-05, #2118: locks in the read/write split (team_editor writes,
// team_admin reads §6), that the default-profile + operation-rule fields
// round-trip through the query result, and that a rejected PATCH surfaces
// the server's 400 detail inline (§7.2 write-time validation errors).

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TeamRoutingPolicy, TeamWithPermissions } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  policy: undefined as TeamRoutingPolicy | undefined,
  updateRoutingPolicy: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useTeamRoutingPolicyQuery: () => ({ data: h.policy, isLoading: false }),
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
});

const TEAM = { id: "team-1", name: "Team One", is_member: true, admins: [], permissions: [] } as TeamWithPermissions;

describe("TeamSettingsRouting", () => {
  it("renders the stored default profile id and operation rules", () => {
    h.policy = {
      team_id: "team-1",
      version: 1,
      chat_default_profile_id: "default.chat.mistral",
      operation_rules: [{ rule_id: "r1", operation: "planning", purpose: null, target_profile_id: "chat.openai.gpt5" }],
    };
    render(<TeamSettingsRouting team={TEAM} canWrite={true} />);

    const inputs = container.querySelectorAll("input");
    expect((inputs[0] as HTMLInputElement).value).toBe("default.chat.mistral");
    expect((inputs[1] as HTMLInputElement).value).toBe("planning");
    expect((inputs[3] as HTMLInputElement).value).toBe("chat.openai.gpt5");
  });

  it("disables every input and hides the save/add controls for a read-only caller (team_admin)", () => {
    h.policy = { team_id: "team-1", version: 1, chat_default_profile_id: "p1", operation_rules: [] };
    render(<TeamSettingsRouting team={TEAM} canWrite={false} />);

    const inputs = container.querySelectorAll("input");
    inputs.forEach((input) => expect((input as HTMLInputElement).disabled).toBe(true));
    expect(container.querySelectorAll("button")).toHaveLength(0);
  });

  it("adding a rule appends one empty row", () => {
    h.policy = { team_id: "team-1", version: 0, chat_default_profile_id: null, operation_rules: [] };
    render(<TeamSettingsRouting team={TEAM} canWrite={true} />);

    const addButton = Array.from(container.querySelectorAll("button")).find((b) => b.textContent?.includes("addRule"))!;
    act(() => {
      addButton.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    // 1 default-profile input + 3 inputs for the new row.
    expect(container.querySelectorAll("input")).toHaveLength(4);
  });

  it("save PATCHes the trimmed default profile id and current rows", async () => {
    h.policy = { team_id: "team-1", version: 0, chat_default_profile_id: null, operation_rules: [] };
    render(<TeamSettingsRouting team={TEAM} canWrite={true} />);

    const defaultInput = container.querySelector("input")!;
    act(() => {
      defaultInput.dispatchEvent(new Event("focusin"));
      Object.defineProperty(defaultInput, "value", { value: "  chat.openai.gpt5  ", writable: true });
      defaultInput.dispatchEvent(new Event("input", { bubbles: true }));
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
      updateTeamRoutingPolicyRequest: { chat_default_profile_id: "chat.openai.gpt5", operation_rules: [] },
    });
  });

  it("shows the server's 400 detail inline when the save is rejected", async () => {
    h.policy = { team_id: "team-1", version: 0, chat_default_profile_id: null, operation_rules: [] };
    h.updateRoutingPolicy.mockReturnValue({
      unwrap: () => Promise.reject({ data: { detail: "Team 'team-1' may not use profile id(s) ['ghost']." } }),
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
});
