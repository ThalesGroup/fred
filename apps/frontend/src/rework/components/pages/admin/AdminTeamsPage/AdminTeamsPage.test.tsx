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

const h = vi.hoisted(() => ({
  canAdmin: true,
  gcuVersion: "v1" as string | null,
  teams: [
    { id: "uid-alpha", name: "Alpha" },
    { id: "uid-beta", name: "Beta" },
  ],
  defaultTeam: { team_id: "uid-beta", name: "Beta" } as { team_id: string; name: string } | null | undefined,
  setDefaultTeam: vi.fn(),
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
  useDefaultTeamForNewUsersQuery: (_arg: unknown, options?: { skip?: boolean }) => ({
    data: options?.skip ? undefined : h.defaultTeam,
  }),
  useSearchCandidateTeamAdminsQuery: () => ({ data: undefined }),
  useCreateTeamMutation: () => [vi.fn(), { isLoading: false }],
  useSetDefaultTeamForNewUsersMutation: () => [h.setDefaultTeam, { isLoading: false }],
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

const defaultTeamSection = () =>
  Array.from(container.querySelectorAll("section")).find(
    (section) => section.querySelector("h2")?.textContent === "rework.adminTeams.defaultTeam.title",
  );

beforeEach(() => {
  h.canAdmin = true;
  h.gcuVersion = "v1";
  h.defaultTeam = { team_id: "uid-beta", name: "Beta" };
  h.setDefaultTeam.mockReset();
  h.setDefaultTeam.mockReturnValue({ unwrap: () => Promise.resolve() });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("AdminTeamsPage default team for new users", () => {
  it("is hidden from a team_manager who is not platform_admin", () => {
    h.canAdmin = false;
    render();
    expect(defaultTeamSection()).toBeUndefined();
  });

  it("warns that the setting never applies when GCU is disabled", () => {
    const gcuDisabled = () => defaultTeamSection()!.textContent?.includes("rework.adminTeams.defaultTeam.gcuDisabled");
    render();
    expect(gcuDisabled()).toBe(false);

    act(() => root.unmount());
    root = createRoot(container);
    h.gcuVersion = null;
    render();
    expect(gcuDisabled()).toBe(true);
  });

  it("says there is no default team only once the server answered null", () => {
    const saysNone = () => defaultTeamSection()!.textContent?.includes("rework.adminTeams.defaultTeam.none");
    h.defaultTeam = undefined;
    render();
    expect(saysNone()).toBe(false);

    act(() => root.unmount());
    root = createRoot(container);
    h.defaultTeam = null;
    render();
    expect(saysNone()).toBe(true);
  });

  it("shows the current default and offers the other teams by name", () => {
    render();
    const section = defaultTeamSection()!;
    act(() => section.querySelector("input")!.focus());

    const options = Array.from(section.querySelectorAll('[role="option"]')).map((option) => option.textContent);
    expect(options).toEqual(["Alpha"]);
    expect(section.textContent).toContain("Beta");
    expect(section.textContent).not.toContain("uid-");
  });

  it("sets the team picked in the search", async () => {
    render();
    const input = defaultTeamSection()!.querySelector("input")!;
    act(() => input.focus());
    await act(async () => {
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    });

    expect(h.setDefaultTeam).toHaveBeenCalledWith({ setDefaultTeamForNewUsersRequest: { team_id: "uid-alpha" } });
  });

  it("clears the default team", async () => {
    render();
    const clear = defaultTeamSection()!.querySelector(
      'button[aria-label="rework.adminTeams.defaultTeam.clear"]',
    ) as HTMLButtonElement;
    await act(async () => clear.click());

    expect(h.setDefaultTeam).toHaveBeenCalledWith({ setDefaultTeamForNewUsersRequest: { team_id: null } });
  });
});
