// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act, Component, useState, type PropsWithChildren } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { Team } from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";

const h = vi.hoisted(() => ({
  bootstrap: { data: undefined as { available_teams: Team[] } | undefined, isLoading: false },
  refetch: vi.fn(),
  agents: vi.fn(() => ({ unwrap: () => Promise.reject(new Error("unavailable")) })),
  prompts: vi.fn(() => ({ unwrap: () => Promise.reject(new Error("unavailable")) })),
}));
vi.mock("../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi", () => ({
  useGetFrontendBootstrapControlPlaneV1FrontendBootstrapGetQuery: () => ({
    ...h.bootstrap,
    isFetching: h.bootstrap.isLoading,
    refetch: h.refetch,
  }),
  useGetMarketplacePromptsControlPlaneV1MarketplacePromptsGetQuery: () => ({ data: undefined }),
  useLazyGetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetQuery: () => [h.prompts],
}));
vi.mock("../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements", () => ({
  useLazyTeamAgentInstancesQuery: () => [h.agents],
}));
// Keep both the real search hook and the real bootstrap adapter: mocking the
// latter with a stable array would hide the unavailable-bootstrap render loop.
import { useHomeSearchIndex } from "./useHomeSearchIndex";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement;
let root: Root;
let renders: number;
const caught = vi.fn();

class RenderBoundary extends Component<PropsWithChildren, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? <p>render loop</p> : this.props.children;
  }
}

function Probe() {
  const sources = useHomeSearchIndex(true); // Home's automatic focus activates it.
  const [clicks, setClicks] = useState(0);
  // Stop the known regression deterministically instead of hanging the runner.
  if (++renders > 20) throw new Error("Home search did not settle");
  return (
    <>
      <p>{sources.teams.map((team) => team.name).join(",")}</p>
      <button onClick={() => setClicks((value) => value + 1)}>clicks {clicks}</button>
    </>
  );
}

async function render() {
  await act(async () =>
    root.render(
      <RenderBoundary>
        <Probe />
      </RenderBoundary>,
    ),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  h.bootstrap = { data: undefined, isLoading: false };
  renders = 0;
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host, { onCaughtError: caught });
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

it.each([true, false])("settles and remains interactive without bootstrap data (loading=%s)", async (loading) => {
  h.bootstrap.isLoading = loading;
  await render();
  expect(caught).not.toHaveBeenCalled();
  expect(renders).toBeLessThan(10);
  expect(h.agents).not.toHaveBeenCalled();
  expect(h.prompts).not.toHaveBeenCalled();
  await act(async () => host.querySelector("button")!.click());
  expect(host.textContent).toContain("clicks 1");
  expect(caught).not.toHaveBeenCalled();
});

it("refreshes teams on recovery and tolerates unavailable agent/prompt APIs without a fetch loop", async () => {
  await render();
  expect(caught).not.toHaveBeenCalled();
  h.bootstrap.data = { available_teams: [{ id: "team-1", name: "Team One", is_member: true }] };
  await render();
  expect(host.textContent).toContain("Team One");
  expect(h.agents).toHaveBeenCalledExactlyOnceWith({ teamId: "team-1" }, true);
  expect(h.prompts).toHaveBeenCalledExactlyOnceWith({ teamId: "team-1" }, true);
  await act(async () => host.querySelector("button")!.click());
  expect(host.textContent).toContain("clicks 1");
  expect(h.agents).toHaveBeenCalledTimes(1);
  expect(h.prompts).toHaveBeenCalledTimes(1);
  expect(caught).not.toHaveBeenCalled();
});
