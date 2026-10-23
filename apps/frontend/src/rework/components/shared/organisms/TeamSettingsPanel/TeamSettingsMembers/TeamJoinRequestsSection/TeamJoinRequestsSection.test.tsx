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

// What these pin: the section shows only to people who can decide and only
// while requests exist; a pending row offers Refuse then Accept, a refused row
// "Accept anyway" while the team takes requests; a failure shows a toast.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { TeamJoinRequest } from "../../../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  requests: [] as TeamJoinRequest[],
  query: vi.fn(),
  accept: vi.fn(),
  refuse: vi.fn(),
  showError: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: h.showError }) }));
vi.mock("../../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useTeamJoinRequestsQuery: (arg: unknown, options: { skip: boolean }) => {
    h.query(arg, options);
    return { data: options.skip ? undefined : h.requests, refetch: vi.fn() };
  },
  useAcceptTeamJoinRequestMutation: () => [h.accept, { isLoading: false }],
  useRefuseTeamJoinRequestMutation: () => [h.refuse, { isLoading: false }],
}));

import TeamJoinRequestsSection from "./TeamJoinRequestsSection";

const pending: TeamJoinRequest = {
  id: "r1",
  team_id: "demo",
  requester_id: "alice",
  requester_name: "Alice Martin",
  message: "I work on the RFP pipeline\nand would like to reuse your agents.",
  status: "pending",
  created_at: "2026-10-22T08:00:00Z",
  expires_at: "2026-11-21T08:00:00Z",
};
const refused: TeamJoinRequest = {
  ...pending,
  id: "r2",
  requester_id: "bob",
  requester_name: "Bob Durand",
  message: null,
  status: "refused",
  decided_at: "2026-10-21T08:00:00Z",
};

let container: HTMLDivElement;
let root: Root;

const render = (canAdministerMembers = true, takesRequests = true) => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() =>
    root.render(
      <TeamJoinRequestsSection
        teamId="demo"
        canAdministerMembers={canAdministerMembers}
        takesRequests={takesRequests}
      />,
    ),
  );
};
const settled = () => ({ unwrap: () => Promise.resolve() });
const button = (label: string, row = 0) =>
  [...container.querySelectorAll("li")[row].querySelectorAll("button")].find((node) =>
    node.textContent?.includes(label),
  );

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  h.requests = [];
  h.query.mockClear();
  h.accept.mockReset();
  h.refuse.mockReset();
  h.showError.mockReset();
});

beforeEach(() => {
  h.accept.mockReturnValue(settled());
  h.refuse.mockReturnValue(settled());
});

it("renders nothing while no request is waiting", () => {
  render();
  expect(container.textContent).toBe("");
});

it("never fetches nor renders for someone who cannot administer members", () => {
  h.requests = [pending];
  render(false);
  expect(h.query).toHaveBeenCalledWith({ teamId: "demo" }, expect.objectContaining({ skip: true }));
  expect(container.textContent).toBe("");
});

it("lists a pending request with its full message and decides it", () => {
  h.requests = [pending, refused];
  render();
  expect(container.textContent).toContain("rework.teamSettings.members.joinRequests.title");
  expect(container.textContent).toContain("Alice Martin");
  expect(container.querySelector("p")?.textContent).toBe(pending.message);
  // Refuse on the left, Accept on the right, as on the notification tile.
  expect([...container.querySelectorAll("li")[0].querySelectorAll("button")].map((node) => node.textContent)).toEqual([
    "rework.teamSettings.members.joinRequests.refuse",
    "rework.teamSettings.members.joinRequests.accept",
  ]);

  act(() => button("rework.teamSettings.members.joinRequests.accept")!.click());
  expect(h.accept).toHaveBeenCalledWith({ teamId: "demo", requestId: "r1" });
  act(() => button("rework.teamSettings.members.joinRequests.refuse")!.click());
  expect(h.refuse).toHaveBeenCalledWith({ teamId: "demo", requestId: "r1" });
});

it("offers Accept anyway on a refused request", () => {
  h.requests = [pending, refused];
  render();
  expect(button("rework.teamSettings.members.joinRequests.refuse", 1)).toBeUndefined();
  expect(container.querySelectorAll("li")[1].textContent).toContain(
    "rework.teamSettings.members.joinRequests.refusedOn",
  );
  act(() => button("rework.teamSettings.members.joinRequests.acceptAnyway", 1)!.click());
  expect(h.accept).toHaveBeenCalledWith({ teamId: "demo", requestId: "r2" });
});

it("hides Accept anyway once the team no longer takes requests", () => {
  h.requests = [refused];
  render(true, false);
  expect(container.textContent).toBe("");
});

it("reports a failed decision in a toast", async () => {
  h.requests = [pending];
  h.refuse.mockReturnValue({ unwrap: () => Promise.reject({ status: 500, data: { detail: "boom" } }) });
  render();

  await act(async () => button("rework.teamSettings.members.joinRequests.refuse")!.click());

  expect(h.showError).toHaveBeenCalledWith(
    expect.objectContaining({ summary: "rework.notifications.actionFailed", detail: "boom" }),
  );
});
