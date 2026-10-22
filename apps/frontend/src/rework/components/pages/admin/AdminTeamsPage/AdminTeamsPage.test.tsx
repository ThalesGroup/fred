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

// Only a platform_admin picks where new users land and edits teams; the picker
// names teams, never their ids.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type DefaultTeam = { team_id: string; name: string };

const h = vi.hoisted(() => ({
  canAdmin: true,
  canManageTeams: true,
  canManagePlatformAccess: true,
  admissionEnabled: true,
  admissionFetching: false,
  admissionTeams: [
    { team_id: "uid-alpha", name: "Alpha", allowed: true, free: false },
    { team_id: "uid-beta", name: "Beta", allowed: false, free: true },
  ],
  admissionQuery: vi.fn(),
  admissionTeamsQuery: vi.fn(),
  setAdmissionTeam: vi.fn(),
  gcuVersion: "v1" as string | null,
  teams: [
    {
      id: "uid-alpha",
      name: "Alpha",
      description: "Automates the drafting of reports.",
      admins: [{ id: "u-zoe", first_name: "Zoe", last_name: "Zed", username: "zoe" }],
    },
    { id: "uid-beta", name: "Beta" },
    {
      id: "uid-gamma",
      name: "Gamma",
      admins: [
        { id: "u-max", first_name: "Max", last_name: "Mill", username: "max" },
        { id: "u-ian", first_name: "Ian", last_name: "Iles", username: "ian" },
      ],
      pending_admin_ids: ["u-ian"],
    },
  ] as Record<string, unknown>[],
  defaultTeams: undefined as { team_id: string; name: string }[] | undefined,
  setDefaultTeams: vi.fn(),
  createTeam: vi.fn(),
  editTeam: vi.fn(),
  showError: vi.fn(),
  notifyApiError: vi.fn(),
  candidateAdmins: {
    ad: [{ id: "u-ada", first_name: "Ada", last_name: "Admin", username: "ada" }],
  } as Record<string, { id: string; first_name: string; last_name: string; username: string }[]>,
  loadingAdminQueries: new Set<string>(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: h.showError }),
}));

vi.mock("@core/hooks/useApiErrorToast.ts", () => ({
  useApiErrorToast: () => ({ notifyApiError: h.notifyApiError }),
}));

vi.mock("@core/hooks/useMutationAction.ts", () => ({
  useMutationAction: () => ({
    runMutationAction: async ({
      action,
      onSuccess,
      onError,
    }: {
      action: () => Promise<unknown>;
      onSuccess?: () => void;
      onError?: (error: unknown) => void;
    }) => {
      try {
        await action();
      } catch (error) {
        onError?.(error);
        return;
      }
      onSuccess?.();
    },
  }),
}));

vi.mock("@core/hooks/useUserCapabilities.ts", () => ({
  useUserCapabilities: () => ({
    canAdmin: h.canAdmin,
    canManageTeams: h.canManageTeams,
    canManagePlatformAccess: h.canManagePlatformAccess,
  }),
}));

