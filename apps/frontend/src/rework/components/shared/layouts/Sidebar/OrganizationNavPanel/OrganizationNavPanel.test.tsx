// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  extraSpaces: [] as {
    id: string;
    kind: string;
    name: string;
    parent_id: string;
    organization_id: string;
    roles: string[];
  }[],
  selected: undefined as string | undefined,
  hideTeam: false,
  user: "priya",
  roles: ["owner"],
  teamRoles: ["editor", "analyst"],
  teamKind: "team",
  personal: false,
  organization: true,
  otherOrganization: false,
  fail: false,
  organizationRead: false,
  organizationManage: false,
  locationState: null as unknown,
  contentArgs: vi.fn(),
  navigate: vi.fn(),
  open: vi.fn(),
  refetch: vi.fn(() => ({ unwrap: async () => [{ id: "personal" }, { id: "private-priya" }, { id: "new-personal" }] })),
}));
vi.mock("@core/hooks/useSpaceAccess", () => ({
  useSpaceAccess: (id: string | undefined, permission: string) => {
    const granted =
      (id === "org" || id === "other") &&
      (permission === "read" ? state.organizationRead : permission === "manage" && state.organizationManage);
    return { allowed: granted, offered: granted };
  },
}));
vi.mock("../useSpaceContentItems.tsx", () => ({
  useSpaceContentItems: (args: { teamId?: string; canReadContent: boolean }) => {
    state.contentArgs(args);
    return args.canReadContent
      ? [
          {
            type: "link",
            label: "rework.sidebar.team.menu.resources",
            linkProps: { to: `/team/${args.teamId}/resources` },
          },
        ]
      : [];
  },
}));
vi.mock("@shared/molecules/NavigationMenu/NavigationMenu.tsx", () => ({
  default: ({ items }) => (
    <nav data-content-menu>
      {items.map((item) => (
        <a key={item.linkProps.to} href={item.linkProps.to}>
          {item.label}
        </a>
      ))}
    </nav>
  ),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-router-dom", () => ({
  useNavigate: () => state.navigate,
  useLocation: () => ({ pathname: "/home", state: state.locationState }),
  Link: ({ children, to }) => <a href={typeof to === "string" ? to : to.pathname}>{children}</a>,
}));
vi.mock("../../../../../../security/KeycloakService", () => ({
  KeyCloakService: { GetUserFullName: () => state.user },
}));
vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetMyAvatarQuery: () => ({ currentData: undefined }),
  useMeQuery: () => ({ data: { user_id: state.user } }),
  useGetTeamAvatarQuery: () => ({ currentData: undefined }),
  useMySpacesQuery: () => {
    const data = [
      ...(state.otherOrganization
        ? [
            {
              id: "other",
              kind: "organization",
              path: ["other"],
              name: "Other",
              organization_id: "other",
              roles: ["member"],
            },
          ]
        : []),
      ...(state.organization
        ? [{ id: "org", kind: "organization", path: ["org"], name: "Demo", organization_id: "org", roles: state.roles }]
        : []),
      ...(state.hideTeam
        ? []
        : [
            {
              id: "fredlab",
              kind: state.teamKind,
              name: "fredlab",
              parent_id: "org",
              organization_id: "org",
              roles: state.teamRoles,
            },
          ]),
      ...state.extraSpaces,
      ...(state.personal
        ? [
            {
              id: "personal",
              kind: "personal",
              name: "priya",
              organization_id: "org",
              personal_owner: "priya",
              roles: ["member"],
            },
          ]
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
vi.mock("@core/hooks/useWorkingOrganization", async () => {
  const api = await import("../../../../../../slices/controlPlane/controlPlaneApiEnhancements");
  return {
    useWorkingOrganization: () => {
      const memberships = api.useMySpacesQuery();
      const id = state.selected ?? (state.otherOrganization ? "other" : "org");
      const available = memberships.currentData?.some((space) => space.organization_id === id);
      const org = memberships.currentData?.find((space) => space.id === id && space.kind === "organization");
      return {
        memberships,
        organizationId: available && !state.fail ? id : undefined,
        organization: available ? { id, name: org?.name ?? "rework.home.organizationOf" } : undefined,
      };
    },
  };
});
vi.mock("../../../../../../hooks/useFrontendProperties", () => ({ useFrontendProperties: () => ({}) }));
vi.mock("@shared/atoms/UserAvatar/UserAvatar.tsx", () => ({ default: () => <span>avatar</span> }));
vi.mock("@shared/atoms/TeamInitials/TeamInitials.tsx", () => ({ default: () => <span>initials</span> }));
vi.mock("@shared/molecules/SearchInput/SearchInput.tsx", () => ({
  default: ({ value, onChange, ariaLabel }) => (
    <input aria-label={ariaLabel} value={value} onInput={(event) => onChange(event.currentTarget.value)} />
  ),
}));
import { setCurrentUserPreferences } from "../../../../../../app/userPreferences";
import OrganizationNavPanel from "./OrganizationNavPanel";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let node: HTMLDivElement;
let root: ReturnType<typeof createRoot>;
async function render() {
  if (!node) {
    node = document.createElement("div");
    document.body.append(node);
    root = createRoot(node);
  }
  await act(async () => root.render(<OrganizationNavPanel />));
}
afterEach(async () => {
  if (root) await act(async () => root.unmount());
  node?.remove();
  node = undefined!;
  root = undefined!;
  state.selected = undefined;
  state.extraSpaces = [];
  state.hideTeam = false;
  localStorage.clear();
  setCurrentUserPreferences({});
  state.user = "priya";
  state.roles = ["owner"];
  state.teamRoles = ["editor", "analyst"];
  state.teamKind = "team";
  state.personal = false;
  state.organization = true;
  state.otherOrganization = false;
  state.fail = false;
  state.organizationRead = false;
  state.organizationManage = false;
  state.locationState = null;
  vi.clearAllMocks();
});
const entry = () => node.querySelector<HTMLButtonElement>('button[aria-label="rework.home.personalSpace"]');
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
it("links straight to an existing personal space without opening it on the server", async () => {
  state.roles = ["owner"];
  state.personal = true;
  await render();
  expect(entry()).toBeNull();
  expect(node.querySelector('a[href="/team/personal/agents"]')?.textContent).toContain("rework.home.personalSpace");
  expect(state.open).not.toHaveBeenCalled();
});
it("captions organization roles beyond membership under the header, as team panels do", async () => {
  state.roles = ["member", "owner"];
  await render();
  expect(node.textContent).toContain("rework.teamRoles.team_owner");
  state.roles = ["member"];
  await render();
  expect(node.textContent).not.toContain("rework.teamRoles.team_owner");
  // A technical admin holds no business role: no caption, and never "Member".
  state.roles = ["organization_admin"];
  await render();
  expect(node.textContent).not.toContain("rework.teamRoles.team_member");
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
  expect(node.querySelector('a[href="/team/fredlab"]')).not.toBeNull();
  expect(node.textContent).toContain("rework.teamRoles.team_editor");
  expect(node.textContent).not.toContain("rework.manager.hierarchy");
});

it("heads Home with the person's organization under its kind, read-only", async () => {
  await render();
  const heading = node.querySelector("h2");
  expect(heading?.textContent).toBe("Demo");
  expect(heading?.closest("button")).toBeNull();
  expect(heading?.previousElementSibling?.textContent).toBe("rework.manager.kinds.organization");
  expect(node.querySelector('[aria-haspopup="menu"]')).toBeNull();
});

it("keeps the Home title without an organization", async () => {
  state.organization = false;
  state.hideTeam = true;
  await render();
  expect(node.querySelector("h2")?.textContent).toBe("rework.home.title");
  expect(node.querySelector("h2")?.previousElementSibling).toBeNull();
});

it("shows the organization's content menu only with the server's Read permission", async () => {
  state.roles = ["organization_admin"];
  await render();
  expect(node.querySelector("[data-content-menu]")).toBeNull();
  state.organizationRead = true;
  await render();
  expect(node.querySelector('[data-content-menu] a[href="/team/org/resources"]')).not.toBeNull();
  expect(state.contentArgs).toHaveBeenLastCalledWith(
    expect.objectContaining({ teamId: "org", canReadContent: true, isPersonalTeam: false }),
  );
  state.fail = true;
  await render();
  expect(node.querySelector("[data-content-menu]")).toBeNull();
});

it("offers the organization's gear only with Manage, opening its settings with focus inside", async () => {
  await render();
  const gear = () =>
    node.querySelector<HTMLButtonElement>('button[aria-label="rework.teamSettings.navigation.settings"]');
  expect(gear()).toBeNull();
  state.organizationManage = true;
  await render();
  await act(async () => gear()!.click());
  expect(state.navigate).toHaveBeenCalledWith("/team/org/settings/members", { state: { focusPanel: true } });
});

it("returns focus to the gear when coming back from the organization settings", async () => {
  state.organizationManage = true;
  state.locationState = { focusSettings: true };
  await render();
  expect(document.activeElement?.getAttribute("aria-label")).toBe("rework.teamSettings.navigation.settings");
});

it("follows the selected organization for its content and the personal space", async () => {
  state.otherOrganization = true;
  state.organizationRead = true;
  state.roles = ["member"];
  state.open.mockReturnValue({ unwrap: async () => ({ id: "new-personal" }) });
  await render();
  expect(node.querySelector('a[href="/team/other/resources"]')).not.toBeNull();
  state.selected = "org";
  await render();
  expect(node.querySelector('a[href="/team/org/resources"]')).not.toBeNull();
  expect(node.querySelector('a[href="/team/other/resources"]')).toBeNull();
  await act(async () => entry()!.click());
  expect(state.open).toHaveBeenCalledExactlyOnceWith({ createPersonalSpace: { organization_id: "org" } });
});

const atlas = {
  id: "atlas",
  kind: "project",
  name: "Atlas",
  parent_id: "fredlab",
  organization_id: "org",
  roles: ["member"],
};

it("lists only the teams with a direct role, never projects, and filters them by search", async () => {
  state.extraSpaces = [
    atlas,
    { id: "alpha", kind: "team", name: "Alpha", parent_id: "org", organization_id: "org", roles: [] },
  ];
  await render();
  expect(node.querySelector('a[href="/team/fredlab"]')).not.toBeNull();
  expect(node.querySelector('a[href="/team/atlas"]')).toBeNull();
  expect(node.querySelector('a[href="/team/alpha"]')).toBeNull();
  await act(async () =>
    node.querySelector<HTMLButtonElement>('button[aria-label="rework.home.searchPlaceholder"]')!.click(),
  );
  const search = node.querySelector<HTMLInputElement>('input[aria-label="rework.home.searchPlaceholder"]')!;
  await act(async () => {
    search.value = "missing";
    search.dispatchEvent(new Event("input", { bubbles: true }));
  });
  expect(node.querySelector('a[href="/team/fredlab"]')).toBeNull();
  expect(node.querySelector('[role="status"]')?.textContent).toBe("rework.home.noTeams");
});

it("empties and closes the search on Escape, back on its button", async () => {
  await render();
  const button = () => node.querySelector<HTMLButtonElement>('button[aria-label="rework.home.searchPlaceholder"]')!;
  await act(async () => button().click());
  const search = node.querySelector<HTMLInputElement>('input[aria-label="rework.home.searchPlaceholder"]')!;
  await act(async () => {
    search.value = "missing";
    search.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => search.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  expect(node.querySelector('input[aria-label="rework.home.searchPlaceholder"]')).toBeNull();
  expect(node.querySelector('a[href="/team/fredlab"]')).not.toBeNull();
  expect(document.activeElement).toBe(button());
});

it("filters the teams by the selected organization and removes them on authority failure", async () => {
  state.otherOrganization = true;
  state.extraSpaces = [
    { id: "support", kind: "team", name: "Support", parent_id: "other", organization_id: "other", roles: ["member"] },
  ];
  await render();
  expect(node.querySelector('a[href="/team/support"]')).not.toBeNull();
  expect(node.querySelector('a[href="/team/fredlab"]')).toBeNull();
  state.selected = "org";
  await render();
  expect(node.querySelector('a[href="/team/support"]')).toBeNull();
  expect(node.querySelector('a[href="/team/fredlab"]')).not.toBeNull();
  state.fail = true;
  await render();
  expect(node.querySelector('a[href="/team/fredlab"]')).toBeNull();
  expect(node.querySelector('[role="alert"]')).not.toBeNull();
});

it("sorts teams by recent visits or alphabetically", async () => {
  state.extraSpaces = [
    { id: "alpha", kind: "team", name: "Alpha", parent_id: "org", organization_id: "org", roles: ["member"] },
  ];
  localStorage.setItem("fred.teamRecency", JSON.stringify({ fredlab: 100, alpha: 50 }));
  await render();
  const links = () => Array.from(node.querySelectorAll('a[href^="/team/"]')).map((link) => link.getAttribute("href"));
  expect(links()).toEqual(["/team/fredlab", "/team/alpha"]);
  await act(async () => setCurrentUserPreferences({ team_sort_mode: "alpha" }));
  expect(links()).toEqual(["/team/alpha", "/team/fredlab"]);
});

it("puts the marketplace right above the personal space", async () => {
  state.roles = ["owner"];
  state.personal = true;
  await render();
  const marketplace = node.querySelector('a[href="/marketplace"]')!;
  const personal = node.querySelector('a[href="/team/personal/agents"]')!;
  expect(marketplace.textContent).toContain("rework.mainNav.marketplace");
  expect(marketplace.compareDocumentPosition(personal) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

it("orders the personal space, then the organization's content, then the teams, without a divider", async () => {
  state.roles = ["member"];
  state.teamRoles = ["editor"];
  state.organizationRead = true;
  await render();
  const personal = entry()!;
  const menu = node.querySelector("[data-content-menu]")!;
  const team = node.querySelector('a[href="/team/fredlab"]')!;
  expect(personal.compareDocumentPosition(menu) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(menu.compareDocumentPosition(team) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(personal.textContent).toContain("rework.home.personalSpace");
  expect(personal.textContent).not.toContain("rework.home.personalSpaceDescription");
  expect(node.querySelector('[role="separator"], hr')).toBeNull();
  expect(node.textContent).not.toContain("rework.home.yourSpaces");
  expect(state.open).not.toHaveBeenCalled();
});
