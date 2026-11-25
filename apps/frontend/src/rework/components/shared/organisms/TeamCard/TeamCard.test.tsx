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
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
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
const render = async (team = base) => {
  await act(async () =>
    root.render(
      <MemoryRouter>
        <TeamCard team={team} onJoined={h.joined} />
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
  expect(container.textContent).not.toContain("memberCount");
});
it("requires invitation or parent eligibility when enrollment is not offered", async () => {
  await render({ ...base, can_join: false, joining_mode: "invite_only" });
  expect(container.querySelector("button")).toBeNull();
  expect(container.textContent).toContain("rework.teamCard.inviteOnly");
  await render({ ...base, can_join: false });
  expect(container.querySelector("button")).toBeNull();
  expect(container.textContent).toContain("rework.teamDiscovery.notEligible");
});
it("uses the neutral landing for a member including a hidden owner-only team", async () => {
  await render({ ...base, visibility: "hidden", is_member: true, can_join: false });
  expect(container.querySelector("a")?.getAttribute("href")).toBe("/team/team");
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
