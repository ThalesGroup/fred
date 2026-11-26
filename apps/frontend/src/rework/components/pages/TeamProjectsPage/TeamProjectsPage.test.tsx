// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  isError: false,
  loading: false,
  refreshing: false,
  projects: [] as Record<string, unknown>[],
  query: vi.fn(),
  refetch: vi.fn(),
  manager: false,
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-router-dom", () => ({ useParams: () => ({ teamId: "team-1" }) }));
vi.mock("../../../../slices/controlPlane/controlPlaneApi", () => ({ sessionQueryArgs: (args: unknown) => args }));
vi.mock("@core/hooks/useSpaceAccess", () => ({
  useSpaceAccess: (id: string, permission: string) => ({
    offered: h.manager && id === "team-1" && permission === "manage",
    allowed: h.manager,
  }),
}));
vi.mock("./ProjectCreationModal", () => ({
  default: ({ teamId, teamName, onClose }: { teamId: string; teamName?: string; onClose: () => void }) => (
    <div data-creation={teamId} data-team-name={teamName}>
      <button onClick={onClose}>close</button>
    </div>
  ),
}));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMySpacesQuery: () => ({ currentData: [{ id: "team-1", name: "Bid" }] }),
  useTeamProjectsQuery: (...args: unknown[]) => {
    h.query(...args);
    return {
      currentData: h.loading ? undefined : h.projects,
      isError: h.isError,
      isFetching: h.loading || h.refreshing,
      refetch: h.refetch,
    };
  },
}));
vi.mock("@shared/molecules/PageHeader/PageHeader.tsx", () => ({
  default: ({ title, actions }: { title: string; actions?: ReactNode }) => (
    <header>
      <h1>{title}</h1>
      {actions}
    </header>
  ),
}));
vi.mock("@shared/molecules/PageEmptyState/PageEmptyState.tsx", () => ({
  default: ({ message }: { message: string }) => <span data-empty>{message}</span>,
}));
vi.mock("@shared/organisms/TeamCard/TeamCard", () => ({
  default: ({ team, kind, onJoined }: { team: { name: string }; kind: string; onJoined: () => void }) => (
    <button data-kind={kind} onClick={onJoined}>
      {team.name}
    </button>
  ),
}));
import TeamProjectsPage from "./TeamProjectsPage";

const project = (id: string, name: string, extra: Record<string, unknown> = {}) => ({
  id,
  name,
  description: null,
  visibility: "visible",
  joining_mode: "open",
  is_member: false,
  can_join: true,
  ...extra,
});

let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  h.isError = false;
  h.loading = false;
  h.refreshing = false;
  h.projects = [];
  h.manager = false;
  vi.clearAllMocks();
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});
const render = async () => act(async () => root.render(<TeamProjectsPage />));

it("lists the person's projects first, then the team's others, in server order, as cards that refresh after a join", async () => {
  h.projects = [project("atlas", "Atlas"), project("beta", "Beta", { is_member: true }), project("zeta", "Zeta")];
  await render();
  expect(h.query).toHaveBeenCalledWith({ id: "team-1" }, expect.objectContaining({ skip: false }));
  const sections = Array.from(container.querySelectorAll("section")).map((section) => [
    section.querySelector("h2")?.textContent,
    Array.from(section.querySelectorAll("li button")).map((card) => [card.textContent, card.getAttribute("data-kind")]),
  ]);
  expect(sections).toEqual([
    ["rework.teamProjects.mine", [["Beta", "project"]]],
    [
      "rework.teamProjects.others",
      [
        ["Atlas", "project"],
        ["Zeta", "project"],
      ],
    ],
  ]);
  await act(async () => container.querySelector<HTMLButtonElement>("li button")!.click());
  expect(h.refetch).toHaveBeenCalledOnce();
});

it("hides an empty section", async () => {
  h.projects = [project("atlas", "Atlas", { is_member: true })];
  await render();
  expect(Array.from(container.querySelectorAll("h2")).map((title) => title.textContent)).toEqual([
    "rework.teamProjects.mine",
  ]);
  h.projects = [project("zeta", "Zeta")];
  await render();
  expect(Array.from(container.querySelectorAll("h2")).map((title) => title.textContent)).toEqual([
    "rework.teamProjects.others",
  ]);
});

it("shows an empty state without projects", async () => {
  await render();
  expect(container.querySelector("[data-empty]")?.textContent).toBe("rework.teamProjects.empty");
});

it("reports loading and failure without stale cards", async () => {
  h.loading = true;
  await render();
  expect(container.querySelector('[role="status"]')?.textContent).toBe("common.loading");
  h.loading = false;
  h.isError = true;
  h.projects = [project("atlas", "Atlas")];
  await render();
  expect(container.querySelector('[role="alert"]')?.textContent).toBe("rework.manager.unavailable");
  expect(container.querySelector("li")).toBeNull();
});

it("keeps the cards in place while a join refreshes the list", async () => {
  h.projects = [project("atlas", "Atlas")];
  h.refreshing = true;
  await render();
  expect(container.querySelectorAll("li")).toHaveLength(1);
  expect(container.querySelector('[role="status"]')).toBeNull();
});

it("offers project creation to the team's direct Owner only, in a surface that closes back to the list", async () => {
  await render();
  expect(container.querySelector("header button")).toBeNull();
  h.manager = true;
  await render();
  const create = container.querySelector<HTMLButtonElement>("header button")!;
  expect(create.textContent).toContain("rework.create");
  expect(container.querySelector("[data-creation]")).toBeNull();
  await act(async () => create.click());
  const surface = container.querySelector("[data-creation]")!;
  expect(surface.getAttribute("data-creation")).toBe("team-1");
  expect(surface.getAttribute("data-team-name")).toBe("Bid");
  await act(async () => surface.querySelector("button")!.click());
  expect(container.querySelector("[data-creation]")).toBeNull();
});
