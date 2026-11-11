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
  inventoryError: false,
  loading: false,
  permission: false,
  setPermission: vi.fn(),
  rows: [] as McpConnectionView[],
  query: vi.fn(),
  publish: vi.fn(),
  test: vi.fn(),
  update: vi.fn(),
  t: vi.fn((key: string) => key),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: h.t, i18n: { language: "en" } }) }));
vi.mock("@core/hooks/useSpaceAccess", () => ({
  useSpaceAccess: () => ({ allowed: h.admin, settled: true, error: undefined }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMcpConnectionsQuery: (...args: unknown[]) => {
    h.query(...args);
    return { currentData: h.rows, isError: h.error, isFetching: h.loading };
  },
  useOrganizationCapabilitiesQuery: () => ({
    isError: h.inventoryError,
    currentData: [
      {
        source_id: "$mcp",
        origin: "managed_mcp",
        capabilities: h.rows.map((row) => ({
          capability_id: row.capability_id,
          default_on: h.permission,
          advertised: row.available,
        })),
      },
    ],
  }),
  useSetOrganizationCapabilityDefaultMutation: () => [
    (args: unknown) => ({ unwrap: async () => h.setPermission(args) }),
  ],
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
  h.inventoryError = false;
  h.loading = false;
  h.permission = false;
  h.rows = [
    {
      id: "one",
      capability_id: "managed-mcp:one",
      tool_changes: { added: ["search"], modified: [], removed: [] },
      space_id: "org-a",
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
const render = (spaceId = "org-a") => act(() => root.render(<McpConnectionsPage spaceId={spaceId} />));
const select = () => act(() => button("details").click());
const confirm = async () =>
  act(async () => {
    const dialog = document.querySelector('[role="alertdialog"]')!;
    [...dialog.querySelectorAll<HTMLButtonElement>("button")]
      .find((item) => item.textContent !== "common.cancel")!
      .click();
  });
const button = (key: string) =>
  [...container.querySelectorAll("button")].find((item) => item.textContent === `rework.mcp.${key}`)!;
it("hides cached inventory without space management permission", () => {
  h.admin = false;
  render();
  expect(h.query).toHaveBeenLastCalledWith({ spaceId: "org-a" }, expect.objectContaining({ skip: true }));
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
    spaceId: "org-a",
    id: "one",
    mcpPublication: { expected_revision: 7, expected_checked_at: h.rows[0].checked_at },
  });
  expect(h.update).not.toHaveBeenCalled();
});
it("cannot publish an observation from an older configuration", () => {
  h.rows[0].observation_revision = 6;
  h.rows[0].tool_changes = null;
  render();
  select();
  expect(button("publish").disabled).toBe(true);
});
it("technical withdrawal preserves the identity and carries optimistic concurrency", async () => {
  render();
  select();
  await act(async () => button("disable").click());
  await confirm();
  expect(h.update).toHaveBeenCalledWith({
    spaceId: "org-a",
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
  await confirm();
  expect(h.update).toHaveBeenCalledWith({
    spaceId: "org-a",
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

it("edits a trusted service without a URL or static credential and keeps publication separate", async () => {
  h.rows[0].configuration = {
    url: "https://kf.invalid/knowledge-flow/v2/mcp/tabular",
    authentication: { kind: "knowledge_flow_tabular" },
  };
  render();
  select();
  await act(async () => button("edit").click());
  const dialog = document.querySelector<HTMLElement>('[role="dialog"]')!;
  expect(dialog.textContent).toContain("rework.mcp.trustedService");
  expect(dialog.querySelector('input[value="https://kf.invalid/knowledge-flow/v2/mcp/tabular"]')).toBeNull();
  const save = [...dialog.querySelectorAll("button")].find((item) => item.textContent === "rework.mcp.save")!;
  await act(async () => save.click());
  expect(h.update).toHaveBeenCalledWith({
    spaceId: "org-a",
    id: "one",
    updateMcpConnection: expect.objectContaining({
      expected_revision: 7,
      configuration: expect.objectContaining({ url: "", authentication: { kind: "knowledge_flow_tabular" } }),
    }),
  });
  expect(h.test).not.toHaveBeenCalled();
  expect(h.publish).not.toHaveBeenCalled();
});

it("clears inspection and the form when the owning organization changes", async () => {
  render();
  select();
  await act(async () => button("edit").click());
  expect(document.querySelector('[role="dialog"]')).not.toBeNull();
  h.rows = [];
  render("org-b");
  expect(h.query).toHaveBeenLastCalledWith({ spaceId: "org-b" }, expect.anything());
  expect(document.querySelector('[role="dialog"]')).toBeNull();
  expect(container.textContent).not.toContain("Shared tools");
  expect(button("publish")).toBeUndefined();
  render("org-a");
  expect(document.querySelector('[role="dialog"]')).toBeNull();
});

it("grants organization usage independently of technical activation", async () => {
  render();
  await act(async () => container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click());
  expect(h.setPermission).toHaveBeenCalledWith({
    organizationId: "org-a",
    sourceId: "$mcp",
    capabilityId: "managed-mcp:one",
    setDefaultOnRequest: { default_on: true },
  });
  expect(h.update).not.toHaveBeenCalled();
  expect(h.publish).not.toHaveBeenCalled();
  expect(container.textContent).not.toContain("managed-mcp:");
});
it("confirms revocation while keeping technical configuration unchanged", async () => {
  h.permission = true;
  render();
  await act(async () => container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click());
  expect(h.setPermission).not.toHaveBeenCalled();
  await confirm();
  expect(h.setPermission).toHaveBeenCalledWith(expect.objectContaining({ setDefaultOnRequest: { default_on: false } }));
  expect(h.update).not.toHaveBeenCalled();
});
it("does not invent a denied permission when governance cannot load", () => {
  h.inventoryError = true;
  render();
  expect(container.textContent).toContain("rework.mcp.permissionUnknown");
  expect(container.querySelector('input[type="checkbox"]')).toBeNull();
});
it("shows contract changes including removed tools and validates the entire inventory", async () => {
  const row = h.rows[0];
  row.published_revision = 7;
  row.published_tools = [
    { name: "search", input_schema: { type: "object" } },
    { name: "old", input_schema: {} },
  ];
  row.observed_tools = [
    { name: "search", input_schema: { type: "object", required: ["query"] } },
    { name: "new", input_schema: {} },
  ];
  row.tool_changes = { added: ["new"], modified: ["search"], removed: ["old"] };
  render();
  select();
  const drawer = container.querySelector("aside")!;
  expect(drawer.textContent).toContain("rework.mcp.modified");
  expect(drawer.textContent).toContain("rework.mcp.removed");
  expect(drawer.textContent).toContain("rework.mcp.added");
  await act(async () => button("applyChanges").click());
  expect(h.publish).toHaveBeenCalledWith(
    expect.objectContaining({ mcpPublication: { expected_revision: 7, expected_checked_at: row.checked_at } }),
  );
});
it("reports no difference once and disables redundant validation", () => {
  h.rows[0].published_revision = 7;
  h.rows[0].published_tools = h.rows[0].observed_tools;
  h.rows[0].tool_changes = { added: [], modified: [], removed: [] };
  render();
  select();
  expect(container.textContent).toContain("rework.mcp.upToDate");
  expect(button("applyChanges").disabled).toBe(true);
  expect(container.textContent).not.toContain("rework.mcp.published");
});
it("never presents retained tools as a successful new check after failure", () => {
  h.rows[0].observation_state = "unavailable";
  h.rows[0].published_tools = h.rows[0].observed_tools;
  h.rows[0].tool_changes = null;
  render();
  select();
  expect(container.textContent).toContain("rework.mcp.discoveryFailed");
  expect(container.textContent).toContain("rework.mcp.previousInventory");
  expect(container.textContent).not.toContain("rework.mcp.upToDate");
  expect(button("publish").disabled).toBe(true);
});
it("shows explicit loading, empty and missing-connection states", () => {
  h.rows = [];
  h.loading = true;
  render();
  expect(container.textContent).toContain("common.loading");
  expect(container.textContent).not.toContain("rework.mcp.empty");
  h.loading = false;
  render();
  expect(container.textContent).toContain("rework.mcp.empty");
});
it("retains an open drawer with a neutral message when its connection disappears", () => {
  render();
  select();
  h.rows = [];
  render();
  expect(container.querySelector("aside")!.textContent).toContain("rework.mcp.connectionUnavailable");
  expect(container.textContent).not.toContain("managed-mcp:");
});

it("keeps the drawer open when Escape belongs to the connection form", async () => {
  render();
  select();
  await act(async () => button("edit").click());
  act(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  expect(container.querySelector("aside")).not.toBeNull();
  expect(document.querySelector('[role="dialog"]')).not.toBeNull();
});

it("requires revalidation of unchanged tools after a configuration change", () => {
  h.rows[0].published_revision = 6;
  h.rows[0].published_tools = h.rows[0].observed_tools;
  h.rows[0].tool_changes = { added: [], modified: [], removed: [] };
  render();
  select();
  expect(container.textContent).toContain("rework.mcp.validationRequired");
  expect(container.textContent).not.toContain("rework.mcp.upToDate");
  expect(button("applyChanges").disabled).toBe(false);
});
