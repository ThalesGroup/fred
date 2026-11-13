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

import { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  working: { organizationId: "org" as string | undefined, loading: false, error: undefined as unknown },
  membershipError: false,
  canManage: false,
  canRead: true,
  memberships: [] as {
    id: string;
    kind: string;
    name: string;
    roles: string[];
    parent_id?: string;
    organization_id?: string;
  }[],
  isPersonalTeam: false,
  pathname: "/team/team-1/resources",
  relations: ["team_member"] as string[],
  charterEnabled: undefined as boolean | undefined,
  applicationsEnabled: false,
  result: { data: undefined, isError: false } as {
    data?: { items: Array<Record<string, unknown>> };
    isError: boolean;
  },
  refetchKnowledgeBases: vi.fn(),
  knowledgeBasesQuery: vi.fn(),
  selectedTeam: vi.fn(),
  avatarQuery: vi.fn(),
  wiki: vi.fn(),
  applications: vi.fn(),
  flags: vi.fn(),
  canUseKnowledgeBases: true,
  knowledgeBases: { currentData: undefined, isError: false } as {
    currentData?: { definition_id: string; name: string; description: string }[];
    isError: boolean;
  },
  wikiEnabled: undefined as boolean | undefined,
  wikiError: false,
  defaultTeamAvatarFile: "",
  teamAvatarImageUrl: undefined as string | undefined,
  userPictureUrl: undefined as string | undefined,
}));

vi.mock("@core/hooks/useWorkingOrganization", () => ({ useWorkingOrganization: () => h.working }));

vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMarketplaceProposalSpacesQuery: () => ({ currentData: { items: [], next_cursor: null }, isError: false }),
  useGetMyAvatarQuery: (_arg: undefined, { skip }: { skip: boolean }) => {
    h.avatarQuery(skip);
    return { currentData: skip ? undefined : h.userPictureUrl };
  },
  useMySpacesQuery: () => ({ currentData: h.memberships, isError: h.membershipError }),
  useWikiAvailabilityQuery: (
    args: { spaceId: string },
    options: { skip: boolean; refetchOnMountOrArgChange: boolean },
  ) => {
    h.wiki(args, options);
    return {
      currentData: options.skip || h.wikiEnabled === undefined ? undefined : { enabled: h.wikiEnabled },
      isError: !options.skip && h.wikiError,
    };
  },
}));

vi.mock("@core/hooks/useSpaceAccess", () => ({
  useSpaceAccess: (_id: string, permission: string) => ({ allowed: permission === "manage" ? h.canManage : h.canRead }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("react-router-dom", () => ({
  Link: ({ to, children }) => <a href={to}>{children}</a>,
  useLocation: () => ({ pathname: h.pathname }),
  useNavigate: () => vi.fn(),
  NavLink: ({ to, children }: { to: string; children: ReactNode | ((args: { isActive: boolean }) => ReactNode) }) => (
    <a href={to}>{typeof children === "function" ? children({ isActive: false }) : children}</a>
  ),
}));
vi.mock("../../../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({
    agentIconName: "smart_toy",
    agentsNicknamePlural: "agents",
    defaultTeamAvatarFile: h.defaultTeamAvatarFile,
  }),
}));
vi.mock("../../../../../../hooks/useSelectedTeam.ts", () => ({
  useSelectedTeam: (skip: boolean) => (
    h.selectedTeam(skip),
    {
      teamId: "team-1",
      isPersonalTeam: h.isPersonalTeam,
      selectedTeam: {
        id: "team-1",
        name: "Team One",
        is_member: true,
        my_relations: h.relations,
        avatar_image_url: h.teamAvatarImageUrl,
      },
      canOpenTeamSettings: false,
    }
  ),
}));
vi.mock("@hooks/useTeamCapabilities.ts", () => ({
  useTeamCapabilities: () => ({
    canUpdateAgents: true,
    canUpdateInfo: false,
    canUseTeamKnowledgeBases: h.canUseKnowledgeBases,
  }),
}));
vi.mock("@hooks/useFrontendFeatureFlag.ts", () => ({
  useFrontendFeatureFlag: (name: string, skip: boolean) => (
    h.flags(name, skip), { enabled: h.applicationsEnabled, isLoading: false }
  ),
}));
vi.mock("@hooks/teamCapabilities.ts", () => ({ hasElevatedTeamRole: () => false }));
vi.mock("@rework/features/applications/useTeamApplications.ts", () => ({
  useTeamApplications: (teamId: string, skip: boolean) => {
    h.applications(teamId, skip);
    return h.result;
  },
}));
vi.mock("../../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements", () => ({
  useKnowledgeBaseDefinitionsQuery: (args: unknown, options: unknown) => {
    h.knowledgeBasesQuery(args, options);
    return { ...h.knowledgeBases, refetch: h.refetchKnowledgeBases };
  },
}));
vi.mock("@shared/organisms/ChatList/ChatList.tsx", () => ({ default: () => <div data-chat-list /> }));