vi.mock("../../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ gcuVersion: h.gcuVersion }),
}));
vi.mock("../../../../../common/config", () => ({
  getConfig: () => ({ platform_access_enabled: h.admissionEnabled }),
}));
vi.mock("../PlatformAccessPage/PlatformAccessLinkManager", () => ({
  default: ({ team }: { team: { team_id: string; free: boolean } }) => (
    <div role="dialog" data-team={team.team_id} data-free={team.free} />
  ),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useListAllTeamsQuery: () => ({ data: h.teams }),
  useDefaultTeamsForNewUsersQuery: (_arg: unknown, options?: { skip?: boolean }) => ({
    data: options?.skip ? undefined : h.defaultTeams,
  }),
  // Mirrors RTK Query: `currentData` is undefined while the search for a new query is in flight.
  useSearchCandidateTeamAdminsQuery: ({ query }: { query: string }) => {
    const loading = h.loadingAdminQueries.has(query);
    return {
      currentData: loading ? undefined : (h.candidateAdmins[query] ?? h.candidateAdmins.ad),
      data: h.candidateAdmins.ad,
      isFetching: loading,
    };
  },
  useCreateTeamMutation: () => [h.createTeam, { isLoading: false }],
  useEditTeamRegistryMutation: () => [h.editTeam, { isLoading: false }],
  useSetDefaultTeamsForNewUsersMutation: () => [h.setDefaultTeams, { isLoading: false }],
  usePlatformAccessStateQuery: (arg: unknown, options: { skip: boolean }) => {
    h.admissionQuery(arg, options);
    return { data: options.skip ? undefined : {}, isFetching: h.admissionFetching };
  },
  usePlatformAccessTeamsQuery: (arg: unknown, options: { skip: boolean }) => {
    h.admissionTeamsQuery(arg, options);
    return { data: options.skip ? undefined : h.admissionTeams };
  },
  useSetPlatformTeamMutation: () => [h.setAdmissionTeam, { isLoading: false }],
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
  h.canManageTeams = true;
  h.canManagePlatformAccess = true;
  h.admissionEnabled = true;
  h.admissionFetching = false;
  h.admissionQuery.mockClear();
  h.admissionTeamsQuery.mockClear();
  h.setAdmissionTeam.mockReset();
  h.setAdmissionTeam.mockReturnValue({ unwrap: () => Promise.resolve() });
  h.gcuVersion = "v1";
  h.defaultTeams = [{ team_id: "uid-beta", name: "Beta" }] satisfies DefaultTeam[];
  h.setDefaultTeams.mockReset();
  h.setDefaultTeams.mockReturnValue({ unwrap: () => Promise.resolve() });
  h.createTeam.mockReset();
  h.createTeam.mockReturnValue({ unwrap: () => Promise.resolve() });
  h.editTeam.mockReset();
  h.editTeam.mockReturnValue({ unwrap: () => Promise.resolve() });
  h.showError.mockReset();
  h.notifyApiError.mockReset();
  h.loadingAdminQueries.clear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const buttonByText = (scope: ParentNode, text: string) =>
  Array.from(scope.querySelectorAll<HTMLButtonElement>("button")).find((button) => button.textContent?.includes(text));
const editButtons = () =>
  container.querySelectorAll<HTMLButtonElement>('button[aria-label="rework.adminTeams.editTeam.openAria"]');

describe("AdminTeamsPage layout", () => {
  it("creates from the header and lists teams right after the default-teams setting", () => {
    render();
    const titles = Array.from(container.querySelectorAll("h2")).map((h2) => h2.textContent);
    expect(titles).toEqual(["rework.adminTeams.defaultTeam.title", "rework.adminTeams.existingTeams.title"]);
    const create = buttonByText(container, "rework.adminTeams.createTeam.open")!;
    const firstSection = container.querySelector("h2")!;
    expect(create.compareDocumentPosition(firstSection) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows the description as one line under the team name", () => {
    render();
    expect(container.querySelector('[title="Automates the drafting of reports."]')?.textContent).toBe(
      "Automates the drafting of reports.",
    );
  });

  it("offers Edit on every row to a platform admin only", () => {
    render();
    expect(editButtons()).toHaveLength(3);
    h.canAdmin = false;
    rerender();
    expect(editButtons()).toHaveLength(0);
    expect(buttonByText(container, "rework.adminTeams.createTeam.open")).toBeDefined();
  });

  it("marks the admins still awaiting the charter next to the avatars", () => {
    render();
    const marker = container.querySelector('[title="rework.adminTeams.pendingAdminHint"]');
    expect(marker?.textContent).toBe("rework.adminTeams.existingTeams.pendingCount");
    expect(container.querySelectorAll('[title="rework.adminTeams.pendingAdminHint"]')).toHaveLength(1);
  });
});

describe("AdminTeamsPage Free enrollment", () => {
  it("does not expose controls or request admission authority for ordinary team managers", () => {
    h.canAdmin = false;
    h.canManagePlatformAccess = false;
    render();
    expect(h.admissionQuery).toHaveBeenLastCalledWith(undefined, { skip: true });
    expect(h.admissionTeamsQuery).toHaveBeenLastCalledWith(undefined, { skip: true });
    expect(container.querySelector('input[aria-label^="rework.platformAccess.free"]')).toBeNull();
    expect(container.textContent).not.toContain("rework.platformAccess.links.manage");
  });

  it("skips admission controls when authenticated admission administration is unavailable", () => {
    h.admissionEnabled = false;
    render();
    expect(h.admissionTeamsQuery).toHaveBeenLastCalledWith(undefined, { skip: true });
    expect(container.textContent).not.toContain("rework.platformAccess.links.manage");
  });

  it("changes Free while preserving independent authorization for the exact team", async () => {
    render();
    const toggle = container.querySelector<HTMLInputElement>('input[aria-label="rework.platformAccess.free Alpha"]')!;
    expect(toggle.checked).toBe(false);
    await act(async () => toggle.click());
    expect(h.setAdmissionTeam).toHaveBeenCalledWith({
      teamId: "uid-alpha",
      setPlatformAccessTeam: { allowed: true, free: true },
    });
  });

  it("retains invitation history for teams whose Free flag is disabled", () => {
    render();
    const manage = [...container.querySelectorAll<HTMLButtonElement>("button")].find(
      (button) => button.textContent === "rework.platformAccess.links.manage",
    )!;
    expect(manage.disabled).toBe(false);
    act(() => manage.click());
    const dialog = container.querySelector('[role="dialog"]')!;
    expect(dialog.getAttribute("data-team")).toBe("uid-alpha");
    expect(dialog.getAttribute("data-free")).toBe("false");
    h.canAdmin = false;
    h.canManagePlatformAccess = false;
    act(() => root.render(<AdminTeamsPage />));
    expect(container.querySelector('[role="dialog"]')).toBeNull();
  });

  it("disables team actions until authority is loaded and hides missing team state behind disabled controls", () => {
    h.admissionFetching = true;
    render();
    const toggles = [
      ...container.querySelectorAll<HTMLInputElement>('input[aria-label^="rework.platformAccess.free"]'),
    ];
    expect(toggles.length).toBeGreaterThan(0);
    expect(toggles.every((toggle) => toggle.disabled)).toBe(true);
    h.admissionFetching = false;
    act(() => root.render(<AdminTeamsPage />));
    expect(
      container.querySelector<HTMLInputElement>('input[aria-label="rework.platformAccess.free Gamma"]')!.disabled,
    ).toBe(true);
  });

  it("lets an access manager manage Free without team registry controls", () => {
    h.canAdmin = false;
    h.canManageTeams = false;
    render();
    expect(container.textContent).toContain("rework.platformAccess.links.manage");
    expect(editButtons()).toHaveLength(0);
    expect(buttonByText(container, "rework.adminTeams.createTeam.open")).toBeUndefined();
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
    const options = Array.from(document.querySelectorAll('[role="option"]')).map((option) => option.textContent);
    expect(options).toEqual(["Alpha", "Gamma"]);
    expect(section.textContent).toContain("Beta");
    expect(section.textContent).not.toContain("uid-");
    const betaChip = section.querySelector('span[title="Beta"]')!;
    expect(searchInput().compareDocumentPosition(betaChip) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
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

// React tracks the value through the native setter, not the property.
const type = (field: HTMLInputElement | HTMLTextAreaElement, value: string) => {
  const proto = field instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  act(() => {
    Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(field, value);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
};
const dialog = () => document.body.querySelector<HTMLElement>('[role="dialog"][aria-modal="true"]');

describe("AdminTeamsPage team creation", () => {
  const submit = () => buttonByText(dialog()!, "rework.adminTeams.createTeam.submit")!;
  const openAndFillNameAndAdmin = async () => {
    render();
    act(() => buttonByText(container, "rework.adminTeams.createTeam.open")!.click());
    const [nameInput, adminInput] = Array.from(dialog()!.querySelectorAll("input"));
    type(nameInput, "  Ops  ");
    act(() => adminInput.focus());
    type(adminInput, "ad");
    await act(async () => {
      adminInput.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    });
  };

  it("keeps the create action unavailable and explains the minimum for a short description", async () => {
    await openAndFillNameAndAdmin();
    const description = dialog()!.querySelector("textarea")!;
    type(description, "Too short");
    act(() => {
      description.focus();
      description.blur();
    });

    expect(submit().disabled).toBe(true);
    expect(dialog()!.textContent).toContain("rework.teamDescription.tooShort");
    expect(dialog()!.textContent).toContain("9 / 500");
    expect(dialog()!.textContent).not.toContain("rework.teamDescription.maxReached");
  });

  it("says why typing stops once the description reaches 500 characters", async () => {
    await openAndFillNameAndAdmin();
    type(dialog()!.querySelector("textarea")!, "a".repeat(500));
    expect(dialog()!.textContent).toContain("rework.teamDescription.maxReached");
    expect(submit().disabled).toBe(false);
  });

  it("keeps the admin chips in their own spaced row under the search field", async () => {
    await openAndFillNameAndAdmin();
    const chips = dialog()!.querySelector("ul")!;
    const search = dialog()!.querySelectorAll("input")[1];
    expect(chips.parentElement).toBe(search.closest("[data-open]")!.parentElement);
    expect(chips.parentElement!.className).toContain("adminsPicker");
  });

  it("shows our own message when the name is taken", async () => {
    h.createTeam.mockReturnValue({
      unwrap: () =>
        Promise.reject({ status: 409, data: { detail: "Team 'Ops' already exists.", code: "team_name_taken" } }),
    });
    await openAndFillNameAndAdmin();
    type(dialog()!.querySelector("textarea")!, "Automate the drafting of our monthly reports.");
    await act(async () => submit().click());
    expect(h.showError).toHaveBeenCalledWith({
      summary: "rework.adminTeams.createTeam.errors.summary",
      detail: "rework.adminTeams.refusals.teamNameTaken",
    });
    expect(h.notifyApiError).not.toHaveBeenCalled();
  });

  it("sends the trimmed description once it is valid and closes", async () => {
    await openAndFillNameAndAdmin();
    type(dialog()!.querySelector("textarea")!, "  Automate the drafting of our monthly reports.  ");

    expect(submit().disabled).toBe(false);
    await act(async () => submit().click());
    expect(h.createTeam).toHaveBeenCalledWith({
      createTeamRequest: {
        name: "Ops",
        description: "Automate the drafting of our monthly reports.",
        initial_team_admin_ids: ["u-ada"],
      },
    });
    expect(dialog()).toBeNull();
  });
});

describe("AdminTeamsPage team edit", () => {
  const save = () => buttonByText(dialog()!, "rework.adminTeams.editTeam.submit")!;
  const openAlpha = () => {
    render();
    act(() => editButtons()[0].click());
  };

  it("opens prefilled and saves nothing until something changes", () => {
    openAlpha();
    expect(dialog()!.querySelector("input")!.value).toBe("Alpha");
    expect(dialog()!.querySelector("textarea")!.value).toBe("Automates the drafting of reports.");
    expect(dialog()!.textContent).toContain("Zoe Zed");
    expect(save().disabled).toBe(true);
  });

  it("sends only the changed description", async () => {
    openAlpha();
    type(dialog()!.querySelector("textarea")!, "Automates the drafting of every monthly report.");
    await act(async () => save().click());
    expect(h.editTeam).toHaveBeenCalledWith({
      teamId: "uid-alpha",
      editTeamRegistryRequest: { description: "Automates the drafting of every monthly report." },
    });
  });

  it("sends the admin diff and refuses an empty roster", async () => {
    openAlpha();
    const removeZoe = () => dialog()!.querySelector("li button") as HTMLButtonElement;
    act(() => removeZoe().click());
    expect(save().disabled).toBe(true);

    const adminInput = dialog()!.querySelectorAll("input")[1];
    act(() => adminInput.focus());
    type(adminInput, "ad");
    await act(async () => {
      adminInput.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    });
    await act(async () => save().click());
    expect(h.editTeam).toHaveBeenCalledWith({
      teamId: "uid-alpha",
      editTeamRegistryRequest: { add_admin_ids: ["u-ada"], remove_admin_ids: ["u-zoe"] },
    });
  });

  it("does not offer the previous search's admins while a new search loads", async () => {
    h.loadingAdminQueries.add("bo");
    openAlpha();
    const adminInput = dialog()!.querySelectorAll("input")[1];
    act(() => adminInput.focus());
    type(adminInput, "ad");
    expect(document.body.textContent).toContain("Ada Admin");

    type(adminInput, "bo");
    expect(document.body.textContent).not.toContain("Ada Admin");
    expect(document.body.textContent).toContain("rework.adminTeams.createTeam.adminsSearching");
    await act(async () => {
      adminInput.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    });
    expect(dialog()!.querySelectorAll("ul li")).toHaveLength(1);
  });

  it("marks a pending admin's chip", () => {
    render();
    act(() => editButtons()[2].click());
    const chips = Array.from(dialog()!.querySelectorAll("ul li"));
    const ian = chips.find((li) => li.textContent?.includes("Ian Iles"))!;
    const max = chips.find((li) => li.textContent?.includes("Max Mill"))!;
    expect(ian.textContent).toContain("rework.adminTeams.pendingAdmin");
    expect(ian.querySelector('[title="rework.adminTeams.pendingAdminHint"]')).not.toBeNull();
    expect(max.textContent).not.toContain("rework.adminTeams.pendingAdmin");
  });

  it.each([
    ["team_last_admin", "rework.adminTeams.refusals.lastActiveAdmin"],
    ["team_admin_pending_charter", "rework.adminTeams.refusals.pendingCharter"],
  ])("shows our own message for the %s refusal", async (code, message) => {
    h.editTeam.mockReturnValue({
      unwrap: () => Promise.reject({ status: 409, data: { detail: "English detail.", code } }),
    });
    openAlpha();
    type(dialog()!.querySelector("textarea")!, "Automates the drafting of every monthly report.");
    await act(async () => save().click());
    expect(h.showError).toHaveBeenCalledWith({ summary: "rework.adminTeams.editTeam.errors.summary", detail: message });
  });

  it("keeps the generic handling for an unknown refusal", async () => {
    const error = { status: 500, data: { detail: "boom" } };
    h.editTeam.mockReturnValue({ unwrap: () => Promise.reject(error) });
    openAlpha();
    type(dialog()!.querySelector("textarea")!, "Automates the drafting of every monthly report.");
    await act(async () => save().click());
    expect(h.showError).not.toHaveBeenCalled();
    expect(h.notifyApiError).toHaveBeenCalledWith(
      error,
      expect.objectContaining({ summary: "rework.adminTeams.editTeam.errors.summary" }),
    );
  });
});
