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

// "Copy to…" shows, before copying, which teams cannot receive the agent
// (template not enabled: greyed out) and which would lose capabilities
// (warning, explanation above the list), then copies to the selection.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ManagedAgentInstanceSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const copyCalls: unknown[] = [];
const toasts: Array<[string, unknown]> = [];
let copyResults: unknown[] = [];

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) => (options?.count !== undefined ? `${key}:${options.count}` : key),
    i18n: { language: "en" },
  }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({
    showError: (msg: unknown) => toasts.push(["error", msg]),
    showSuccess: (msg: unknown) => toasts.push(["success", msg]),
    showWarn: (msg: unknown) => toasts.push(["warn", msg]),
  }),
}));
vi.mock("../../../../../hooks/useFrontendBootstrap", () => ({
  useFrontendBootstrap: () => ({
    activeTeam: { id: "personal-alice" },
    availableTeams: [
      { id: "team-a", name: "Source team", my_relations: ["team_editor"] },
      { id: "team-b", name: "Ready team", my_relations: ["team_editor"] },
      { id: "team-c", name: "Partial team", my_relations: ["team_editor"] },
      { id: "team-d", name: "No template team", my_relations: ["team_editor"] },
    ],
  }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetAgentInstanceCopyTargetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdCopyTargetsGetQuery: () => ({
    data: {
      targets: [
        { team_id: "personal-alice", template_enabled: true, missing_capabilities: [] },
        { team_id: "team-a", template_enabled: true, missing_capabilities: [] },
        { team_id: "team-b", template_enabled: true, missing_capabilities: [] },
        {
          team_id: "team-c",
          template_enabled: true,
          missing_capabilities: [{ id: "web_search", name: "capability.web_search.name" }],
        },
        { team_id: "team-d", template_enabled: false, missing_capabilities: [] },
      ],
    },
    isError: false,
  }),
  usePostAgentInstanceCopyControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdCopyPostMutation: () => [
    (arg: unknown) => {
      copyCalls.push(arg);
      return { unwrap: async () => ({ results: copyResults }) };
    },
    { isLoading: false },
  ],
}));

import CopyAgentDialog from "./CopyAgentDialog";

const instance = {
  agent_instance_id: "agent-1",
  team_id: "team-a",
  display_name: "Analyst",
} as ManagedAgentInstanceSummary;

function rowFor(name: string): HTMLElement {
  return Array.from(document.querySelectorAll("label")).find((el) => el.textContent?.includes(name))!;
}

function checkboxFor(name: string): HTMLInputElement {
  return rowFor(name).querySelector("input[type=checkbox]") as HTMLInputElement;
}

function click(element: Element) {
  act(() => {
    element.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

async function confirm() {
  const button = Array.from(document.querySelectorAll('[role="dialog"] button')).find(
    (b) => b.textContent?.trim() === "rework.agentCard.copyDialog.confirm",
  );
  await act(async () => {
    button?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

describe("CopyAgentDialog", () => {
  let container: HTMLDivElement;
  let root: Root;

  const render = () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<CopyAgentDialog instance={instance} onClose={() => {}} />);
    });
  };

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    copyCalls.length = 0;
    toasts.length = 0;
    copyResults = [];
  });

  it("greys out a team where the agent template is not enabled", () => {
    render();
    expect(checkboxFor("No template team").disabled).toBe(true);
    expect(rowFor("No template team").textContent).toContain("rework.agentCard.copyDialog.templateDisabled");
    expect(checkboxFor("Ready team").disabled).toBe(false);
  });

  it("warns on a team missing capabilities, which stays selectable, and explains why", () => {
    render();
    expect(rowFor("Partial team").textContent).toContain("rework.agentCard.copyDialog.missingCapabilities:1");
    expect(checkboxFor("Partial team").disabled).toBe(false);
    expect(document.body.textContent).toContain("rework.agentCard.copyDialog.explanation");
  });

  it("keeps the source team checked but never submits it", async () => {
    render();
    expect(checkboxFor("Source team").checked).toBe(true);
    expect(checkboxFor("Source team").disabled).toBe(true);

    copyResults = [{ team_id: "team-b", agent: { agent_instance_id: "agent-2" }, dropped_capabilities: [] }];
    click(checkboxFor("Ready team"));
    await confirm();

    expect(copyCalls).toEqual([
      { teamId: "team-a", agentInstanceId: "agent-1", agentCopyRequest: { target_team_ids: ["team-b"] } },
    ]);
    expect(toasts.map(([kind]) => kind)).toEqual(["success"]);
  });

  it("names the capabilities a copy was made without", async () => {
    render();
    copyResults = [
      {
        team_id: "team-c",
        agent: { agent_instance_id: "agent-3" },
        dropped_capabilities: [{ id: "web_search", name: "capability.web_search.name" }],
      },
    ];
    click(checkboxFor("Partial team"));
    await confirm();

    const warn = toasts.find(([kind]) => kind === "warn")?.[1] as { detail: string };
    expect(warn.detail).toContain("rework.agentCard.copyDialog.droppedDetail");
  });

  it("reports what an editor must redo in the destination", async () => {
    render();
    copyResults = [
      {
        team_id: "team-b",
        agent: { agent_instance_id: "agent-4" },
        dropped_capabilities: [],
        notices: [
          {
            capability: { id: "ppt_filler", name: "capability.ppt_filler.name" },
            message: "Image fields without their folder in this space.",
          },
        ],
      },
    ];
    click(checkboxFor("Ready team"));
    await confirm();

    const warn = toasts.find(([kind]) => kind === "warn")?.[1] as { summary: string; detail: string };
    expect(warn.summary).toBe("rework.agentCard.copyDialog.noticesToast");
    expect(warn.detail).toBe(
      "Ready team — capability.ppt_filler.name : Image fields without their folder in this space.",
    );
  });
});