import TeamContentNavbar from "./TeamContentNavbar.tsx";

beforeEach(() => {
  h.working = { organizationId: "org", loading: false, error: undefined };
  h.membershipError = false;
  h.relations = ["team_member"];
  h.canManage = false;
  h.pathname = "/team/team-1/resources";
  h.memberships = [];
  h.canRead = true;
  h.isPersonalTeam = false;
  h.wikiEnabled = undefined;
  h.wikiError = false;
  h.wiki.mockClear();
});

const application = {
  id: "example",
  version: "1.0.0",
  name: { en: "Example" },
  description: { en: "An example application" },
  icon: "extension",
  ui_prefix: "/apps/example",
};

describe("TeamContentNavbar applications entry", () => {
  beforeEach(() => {
    h.isPersonalTeam = false;
    h.applicationsEnabled = false;
    h.result = { data: undefined, isError: false };
  });

  it("adds exactly one generic Apps entry when an authorized app is available", () => {
    h.applicationsEnabled = true;
    h.result.data = { items: [application] };
    const html = renderToStaticMarkup(<TeamContentNavbar />);
    expect(html.match(/href="\/team\/team-1\/apps"/g)).toHaveLength(1);
    expect(html).toContain("rework.sidebar.team.menu.apps");
    expect(html).not.toContain(application.id);
  });

  it("hides Apps when the catalog is unavailable, empty, or failed", () => {
    h.applicationsEnabled = true;
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/apps"');

    h.result = { data: { items: [] }, isError: false };
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/apps"');

    h.result = { data: { items: [application] }, isError: true };
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/apps"');
  });

  // Fred no longer compiles application code, so an app version Fred has never
  // heard of is ordinary — it must not suppress the entry the way a build-time
  // registry miss once did.
  it("shows Apps for an application version this Fred build predates", () => {
    h.applicationsEnabled = true;
    h.result = { data: { items: [{ ...application, version: "2.0.0" }] }, isError: false };
    expect(renderToStaticMarkup(<TeamContentNavbar />)).toContain('href="/team/team-1/apps"');
  });

  it("never shows Apps for a personal space", () => {
    h.applicationsEnabled = true;
    h.isPersonalTeam = true;
    h.result = { data: { items: [application] }, isError: false };
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/apps"');
  });

  it("hides Apps behind the default-off deployment switch despite a compatible cached catalog", () => {
    h.result.data = { items: [application] };
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/apps"');
  });
});

