// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { DiscoverableTeam } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const h = vi.hoisted(() => ({
  organizationId: "org-a",
  query: vi.fn(),
  membershipRefetch: vi.fn(),
  result: {
    currentData: { items: [] as DiscoverableTeam[], total: 0 },
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
  },
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@core/hooks/useWorkingOrganization", () => ({
  useWorkingOrganization: () => ({
    organizationId: h.organizationId,
    loading: false,
    memberships: { refetch: h.membershipRefetch },
  }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApi", () => ({ sessionQueryArgs: (args: unknown) => args }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useOrganizationTeamsQuery: (args: unknown) => {
    h.query(args);
    return h.result;
  },
}));
vi.mock("@shared/organisms/TeamCard/TeamCard", () => ({
  default: ({ team, onJoined }: { team: DiscoverableTeam; onJoined: () => void }) => (
    <div data-card>
      {team.name}
      <button onClick={onJoined}>joined</button>
    </div>
  ),
}));
import MarketplaceTeams from "./MarketplaceTeams";
let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  h.organizationId = "org-a";
  h.result.isError = false;
  h.result.isFetching = false;
  h.result.currentData = {
    items: [
      {
        id: "team",
        name: "Research",
        visibility: "visible",
        joining_mode: "invite_only",
        is_member: false,
        can_join: false,
      },
    ],
    total: 21,
  };
  h.query.mockClear();
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});
const render = async () => {
  await act(async () => root.render(<MarketplaceTeams />));
};
it("queries only the working organization and resets pagination on search or organization changes", async () => {
  await render();
  expect(h.query).toHaveBeenLastCalledWith({ organizationId: "org-a", search: "", page: 0 });
  const next = container.querySelector<HTMLButtonElement>('[aria-label="dataTable.pagination.next"]')!;
  await act(async () => next.click());
  expect(h.query).toHaveBeenLastCalledWith({ organizationId: "org-a", search: "", page: 1 });
  const input = container.querySelector("input")!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "wind");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  expect(h.query).toHaveBeenLastCalledWith({ organizationId: "org-a", search: "wind", page: 0 });
  h.organizationId = "org-b";
  await render();
  expect(h.query).toHaveBeenLastCalledWith({ organizationId: "org-b", search: "", page: 0 });
});
it("hides cached metadata during refresh and on failed authority", async () => {
  await render();
  expect(container.querySelector("[data-card]")).not.toBeNull();
  h.result.isFetching = true;
  await render();
  expect(container.querySelector("[data-card]")).toBeNull();
  h.result.isFetching = false;
  h.result.isError = true;
  await render();
  expect(container.querySelector("[data-card]")).toBeNull();
  expect(container.querySelector('[role="alert"]')).not.toBeNull();
});
it("refreshes on reconnect without a legacy team query", async () => {
  await render();
  await act(async () => window.dispatchEvent(new Event("online")));
  expect(h.result.refetch).toHaveBeenCalled();
});

it("refreshes memberships and cards immediately after enrollment", async () => {
  await render();
  await act(async () => container.querySelector<HTMLButtonElement>("[data-card] button")!.click());
  expect(h.membershipRefetch).toHaveBeenCalled();
  expect(h.result.refetch).toHaveBeenCalled();
});
