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

// Coverage for AgentsWorkspace — step 3 of the "bring ResourceExplorer to the
// other three tabs" plan (RFC §13.7 FRONT-09.H). Unlike Mon espace/Espace
// d'équipe, Agents is a *single* table whose root is virtual: each agent
// with files is a folder row at that root, named after the agent (never its
// uuid), and clicking one swaps in `FilesystemWorkspace` for that agent's
// real filesystem — with `onNavigateAboveRoot` wired back to the agent list
// so the whole thing reads as one continuous table.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const probe = vi.hoisted(() => ({
  instances: [
    { agent_instance_id: "artemis-1", display_name: "Artemis" },
    { agent_instance_id: "zeus-1", display_name: "Zeus" },
  ] as { agent_instance_id: string; display_name: string }[],
  namesLoading: false,
  dirs: [
    { path: "artemis-1", type: "directory" },
    { path: "zeus-1", type: "directory" },
  ] as { path: string; type: string }[],
  dirsLoading: false,
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery: () => ({
    data: probe.instances,
    isLoading: probe.namesLoading,
  }),
}));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useLsQuery: () => ({ data: probe.dirs, isLoading: probe.dirsLoading }),
}));

const filesystemWorkspaceProbe = vi.hoisted(() => ({ lastProps: null as Record<string, unknown> | null }));
vi.mock("../FilesystemWorkspace/FilesystemWorkspace.tsx", () => ({
  default: (props: Record<string, unknown>) => {
    filesystemWorkspaceProbe.lastProps = props;
    return <div data-testid="filesystem-workspace">{props.rootLabel as string}</div>;
  },
}));

import AgentsWorkspace from "./AgentsWorkspace.tsx";

let container: HTMLDivElement;
let root: Root;

function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<AgentsWorkspace fsTeamId="team-1" userId="u-1" />);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  filesystemWorkspaceProbe.lastProps = null;
  probe.instances = [
    { agent_instance_id: "artemis-1", display_name: "Artemis" },
    { agent_instance_id: "zeus-1", display_name: "Zeus" },
  ];
  probe.namesLoading = false;
  probe.dirs = [
    { path: "artemis-1", type: "directory" },
    { path: "zeus-1", type: "directory" },
  ];
  probe.dirsLoading = false;
});

function click(el: Element | null) {
  act(() => {
    el?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function folderButton(name: string): HTMLButtonElement {
  const button = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes(name));
  if (!button) throw new Error(`"${name}" not rendered`);
  return button as HTMLButtonElement;
}

describe("AgentsWorkspace virtual root", () => {
  it("lists one folder row per agent that has files, named after the agent", () => {
    render();

    expect(() => folderButton("Artemis")).not.toThrow();
    expect(() => folderButton("Zeus")).not.toThrow();
  });

  it("falls back to the removed-agent label for a directory with no matching instance", () => {
    probe.dirs = [{ path: "ghost-1", type: "directory" }];
    render();

    expect(() => folderButton("rework.resources.roots.removedAgent")).not.toThrow();
  });

  it("shows the empty hint when no agent has produced files yet", () => {
    probe.dirs = [];
    render();

    expect(container.textContent).toContain("rework.resources.empty.agents");
  });

  it("ignores non-directory entries under the agents root", () => {
    probe.dirs = [
      { path: "artemis-1", type: "directory" },
      { path: "stray.txt", type: "file" },
    ];
    render();

    expect(() => folderButton("Artemis")).not.toThrow();
    expect([...container.querySelectorAll("button")].some((b) => b.textContent?.includes("stray.txt"))).toBe(false);
  });
});

describe("AgentsWorkspace agent drill-down", () => {
  it("swaps to FilesystemWorkspace with the agent's root/label when a folder is clicked", () => {
    render();

    click(folderButton("Artemis"));

    expect(container.querySelector('[data-testid="filesystem-workspace"]')).not.toBeNull();
    expect(filesystemWorkspaceProbe.lastProps?.root).toBe("teams/team-1/agents/artemis-1/users/u-1");
    expect(filesystemWorkspaceProbe.lastProps?.rootLabel).toBe("Artemis");
  });

  it("returns to the agent list when FilesystemWorkspace calls onNavigateAboveRoot", () => {
    render();

    click(folderButton("Artemis"));
    expect(container.querySelector('[data-testid="filesystem-workspace"]')).not.toBeNull();

    act(() => {
      (filesystemWorkspaceProbe.lastProps?.onNavigateAboveRoot as () => void)();
    });

    expect(container.querySelector('[data-testid="filesystem-workspace"]')).toBeNull();
    expect(() => folderButton("Artemis")).not.toThrow();
  });
});