// WIKI-03: the wiki exists for a team only where an admin enabled the
// `team_wiki` capability. The entry has to follow that, or a member clicks
// into a page the control-plane refuses.
describe("TeamContentNavbar — the wiki entry", () => {
  beforeEach(() => {
    h.isPersonalTeam = false;
    h.applicationsEnabled = false;
    h.result = { data: undefined, isError: false };
    h.wikiEnabled = undefined;
    h.pathname = "/team/team-1/agents";
    h.memberships = [{ id: "team-1", kind: "team", name: "Team One", roles: ["member"] }];
  });

  it.each(["agents", "resources", "prompts", "wiki", "managed-chat/session-1"])(
    "offers the enabled wiki to a reader on %s",
    (route) => {
      h.pathname = `/team/team-1/${route}`;
      h.wikiEnabled = true;
      expect(renderToStaticMarkup(<TeamContentNavbar />)).toContain('href="/team/team-1/wiki"');
      expect(h.wiki).toHaveBeenLastCalledWith({ spaceId: "team-1" }, { skip: false, refetchOnMountOrArgChange: true });
    },
  );

  it("skips availability and hides the wiki without content read access", () => {
    h.canRead = false;
    h.canManage = true;
    try {
      h.wikiEnabled = true;
      expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/wiki"');
      expect(h.wiki).toHaveBeenLastCalledWith({ spaceId: "team-1" }, { skip: true, refetchOnMountOrArgChange: true });
    } finally {
      h.canManage = false;
    }
  });

  it("keeps the wiki available for an authorized personal space", () => {
    h.memberships = [{ id: "team-1", kind: "personal", name: "Personal", roles: [] }];
    h.wikiEnabled = true;
    expect(renderToStaticMarkup(<TeamContentNavbar />)).toContain('href="/team/team-1/wiki"');
    expect(h.wiki).toHaveBeenLastCalledWith({ spaceId: "team-1" }, { skip: false, refetchOnMountOrArgChange: true });
  });

  it.each([undefined, "organization", "project"])("skips availability for unsupported space kind %s", (kind) => {
    h.memberships = kind ? [{ id: "team-1", kind, name: "Unsupported", roles: ["member"] }] : [];
    h.wikiEnabled = true;
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/wiki"');
    expect(h.wiki).toHaveBeenLastCalledWith(
      { spaceId: kind ? "team-1" : "" },
      { skip: true, refetchOnMountOrArgChange: true },
    );
  });

  it("hides the wiki when availability fails despite a previous enabled response", () => {
    h.wikiEnabled = true;
    h.wikiError = true;
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/wiki"');
  });

  it("hides it when the capability is off", () => {
    h.wikiEnabled = false;
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain("/team/team-1/wiki");
  });

  it("hides it while the answer is still unknown", () => {
    // Showing it optimistically means an entry that appears and then vanishes
    // on a slow answer — worse than one that arrives a moment late.
    h.wikiEnabled = undefined;
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain("/team/team-1/wiki");
  });
});

describe("TeamContentNavbar — the team avatar", () => {
  beforeEach(() => {
    h.isPersonalTeam = false;
    h.defaultTeamAvatarFile = "";
    h.teamAvatarImageUrl = undefined;
    h.userPictureUrl = undefined;
  });

  it("falls back to the deployment default when the team has no image of its own", () => {
    h.defaultTeamAvatarFile = "acme-team-avatar.svg";
    const html = renderToStaticMarkup(<TeamContentNavbar />);
    expect(html).toContain('src="/images/acme-team-avatar.svg"');
  });

  it("keeps the team's own image ahead of the deployment default", () => {
    h.defaultTeamAvatarFile = "acme-team-avatar.svg";
    h.teamAvatarImageUrl = "https://store.example/team-1.png";
    const html = renderToStaticMarkup(<TeamContentNavbar />);
    expect(html).toContain('src="https://store.example/team-1.png"');
    expect(html).not.toContain("acme-team-avatar.svg");
  });

  it("renders initials when no default is configured", () => {
    const html = renderToStaticMarkup(<TeamContentNavbar />);
    expect(html).not.toContain("/images/");
    expect(html).toContain("TO");
  });

  // The personal space says "this is you" with the user's own avatar; a team
  // default there would erase that signal.
  it("leaves the personal space on the user avatar", () => {
    h.isPersonalTeam = true;
    h.defaultTeamAvatarFile = "acme-team-avatar.svg";
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain("acme-team-avatar.svg");
  });

  it("shows the user's profile picture in the personal space", () => {
    h.isPersonalTeam = true;
    h.userPictureUrl = "https://store.example/me.webp";
    expect(renderToStaticMarkup(<TeamContentNavbar />)).toContain('src="https://store.example/me.webp"');
  });
});

