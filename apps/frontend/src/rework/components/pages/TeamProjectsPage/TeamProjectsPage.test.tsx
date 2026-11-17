// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  navigate: vi.fn(),
  isError: false,
  loading: false,
  memberships: [] as Record<string, unknown>[],
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-router-dom", () => ({
  useNavigate: () => h.navigate,
  useParams: () => ({ teamId: "team-1" }),
}));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMySpacesQuery: () => ({ currentData: h.loading ? undefined : h.memberships, isError: h.isError }),
}));
vi.mock("@shared/molecules/PageHeader/PageHeader.tsx", () => ({
  default: ({ title }: { title: string }) => <h1>{title}</h1>,
}));
vi.mock("@shared/molecules/PageEmptyState/PageEmptyState.tsx", () => ({
  default: ({ message }: { message: string }) => <span data-empty>{message}</span>,
}));
import TeamProjectsPage from "./TeamProjectsPage";

const team = {
  id: "team-1",
  kind: "team",
  name: "Research",
  organization_id: "org",
  parent_id: "org",
  roles: ["member"],
};
const project = (id: string, name: string, extra: Record<string, unknown> = {}) => ({
  id,
  kind: "project",
  name,
  organization_id: "org",
  parent_id: "team-1",
  roles: ["editor"],
  description: null,
  ...extra,
});

let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  h.isError = false;
  h.loading = false;
  h.memberships = [];
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

it("lists the team's member projects as cards, by name, and enters a project on selection", async () => {
  h.memberships = [
    team,
    project("zeta", "Zeta"),
    project("atlas", "Atlas", { description: "Mapping" }),
    project("elsewhere", "Elsewhere", { parent_id: "team-2" }),
  ];
  await render();
  const cards = Array.from(container.querySelectorAll("li button"));
  expect(cards.map((card) => card.textContent)).toEqual([
    "assignmentAtlasMapping",
    "assignmentZetarework.teamRoles.team_editor",
  ]);
  await act(async () => (cards[0] as HTMLButtonElement).click());
  expect(h.navigate).toHaveBeenCalledWith("/team/atlas");
});

it("shows an empty state without projects", async () => {
  h.memberships = [team];
  await render();
  expect(container.querySelector("[data-empty]")?.textContent).toBe("rework.teamProjects.empty");
});

it("reports loading and failure without stale cards", async () => {
  h.loading = true;
  await render();
  expect(container.querySelector('[role="status"]')?.textContent).toBe("common.loading");
  h.loading = false;
  h.isError = true;
  h.memberships = [team, project("atlas", "Atlas")];
  await render();
  expect(container.querySelector('[role="alert"]')?.textContent).toBe("rework.manager.unavailable");
  expect(container.querySelector("li")).toBeNull();
});
