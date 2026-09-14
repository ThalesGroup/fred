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

// Only a platform_admin picks where new users land, and the picker names teams,
// never their ids.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type DefaultTeam = { team_id: string; name: string };

const h = vi.hoisted(() => ({
  canAdmin: true,
  gcuVersion: "v1" as string | null,
  teams: [
    { id: "uid-alpha", name: "Alpha" },
    { id: "uid-beta", name: "Beta" },
    { id: "uid-gamma", name: "Gamma" },
  ],
  defaultTeams: undefined as { team_id: string; name: string }[] | undefined,
  setDefaultTeams: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}));

vi.mock("@core/hooks/useApiErrorToast.ts", () => ({
  useApiErrorToast: () => ({ notifyApiError: vi.fn() }),
}));

vi.mock("@core/hooks/useMutationAction.ts", () => ({
  useMutationAction: () => ({
    runMutationAction: async ({ action, onSuccess }: { action: () => Promise<unknown>; onSuccess?: () => void }) => {
      await action();
      onSuccess?.();
    },
  }),
}));

vi.mock("@core/hooks/useUserCapabilities.ts", () => ({
  useUserCapabilities: () => ({ canAdmin: h.canAdmin }),
}));

vi.mock("../../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ gcuVersion: h.gcuVersion }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useListAllTeamsQuery: () => ({ data: h.teams }),
  useDefaultTeamsForNewUsersQuery: (_arg: unknown, options?: { skip?: boolean }) => ({
    data: options?.skip ? undefined : h.defaultTeams,
  }),
  useSearchCandidateTeamAdminsQuery: () => ({ data: undefined }),
  useCreateTeamMutation: () => [vi.fn(), { isLoading: false }],
  useSetDefaultTeamsForNewUsersMutation: () => [h.setDefaultTeams, { isLoading: false }],
}));

import AdminTeamsPage from "./AdminTeamsPage";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

function render() {
  act(() => {
    root.render(<AdminTeamsPage />);
  });
}

function rerender() {
  act(() => root.unmount());
  root = createRoot(container);
  render();
}

const defaultTeamSection = () =>
  Array.from(container.querySelectorAll("section")).find(
    (section) => section.querySelector("h2")?.textContent === "rework.adminTeams.defaultTeam.title",
  );

const searchInput = () => defaultTeamSection()!.querySelector("input")!;

beforeEach(() => {
  h.canAdmin = true;
  h.gcuVersion = "v1";
  h.defaultTeams = [{ team_id: "uid-beta", name: "Beta" }] satisfies DefaultTeam[];
  h.setDefaultTeams.mockReset();
  h.setDefaultTeams.mockReturnValue({ unwrap: () => Promise.resolve() });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("AdminTeamsPage layout", () => {
  it("puts the actions above the teams list, which can grow long", () => {
    render();
    const titles = Array.from(container.querySelectorAll("h2")).map((h2) => h2.textContent);
    expect(titles).toEqual([
      "rework.adminTeams.defaultTeam.title",
      "rework.adminTeams.createTeam.title",
      "rework.adminTeams.existingTeams.title",
    ]);
  });
});

describe("AdminTeamsPage default teams for new users", () => {
  it("is hidden from a team_manager who is not platform_admin", () => {
    h.canAdmin = false;
    render();
    expect(defaultTeamSection()).toBeUndefined();
  });

  it("warns that the setting never applies when GCU is disabled", () => {
    const gcuDisabled = () => defaultTeamSection()!.textContent?.includes("rework.adminTeams.defaultTeam.gcuDisabled");
    render();
    expect(gcuDisabled()).toBe(false);

    h.gcuVersion = null;
    rerender();
    expect(gcuDisabled()).toBe(true);
  });

  it("says there is no default team only once the server answered an empty list", () => {
    const saysNone = () => defaultTeamSection()!.textContent?.includes("rework.adminTeams.defaultTeam.none");
    h.defaultTeams = undefined;
    render();
    expect(saysNone()).toBe(false);
    expect(searchInput().disabled).toBe(true);

    h.defaultTeams = [];
    rerender();
    expect(saysNone()).toBe(true);
    expect(searchInput().disabled).toBe(false);
  });

  it("shows the current defaults and offers the other teams by name", () => {
    render();
    act(() => searchInput().focus());

    const section = defaultTeamSection()!;
    const options = Array.from(section.querySelectorAll('[role="option"]')).map((option) => option.textContent);
    expect(options).toEqual(["Alpha", "Gamma"]);
    expect(section.textContent).toContain("Beta");
    expect(section.textContent).not.toContain("uid-");
  });

  it("adds the team picked in the search to the ones already set", async () => {
    render();
    act(() => searchInput().focus());
    await act(async () => {
      searchInput().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    });

    expect(h.setDefaultTeams).toHaveBeenCalledWith({
      setDefaultTeamsForNewUsersRequest: { team_ids: ["uid-beta", "uid-alpha"] },
    });
  });

  it("removes one default team and keeps the others", async () => {
    h.defaultTeams = [
      { team_id: "uid-beta", name: "Beta" },
      { team_id: "uid-gamma", name: "Gamma" },
    ];
    render();
    const betaChip = Array.from(defaultTeamSection()!.querySelectorAll("li")).find((li) =>
      li.textContent?.includes("Beta"),
    )!;
    await act(async () => betaChip.querySelector("button")!.click());

    expect(h.setDefaultTeams).toHaveBeenCalledWith({
      setDefaultTeamsForNewUsersRequest: { team_ids: ["uid-gamma"] },
    });
  });
});