describe("TeamContentNavbar — knowledge bases and beta badges", () => {
  beforeEach(() => {
    h.canUseKnowledgeBases = true;
    h.knowledgeBases = { currentData: undefined, isError: false };
    h.wikiEnabled = true;
  });

  it("shows enabled definitions even before any instance is created, with beta only on the wiki", () => {
    h.memberships = [{ id: "team-1", kind: "team", name: "Team One", roles: ["member"] }];
    h.knowledgeBases.currentData = [{ definition_id: "source", name: "Source", description: "" }];
    const html = renderToStaticMarkup(<TeamContentNavbar />);
    const entry = (route: string) => html.split(`href="/team/team-1/${route}"`)[1]?.split("</a>")[0];
    const knowledgeBases = entry("knowledge-bases");
    expect(knowledgeBases).toContain("rework.sidebar.team.menu.knowledgeBases");
    expect(knowledgeBases).not.toContain("aria-label=");
    const wiki = entry("wiki");
    expect(wiki).toBeDefined();
    expect(wiki!.indexOf("aria-label=")).toBeGreaterThan(wiki!.indexOf("rework.sidebar.team.menu.wiki"));
  });

  it.each([
    { currentData: undefined, isError: false },
    { currentData: undefined, isError: true },
    { currentData: [], isError: false },
  ])("keeps the porting entry when the old catalog is unavailable: %j", (result) => {
    h.knowledgeBases = result;
    expect(renderToStaticMarkup(<TeamContentNavbar />)).toContain("/team/team-1/knowledge-bases");
  });

  it("keeps the last known definitions when a refresh fails", () => {
    h.knowledgeBases = {
      currentData: [{ definition_id: "source", name: "Source", description: "" }],
      isError: true,
    };
    expect(renderToStaticMarkup(<TeamContentNavbar />)).toContain("/team/team-1/knowledge-bases");
  });

  it("requires team permission even with cached enabled definitions", () => {
    h.canUseKnowledgeBases = false;
    h.knowledgeBases.currentData = [{ definition_id: "source", name: "Source", description: "" }];
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain("/team/team-1/knowledge-bases");
  });
});

describe("TeamContentNavbar — pending knowledge base entry", () => {
  it("does not poll the removed Swift catalog", () => {
    h.knowledgeBasesQuery.mockClear();
    h.refetchKnowledgeBases.mockClear();
    h.canUseKnowledgeBases = true;
    const html = renderToStaticMarkup(<TeamContentNavbar />);
    expect(html).not.toContain("/weaver/features");
    expect(h.knowledgeBasesQuery).not.toHaveBeenCalled();
    expect(h.refetchKnowledgeBases).not.toHaveBeenCalled();
  });
});

it("skips legacy sidebar reads and shows the Weaver chat list on agent management", () => {
  h.pathname = "/team/team-1/agents";
  h.memberships = [{ id: "team-1", kind: "team", name: "Team One", roles: ["member"] }];
  const html = renderToStaticMarkup(<TeamContentNavbar />);
  expect(h.selectedTeam).toHaveBeenLastCalledWith(true);
  expect(h.avatarQuery).toHaveBeenLastCalledWith(true);
  expect(h.flags).toHaveBeenLastCalledWith("enableApplications", true);
  expect(h.applications).toHaveBeenLastCalledWith("team-1", true);
  expect(h.wiki).toHaveBeenLastCalledWith({ spaceId: "team-1" }, { skip: false, refetchOnMountOrArgChange: true });
  expect(h.knowledgeBasesQuery).not.toHaveBeenCalled();
  expect(html).toContain("data-chat-list");
  expect(html).not.toContain("rework.weaverAgents.chatUnavailable");
});

