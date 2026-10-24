// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  user: "priya",
  roles: ["member", "personal_space_creator"],
  personal: false,
  fail: false,
  navigate: vi.fn(),
  open: vi.fn(),
  refetch: vi.fn(() => ({ unwrap: async () => [{ id: "personal" }, { id: "private-priya" }, { id: "new-personal" }] })),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-router-dom", () => ({
  useNavigate: () => state.navigate,
  Link: ({ children, to }) => <a href={typeof to === "string" ? to : to.pathname}>{children}</a>,
}));
vi.mock("../../../../../../security/KeycloakService", () => ({
  KeyCloakService: { GetUserFullName: () => state.user },
}));
vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMeQuery: () => ({ data: { user_id: state.user } }),
  useMySpacesQuery: () => {
    const data = [
      { id: "org", kind: "organization", path: ["org"], name: "Demo", roles: state.roles },
      { id: "fredlab", kind: "team", name: "fredlab", roles: ["admin", "editor", "analyst"] },
      ...(state.personal
        ? [{ id: "personal", kind: "personal", name: "priya", personal_owner: "priya", roles: ["member"] }]
        : []),
    ];
    return {
      refetch: state.refetch,
      isError: state.fail,
      data,
      currentData: data,
    };
  },
  useCreatePersonalSpaceMutation: () => [state.open, { isLoading: false }],
}));
vi.mock("../../../../../../hooks/useFrontendBootstrap", () => ({ useFrontendBootstrap: () => ({}) }));
vi.mock("../../../../../../hooks/useFrontendProperties", () => ({ useFrontendProperties: () => ({}) }));
vi.mock("@shared/atoms/UserAvatar/UserAvatar.tsx", () => ({ default: () => <span>avatar</span> }));
vi.mock("@shared/atoms/TeamInitials/TeamInitials.tsx", () => ({ default: () => <span>initials</span> }));
vi.mock("@shared/molecules/NavPanelHeader/NavPanelHeader", () => ({ default: () => <span>spaces</span> }));
vi.mock("@shared/molecules/SearchInput/SearchInput", () => ({ default: () => <input /> }));
import HomeNavPanel from "./HomeNavPanel";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let node: HTMLDivElement;
let root: ReturnType<typeof createRoot>;
async function render() {
  if (!node) {
    node = document.createElement("div");
    document.body.append(node);
    root = createRoot(node);
  }
  await act(async () => root.render(<HomeNavPanel />));
}
afterEach(async () => {
  if (root) await act(async () => root.unmount());
  node?.remove();
  node = undefined!;
  root = undefined!;
  state.user = "priya";
  state.roles = ["member", "personal_space_creator"];
  state.personal = false;
  state.fail = false;
  vi.clearAllMocks();
});
const entry = () => node.querySelector<HTMLButtonElement>('button[aria-label="rework.sidebar.team.userTeam"]');
it("creates only on explicit action, blocks duplicate activation and ignores completion after account change", async () => {
  let resolve!: (value: { id: string }) => void;
  state.open.mockReturnValue({
    unwrap: () =>
      new Promise((done) => {
        resolve = done;
      }),
  });
  await render();
  expect(state.open).not.toHaveBeenCalled();
  await act(async () => {
    entry()!.click();
    entry()!.click();
  });
  expect(state.open).toHaveBeenCalledExactlyOnceWith({ createPersonalSpace: { organization_id: "org" } });
  state.user = "bob";
  await render();
  await act(async () => resolve({ id: "private-priya" }));
  expect(state.navigate).not.toHaveBeenCalled();
});
it("allows reuse without creation eligibility and uses the returned UUID", async () => {
  state.roles = ["member"];
  state.personal = true;
  state.open.mockReturnValue({ unwrap: async () => ({ id: "private-priya" }) });
  await render();
  expect(node.querySelectorAll("a").length).toBe(1);
  await act(async () => entry()!.click());
  expect(state.navigate).toHaveBeenCalledWith("/team/private-priya/agents");
});
it("hides the entry without eligibility or personal access and on authority failure", async () => {
  state.roles = ["member"];
  await render();
  expect(entry()).toBeNull();
  state.roles.push("personal_space_creator");
  state.fail = true;
  await render();
  expect(entry()).toBeNull();
});
it("shows failure, does not navigate and permits another deliberate action", async () => {
  state.open.mockReturnValue({
    unwrap: async () => {
      throw new Error("refused");
    },
  });
  await render();
  await act(async () => entry()!.click());
  expect(node.querySelector('[role="alert"]')).not.toBeNull();
  expect(state.navigate).not.toHaveBeenCalled();
  state.open.mockReturnValue({ unwrap: async () => ({ id: "personal" }) });
  await act(async () => entry()!.click());
  expect(state.navigate).toHaveBeenCalledOnce();
});

it("waits for refreshed memberships before selecting a newly created space", async () => {
  let resolve!: (value: { id: string }[]) => void;
  state.refetch.mockReturnValueOnce({
    unwrap: () =>
      new Promise((done) => {
        resolve = done;
      }),
  });
  state.open.mockReturnValue({ unwrap: async () => ({ id: "new-personal" }) });
  await render();
  await act(async () => entry()!.click());
  expect(state.navigate).not.toHaveBeenCalled();
  expect(entry()!.disabled).toBe(true);
  await act(async () => resolve([{ id: "new-personal" }]));
  expect(state.navigate).toHaveBeenCalledWith("/team/new-personal/agents");
});
it("keeps selection unchanged if creation succeeds but membership refresh fails", async () => {
  state.refetch.mockReturnValueOnce({
    unwrap: async () => {
      throw new Error("unavailable");
    },
  });
  state.open.mockReturnValue({ unwrap: async () => ({ id: "new-personal" }) });
  await render();
  await act(async () => entry()!.click());
  expect(state.navigate).not.toHaveBeenCalled();
  expect(node.querySelector('[role="alert"]')).not.toBeNull();
  expect(entry()!.disabled).toBe(false);
});

it("does not select an absent UUID when refetch joins a stale pending query", async () => {
  state.refetch.mockReturnValueOnce({ unwrap: async () => [{ id: "org" }] });
  state.open.mockReturnValue({ unwrap: async () => ({ id: "new-personal" }) });
  await render();
  await act(async () => entry()!.click());
  expect(state.navigate).not.toHaveBeenCalled();
  expect(node.querySelector('[role="alert"]')).not.toBeNull();
  expect(entry()!.disabled).toBe(false);
});

it("keeps the team list and ordinary agents destination without an organization row", async () => {
  await render();
  expect(node.textContent).toContain("fredlab");
  expect(node.textContent).toContain("rework.home.yourTeams");
  expect(node.textContent).not.toContain("Demo");
  expect(node.querySelector('a[href="/team/fredlab/agents"]')).not.toBeNull();
  expect(node.textContent).toContain("rework.teamRoles.team_admin");
  expect(node.textContent).not.toContain("rework.manager.hierarchy");
});
