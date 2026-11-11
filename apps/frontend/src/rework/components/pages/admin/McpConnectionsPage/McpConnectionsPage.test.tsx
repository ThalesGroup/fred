// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { McpConnectionView } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
const h = vi.hoisted(() => ({
  admin: true,
  error: false,
  rows: [] as McpConnectionView[],
  query: vi.fn(),
  publish: vi.fn(),
  test: vi.fn(),
  update: vi.fn(),
  t: vi.fn((key: string) => key),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: h.t, i18n: { language: "en" } }) }));
vi.mock("@core/hooks/useManagerPlatformAdmin", () => ({
  useManagerPlatformAdmin: () => ({ isAdmin: h.admin, isLoading: false, isError: false }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMcpConnectionsQuery: (...args: unknown[]) => {
    h.query(...args);
    return { currentData: h.rows, isError: h.error };
  },
  useMcpCredentialsQuery: () => ({ currentData: [] }),
  useCreateMcpConnectionMutation: () => [vi.fn(), {}],
  useUpdateMcpConnectionMutation: () => [(args: unknown) => ({ unwrap: async () => h.update(args) }), {}],
  useTestMcpConnectionMutation: () => [(args: unknown) => ({ unwrap: async () => h.test(args) }), {}],
  usePublishMcpConnectionMutation: () => [(args: unknown) => ({ unwrap: async () => h.publish(args) }), {}],
}));
import McpConnectionsPage from "./McpConnectionsPage";
let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  vi.clearAllMocks();
  h.admin = true;
  h.error = false;
  h.rows = [
    {
      id: "one",
      logical_name: "tools",
      display_name: "Shared tools",
      description: "Provider",
      revision: 7,
      configuration: { url: "https://tools.invalid/mcp", authentication: { kind: "none" } },
      enabled: true,
      available: true,
      observation_state: "available",
      observation_revision: 7,
      checked_at: "2026-11-11T10:00:00Z",
      last_success_at: "2026-11-11T10:00:00Z",
      error_code: null,
      observed_tools: [{ name: "search", input_schema: { type: "object" } }],
      published_tools: [],
      published_revision: null,
      affected_instance_count: 2,
    },
  ];
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});
const render = () => act(() => root.render(<McpConnectionsPage />));
const select = () =>
  act(() =>
    [...container.querySelectorAll<HTMLElement>("[data-activatable]")]
      .find((cell) => cell.textContent?.includes("Shared tools"))!
      .click(),
  );
const button = (key: string) =>
  [...container.querySelectorAll("button")].find((item) => item.textContent === `rework.mcp.${key}`)!;
it("denies business admins and hides cached technical inventory after access loss", () => {
  h.admin = false;
  render();
  expect(h.query).toHaveBeenLastCalledWith(undefined, expect.objectContaining({ skip: true }));
  expect(container.textContent).not.toContain("Shared tools");
  expect(container.textContent).toContain("rework.spaceMembers.forbidden");
});
it("does not show stale data after a failed authorization refresh", () => {
  h.error = true;
  render();
  expect(container.textContent).not.toContain("Shared tools");
});
it("publishes exactly the reviewed revision and observation", async () => {
  render();
  select();
  await act(async () => button("publish").click());
  expect(h.publish).toHaveBeenCalledWith({
    id: "one",
    mcpPublication: { expected_revision: 7, expected_checked_at: h.rows[0].checked_at },
  });
  expect(h.update).not.toHaveBeenCalled();
});
it("cannot publish an observation from an older configuration", () => {
  h.rows[0].observation_revision = 6;
  render();
  select();
  expect(button("publish").disabled).toBe(true);
});
it("technical withdrawal preserves the identity and carries optimistic concurrency", async () => {
  render();
  select();
  await act(async () => button("disable").click());
  expect(h.update).toHaveBeenCalledWith({
    id: "one",
    updateMcpConnection: expect.objectContaining({ expected_revision: 7, enabled: false }),
  });
});

it("shows aggregate impact and can withdraw an unavailable credential reference", async () => {
  h.rows[0].configuration.authentication = { kind: "bearer", credential_binding: "withdrawn" };
  render();
  select();
  expect(h.t).toHaveBeenCalledWith("rework.mcp.impact", { count: 2 });
  expect((button("disable") as HTMLButtonElement).disabled).toBe(false);
  await act(async () => button("disable").click());
  expect(h.update).toHaveBeenCalledWith({
    id: "one",
    updateMcpConnection: {
      expected_revision: 7,
      display_name: "Shared tools",
      description: "Provider",
      configuration: h.rows[0].configuration,
      enabled: false,
    },
  });
});