// The owner-only Nova exercise must render the same role as the Home team list.
it.each([["owner"], ["editor", "owner"]])("shows Weaver roles without falling back to member: %j", (...roles) => {
  h.pathname = "/team/team-1/agents";
  h.memberships = [{ id: "team-1", kind: "team", name: "Pilote", roles }];
  try {
    const html = renderToStaticMarkup(<TeamContentNavbar />);
    expect(html).toContain("rework.teamRoles.team_owner");
    expect(html).not.toContain("rework.teamRoles.team_member");
    if (roles.includes("editor")) {
      expect(html).toContain("rework.teamRoles.team_owner · rework.teamRoles.team_editor");
    }
  } finally {
    h.memberships = [];
  }
});

it("gives an owner the Weaver settings entry without reading content or conversations", () => {
  h.canManage = true;
  h.canRead = false;
  h.pathname = "/team/team-1/agents";
  h.memberships = [{ id: "team-1", kind: "team", name: "Pilote", roles: ["owner"] }];
  try {
    const html = renderToStaticMarkup(<TeamContentNavbar />);
    expect(html).toContain("rework.teamSettings.navigation.settings");
    expect(html).toContain("rework.teamRoles.team_owner");
    expect(html).not.toContain("data-chat-list");
    expect(html).not.toContain('href="/team/team-1/agents"');
    h.pathname = "/team/team-1/settings/members";
    const settings = renderToStaticMarkup(<TeamContentNavbar />);
    expect(settings).toContain('href="/team/team-1/settings/members"');
    expect(h.selectedTeam).toHaveBeenLastCalledWith(true);
    expect(h.avatarQuery).toHaveBeenLastCalledWith(true);
  } finally {
    h.memberships = [];
    h.canManage = false;
    h.canRead = true;
  }
});

it.each(["organization", "team", "project"])("offers the same prompts entry for a %s reader", (kind) => {
  h.pathname = "/team/team-1/prompts";
  h.memberships = [{ id: "team-1", kind, name: "Space", roles: ["member"] }];
  h.canRead = true;
  const html = renderToStaticMarkup(<TeamContentNavbar />);
  expect(html).toContain('href="/team/team-1/prompts"');
  if (kind === "organization") {
    expect(html).not.toContain('href="/team/team-1/agents"');
    expect(html).not.toContain("data-chat-list");
  }
  h.canRead = false;
  expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/prompts"');
});

it("shows the project kind and its organization/team breadcrumb from current memberships", () => {
  h.memberships = [
    { id: "org", kind: "organization", name: "Acme", roles: ["member"] },
    { id: "research", kind: "team", name: "Research", organization_id: "org", roles: ["member"] },
    { id: "team-1", kind: "project", name: "Atlas", organization_id: "org", parent_id: "research", roles: ["member"] },
  ];
  const container = document.createElement("div");
  container.innerHTML = renderToStaticMarkup(<TeamContentNavbar />);
  const breadcrumb = container.querySelector('nav[aria-label="rework.home.spaceLocation"]')!;
  expect(Array.from(breadcrumb.querySelectorAll("button")).map((button) => button.textContent)).toEqual([
    "Acme",
    "Research",
  ]);
  expect(breadcrumb.querySelector('[aria-current="page"]')?.textContent).toBe("Atlas");
  expect(container.textContent).toContain("rework.userSettings.spaceKinds.project");
  h.memberships = h.memberships.filter((space) => space.id !== "research");
  expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain("Research");
});

it("offers only member projects of the current team", () => {
  h.memberships = [
    { id: "team-1", kind: "team", name: "Research", organization_id: "org", roles: ["member"] },
    { id: "atlas", kind: "project", name: "Atlas", organization_id: "org", parent_id: "team-1", roles: ["member"] },
    {
      id: "other",
      kind: "project",
      name: "Other project",
      organization_id: "org",
      parent_id: "another-team",
      roles: ["member"],
    },
  ];
  const html = renderToStaticMarkup(<TeamContentNavbar />);
  expect(html).toContain('href="/team/atlas"');
  expect(html).not.toContain('href="/team/other"');
});

