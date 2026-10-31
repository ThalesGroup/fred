// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  user: "priya",
  roles: ["owner"],
  teamRoles: ["editor", "analyst"],
  teamKind: "team",
  personal: false,
  organization: true,
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
      ...(state.organization
        ? [{ id: "org", kind: "organization", path: ["org"], name: "Demo", organization_id: "org", roles: state.roles }]
        : []),
      { id: "fredlab", kind: state.teamKind, name: "fredlab", organization_id: "org", roles: state.teamRoles },
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
  state.roles = ["owner"];
  state.teamRoles = ["editor", "analyst"];
  state.teamKind = "team";
  state.personal = false;
  state.organization = true;
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
it("reuses the existing personal space and uses the returned UUID", async () => {
  state.roles = ["owner"];
  state.personal = true;
  state.open.mockReturnValue({ unwrap: async () => ({ id: "private-priya" }) });
  await render();
  expect(node.querySelectorAll("a").length).toBe(1);
  await act(async () => entry()!.click());
  expect(state.navigate).toHaveBeenCalledWith("/team/private-priya/agents");
});
it.each(["organization", "team", "project"])("offers a personal space to an owner at %s level", async (kind) => {
  state.roles = kind === "organization" ? ["owner"] : ["member"];
  state.teamRoles = kind === "organization" ? [] : ["owner"];
  state.teamKind = kind === "project" ? "project" : "team";
  await render();
  expect(entry()).not.toBeNull();
  expect(state.open).not.toHaveBeenCalled();
});
it.each(["member", "editor", "analyst"])("offers a personal space to a business %s", async (role) => {
  state.roles = [role];
  state.teamRoles = [];
  await render();
  expect(entry()).not.toBeNull();
});
it("hides the entry for a technical admin without a business role", async () => {
  state.roles = ["organization_admin"];
  state.teamRoles = [];
  state.personal = true;
  await render();
  expect(entry()).toBeNull();
});
it("allows mixed technical and business roles but hides the entry on authority failure", async () => {
  state.roles = ["organization_admin", "owner"];
  await render();
  expect(entry()).not.toBeNull();
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
  state.organization = false;
  state.teamRoles = ["owner", "editor", "analyst"];
  await render();
  expect(node.textContent).toContain("rework.teamRoles.team_owner");
  expect(node.textContent).toContain("fredlab");
  expect(node.textContent).toContain("rework.home.yourTeams");
  expect(node.textContent).not.toContain("Demo");
  expect(node.querySelector('a[href="/team/fredlab/agents"]')).not.toBeNull();
  expect(node.textContent).toContain("rework.teamRoles.team_editor");
  expect(node.textContent).not.toContain("rework.manager.hierarchy");
});

it("heads Home with the section and the person's organization, read-only", async () => {
  await render();
  const heading = node.querySelector("h2");
  expect(heading?.textContent).toBe("rework.home.title");
  expect(heading?.closest("button")).toBeNull();
  expect(heading?.previousElementSibling?.textContent).toBe("Demo");
  expect(node.querySelector('[aria-haspopup="menu"]')).toBeNull();
});

it("keeps the Home title without an organization", async () => {
  state.organization = false;
  await render();
  expect(node.querySelector("h2")?.textContent).toBe("rework.home.title");
  expect(node.querySelector("h2")?.previousElementSibling).toBeNull();
});
