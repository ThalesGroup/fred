// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import type { DiscoverableTeam } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const h = vi.hoisted(() => ({
  joined: vi.fn(),
  join: vi.fn(() => ({ unwrap: async () => undefined })),
  avatar: { currentData: "data:image/png;base64,photo", isError: false, isFetching: false, refetch: vi.fn() },
}));
vi.mock("../../../../../hooks/useFrontendProperties", () => ({ useFrontendProperties: () => ({}) }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) => (values ? `${key}:${Object.values(values).join("|")}` : key),
  }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApi", () => ({ sessionQueryArgs: (args: unknown) => args }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useJoinTeamMutation: () => [h.join, { isLoading: false }],
  useGetTeamAvatarQuery: () => h.avatar,
}));
import TeamCard from "./TeamCard";
let container: HTMLDivElement;
let root: Root;
const base: DiscoverableTeam = {
  id: "team",
  name: "Research",
  description: "Work on safe AI systems.",
  visibility: "visible",
  joining_mode: "open",
  is_member: false,
  can_join: true,
  member_count: 5,
  owner_count: 4,
  owners: ["Alice Martin", "Bob Durand", "Chloé Petit"],
};
beforeEach(() => {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  h.joined.mockClear();
  h.avatar.isError = false;
  h.avatar.isFetching = false;
  h.join.mockReset().mockReturnValue({ unwrap: async () => undefined });
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});
const render = async (team = base, kind?: "team" | "project") => {
  await act(async () =>
    root.render(
      <MemoryRouter>
        <TeamCard team={team} kind={kind} onJoined={h.joined} />
      </MemoryRouter>,
    ),
  );
};
it("joins only on the server offer and exposes no content link to outsiders", async () => {
  await render();
  expect(container.querySelector("a")).toBeNull();
  await act(async () => container.querySelector("button")!.click());
  expect(h.join).toHaveBeenCalledWith({ id: "team" });
  expect(h.joined).toHaveBeenCalledOnce();
  expect(container.textContent).toContain(base.description);
  expect(container.textContent).toContain("rework.teamCard.memberCount:5");
  expect(container.textContent).toContain("rework.teamCard.owners:Alice Martin, Bob Durand, Chloé Petit, +1");
  expect(container.querySelector("[tabindex]")).toBeNull();
});
it("omits the owner line when the space has no owner", async () => {
  await render({ ...base, owner_count: 0, owners: [] });
  expect(container.textContent).not.toContain("rework.teamCard.owners");
});
it("requires invitation or parent eligibility when enrollment is not offered", async () => {
  await render({ ...base, can_join: false, joining_mode: "invite_only" });
  expect(container.querySelector("button")).toBeNull();
  expect(container.textContent).toContain("rework.teamCard.inviteOnly");
  await render({ ...base, can_join: false });
  expect(container.querySelector("button")).toBeNull();
  expect(container.textContent).toContain("rework.teamDiscovery.notEligible");
});
it("makes a member's whole card one link to the neutral landing, including a hidden owner-only team", async () => {
  await render({ ...base, visibility: "hidden", is_member: true, can_join: false });
  const link = container.querySelector("a")!;
  expect(link.getAttribute("href")).toBe("/team/team");
  expect(link.parentElement).toBe(container);
  expect(link.textContent).toContain(base.name);
  expect(link.textContent).toContain(base.description);
  expect(container.querySelector("button")).toBeNull();
});
it("reports a refused join and drops an avatar after authorization failure", async () => {
  h.join.mockReturnValue({
    unwrap: async () => {
      throw new Error("closed");
    },
  });
  await render();
  await act(async () => container.querySelector("button")!.click());
  expect(container.querySelector('[role="alert"]')?.textContent).toContain("joinFailed");
  h.avatar.isError = true;
  await render();
  expect(container.querySelector("img")).toBeNull();
});
it("speaks of the parent team for a project card", async () => {
  await render({ ...base, is_member: true }, "project");
  expect(container.querySelector("a")?.getAttribute("href")).toBe("/team/team");
  await render({ ...base, can_join: false }, "project");
  expect(container.textContent).toContain("rework.projectParameters.card.notEligible");
  h.join.mockReturnValue({
    unwrap: async () => {
      throw new Error("closed");
    },
  });
  await render(base, "project");
  await act(async () => container.querySelector("button")!.click());
  expect(container.querySelector('[role="alert"]')?.textContent).toBe("rework.projectParameters.card.joinFailed");
});