describe("TeamContentNavbar collective usage", () => {
  beforeEach(() => {
    h.pathname = "/team/team-1/agents";
    h.canRead = false;
    h.canManage = false;
    h.memberships = [{ id: "team-1", kind: "team", name: "Research", organization_id: "org", roles: ["analyst"] }];
  });

  it.each([
    { kind: "team", role: "owner" },
    { kind: "team", role: "analyst" },
    { kind: "project", role: "owner" },
    { kind: "project", role: "analyst" },
  ])("links $kind usage for a direct $role independently of content or management", ({ kind, role }) => {
    h.memberships[0] = { ...h.memberships[0], kind, roles: [role] };
    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(<TeamContentNavbar />);
    const links = container.querySelectorAll('a[href="/team/team-1/usage"]');
    expect(links).toHaveLength(1);
    expect(links[0].textContent).toContain("rework.teamSettings.navigation.usage");
    expect(container.querySelector('a[href="/team/team-1/agents"]')).toBeNull();
    expect(h.selectedTeam).toHaveBeenLastCalledWith(true);
  });

  it.each(["member", "editor", "organization_admin"])("does not infer usage from %s or legacy roles", (role) => {
    h.memberships[0].roles = [role];
    h.canRead = h.canManage = true;
    h.relations = ["team_admin", "team_analyst"];
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/usage"');
  });

  it.each(["owner", "organization_admin"])("does not inherit the parent %s role", (role) => {
    h.memberships[0].roles = ["member"];
    h.memberships.push({ id: "org", kind: "organization", name: "Acme", organization_id: "org", roles: [role] });
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/usage"');
  });

  it.each(["loading", "error", "missing", "other-organization", "membership-error", "revoked"])(
    "hides the entry for %s context despite previously available roles",
    (state) => {
      expect(renderToStaticMarkup(<TeamContentNavbar />)).toContain('href="/team/team-1/usage"');
      if (state === "loading") h.working.loading = true;
      if (state === "error") h.working.error = new Error("unavailable");
      if (state === "missing") h.working.organizationId = undefined;
      if (state === "other-organization") h.working.organizationId = "other";
      if (state === "membership-error") h.membershipError = true;
      if (state === "revoked") h.memberships[0].roles = ["member"];
      expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/usage"');
    },
  );

  it.each(["usage", "settings/members"])("keeps Analyst out of management links on %s", (route) => {
    h.pathname = `/team/team-1/${route}`;
    const html = renderToStaticMarkup(<TeamContentNavbar />);
    expect(html).toContain('href="/team/team-1/usage"');
    expect(html).not.toContain('href="/team/team-1/settings/members"');
    expect(html).not.toContain('href="/team/team-1/settings/offers"');
  });

  it("keeps management and usage navigation together for an authorized Owner", () => {
    h.memberships[0].roles = ["owner"];
    h.canManage = true;
    h.pathname = "/team/team-1/settings/members";
    const html = renderToStaticMarkup(<TeamContentNavbar />);
    expect(html).toContain('href="/team/team-1/usage"');
    expect(html).toContain('href="/team/team-1/settings/members"');
    expect(html).toContain('href="/team/team-1/settings/offers"');
  });

  it("preserves the personal shortcut without a collective link and excludes organizations", () => {
    h.memberships[0].kind = "personal";
    h.memberships[0].roles = ["owner"];
    const personal = renderToStaticMarkup(<TeamContentNavbar />);
    expect(personal).toContain('title="rework.teamUsage.title"');
    expect(personal).not.toContain('href="/team/team-1/usage"');
    h.memberships[0].kind = "organization";
    expect(renderToStaticMarkup(<TeamContentNavbar />)).not.toContain('href="/team/team-1/usage"');
  });
});
