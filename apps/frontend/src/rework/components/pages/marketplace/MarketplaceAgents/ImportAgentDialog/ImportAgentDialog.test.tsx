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

// Importing a marketplace agent: the publishing team is never offered, losses
// show per team before confirming, then a result step per destination.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MarketplaceAgentSummary } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => {
  const targets = {
    targets: [
      { team_id: "personal-alice", template_enabled: true, missing_capabilities: [] },
      { team_id: "team-b", template_enabled: true, missing_capabilities: [] },
      {
        team_id: "team-c",
        template_enabled: true,
        missing_capabilities: [{ id: "web_search", name: "capability.web_search.name" }],
      },
      { team_id: "team-d", template_enabled: false, missing_capabilities: [] },
    ],
  };
  return {
    importCalls: [] as unknown[],
    results: [] as unknown[],
    toasts: [] as unknown[],
    targets,
    targetsQuery: { data: targets as typeof targets | undefined, isError: false, isFetching: false },
  };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
    i18n: { language: "fr-FR" },
  }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: (msg: unknown) => h.toasts.push(msg) }),
}));
vi.mock("../../../../../../hooks/useFrontendBootstrap", () => ({
  useFrontendBootstrap: () => ({
    activeTeam: { id: "personal-alice" },
    availableTeams: [
      { id: "team-pub", name: "Source Team", my_relations: ["team_editor"] },
      { id: "team-b", name: "Ready team", my_relations: ["team_editor"] },
      { id: "team-c", name: "Partial team", my_relations: ["team_editor"] },
      { id: "team-d", name: "No type team", my_relations: ["team_editor"] },
    ],
  }),
}));
vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMarketplaceAgentImportTargetsQuery: () => h.targetsQuery,
  useImportMarketplaceAgentMutation: () => [
    (arg: unknown) => {
      h.importCalls.push(arg);
      return { unwrap: async () => ({ results: h.results }) };
    },
    { isLoading: false },
  ],
}));

import ImportAgentDialog from "./ImportAgentDialog";

const agent = {
  entry_id: "entry-1",
  team_id: "team-pub",
  team_name: "Source Team",
  display_name: "Analyst",
} as MarketplaceAgentSummary;

const rowFor = (name: string) =>
  Array.from(document.querySelectorAll("label")).find((el) => el.textContent?.includes(name));

function click(element: Element | undefined) {
  act(() => {
    element?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

const confirmButton = () =>
  Array.from(document.querySelectorAll('[role="dialog"] button')).find(
    (b) => b.textContent?.trim() === "rework.marketplace.agents.import.confirm",
  ) as HTMLButtonElement | undefined;

async function confirmImport() {
  const button = confirmButton();
  await act(async () => {
    button?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

describe("ImportAgentDialog", () => {
  let container: HTMLDivElement;
  let root: Root;

  const render = () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    rerender();
  };
  const rerender = () =>
    act(() => {
      root.render(<ImportAgentDialog agent={agent} onClose={() => {}} />);
    });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    h.importCalls.length = 0;
    h.toasts.length = 0;
    h.results = [];
    h.targetsQuery = { data: h.targets, isError: false, isFetching: false };
  });

  it("never lists the publishing team and states the copy is independent", () => {
    render();
    expect(rowFor("Source Team")).toBeUndefined();
    expect(rowFor("Ready team")).toBeDefined();
    expect(document.body.textContent).toContain('rework.marketplace.agents.import.independent {"team":"Source Team"}');
  });

  it("shows per team what the agent loses and refuses a team without its agent type", () => {
    render();
    expect(rowFor("Partial team")?.textContent).toContain('rework.marketplace.agents.import.loses {"count":1}');
    const noType = rowFor("No type team");
    expect(noType?.textContent).toContain("rework.marketplace.agents.import.typeNotEnabled");
    expect((noType?.querySelector("input[type=checkbox]") as HTMLInputElement).disabled).toBe(true);
  });

  it("drops a team ticked before its targets said it cannot import, and waits for them", async () => {
    h.targetsQuery = { data: undefined, isError: false, isFetching: true };
    render();
    click(rowFor("Ready team")?.querySelector("input[type=checkbox]") ?? undefined);
    click(rowFor("No type team")?.querySelector("input[type=checkbox]") ?? undefined);
    expect(confirmButton()?.disabled).toBe(true);

    h.targetsQuery = { data: h.targets, isError: false, isFetching: false };
    rerender();
    const noType = rowFor("No type team")?.querySelector("input[type=checkbox]") as HTMLInputElement;
    expect(noType.checked).toBe(false);
    await confirmImport();
    expect(h.importCalls).toEqual([
      { entryId: "entry-1", marketplaceAgentImportRequest: { target_team_ids: ["team-b"], locale: "fr" } },
    ]);
  });

  it("keeps Confirm disabled and says so when the targets failed to load", () => {
    h.targetsQuery = { data: undefined, isError: true, isFetching: false };
    render();
    click(rowFor("Ready team")?.querySelector("input[type=checkbox]") ?? undefined);
    expect(confirmButton()?.disabled).toBe(true);
    expect(document.body.textContent).toContain("rework.agentCard.copyDialog.loadError");
  });

  it("imports into the selection, then lists each result with what to reconfigure", async () => {
    h.results = [
      { team_id: "team-b", agent: { display_name: "Analyst (copie 1)" }, dropped_capabilities: [], notices: [] },
      { team_id: "team-c", error: "boom", error_code: "marketplace_publishing_team" },
    ];
    render();
    click(rowFor("Ready team")?.querySelector("input[type=checkbox]") ?? undefined);
    click(rowFor("Partial team")?.querySelector("input[type=checkbox]") ?? undefined);
    await confirmImport();

    expect(h.importCalls).toEqual([
      { entryId: "entry-1", marketplaceAgentImportRequest: { target_team_ids: ["team-b", "team-c"], locale: "fr" } },
    ]);
    const text = document.body.textContent ?? "";
    expect(text).toContain('rework.marketplace.agents.import.importedInto {"team":"Ready team"}');
    expect(text).toContain('rework.marketplace.agents.import.renamed {"name":"Analyst (copie 1)"}');
    expect(text).toContain("rework.marketplace.agents.import.toReconfigure");
    expect(text).toContain('rework.marketplace.agents.import.failedInto {"team":"Partial team"}');
    expect(text).toContain("rework.marketplace.agents.import.errors.marketplace_publishing_team");
    expect(text).not.toContain("boom");
  });
});
