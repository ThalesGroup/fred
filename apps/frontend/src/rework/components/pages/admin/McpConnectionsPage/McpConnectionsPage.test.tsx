// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { McpConnectionView } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
const h = vi.hoisted(() => ({
  admin: true,
  allowed: true,
  create: vi.fn(),
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
  useSpaceAccess: () => ({ offered: h.admin, allowed: h.admin && h.allowed, settled: h.allowed, error: undefined }),
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
  useCreateMcpConnectionMutation: () => [(args: unknown) => ({ unwrap: async () => h.create(args) }), {}],
  useUpdateMcpConnectionMutation: () => [(args: unknown) => ({ unwrap: async () => h.update(args) }), {}],
  useTestMcpConnectionMutation: () => [(args: unknown) => ({ unwrap: async () => h.test(args) }), {}],
  usePublishMcpConnectionMutation: () => [(args: unknown) => ({ unwrap: async () => h.publish(args) }), {}],
}));
import McpConnectionsPage from "./McpConnectionsPage";
let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  vi.resetAllMocks();
  h.t.mockImplementation((key: string) => key);
  h.update.mockImplementation(() => h.rows[0]);
  h.create.mockImplementation(() => h.rows[0]);
  h.allowed = true;
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
  expect(button("publish")).toBeUndefined();
  expect(button("test").disabled).toBe(false);
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

it("does not expose internal Knowledge Flow authentication in the MCP editor", async () => {
  render();
  select();
  await act(async () => button("edit").click());
  expect(document.body.textContent).not.toContain("knowledge_flow_tabular");
  expect(document.body.textContent).not.toContain("trustedService");
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
it("advances past already validated tools without redundant publication", () => {
  h.rows[0].published_revision = 7;
  h.rows[0].published_tools = h.rows[0].observed_tools;
  h.rows[0].tool_changes = { added: [], modified: [], removed: [] };
  render();
  select();
  expect(container.textContent).toContain("rework.mcp.upToDate");
  expect(button("applyChanges")).toBeUndefined();
  expect(button("authorize").disabled).toBe(false);
  expect(container.textContent).not.toContain("rework.mcp.published");
});
it("never presents retained tools as a successful new check after failure", () => {
  h.rows[0].observation_state = "unavailable";
  h.rows[0].published_tools = h.rows[0].observed_tools;
  h.rows[0].tool_changes = null;
  render();
  select();
  expect(container.textContent).toContain("rework.mcp.discoveryFailed");
  expect(container.querySelector("aside")!.textContent).not.toContain("search");
  expect(container.textContent).not.toContain("rework.mcp.upToDate");
  expect(button("publish")).toBeUndefined();
  expect(button("test").disabled).toBe(false);
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

const reviewedConnection = () => {
  const row = h.rows[0];
  Object.assign(row, {
    enabled: false,
    available: false,
    published_revision: row.revision,
    published_tools: row.observed_tools,
    tool_changes: { added: [], modified: [], removed: [] },
  });
  return row;
};

it("guides discovery, review and activation using the latest server revisions", async () => {
  const observed = { ...h.rows[0], enabled: false, available: false };
  h.rows = [
    {
      ...observed,
      observation_state: "not_observed",
      observation_revision: null,
      checked_at: null,
      observed_tools: [],
      tool_changes: null,
    },
  ];
  h.test.mockImplementation(() => {
    h.rows = [observed];
    return observed;
  });
  h.publish.mockImplementation(() => {
    const row = reviewedConnection();
    h.rows = [{ ...row, revision: 8, published_revision: 8, observation_revision: 8 }];
    return h.rows[0];
  });
  h.update.mockImplementation(() => {
    h.rows = [
      { ...h.rows[0], revision: 9, published_revision: 9, observation_revision: 9, enabled: true, available: true },
    ];
    return h.rows[0];
  });
  h.setPermission.mockImplementation(() => {
    h.permission = true;
  });
  render();
  select();
  expect(container.querySelector('[aria-current="step"]')!.textContent).toContain("connectionStep");
  expect(button("publish")).toBeUndefined();
  await act(async () => button("test").click());
  expect(h.test).toHaveBeenCalledWith(expect.objectContaining({ mcpRevision: { expected_revision: 7 } }));
  expect(container.querySelector('[aria-current="step"]')!.textContent).toContain("toolsStep");
  expect(h.update).not.toHaveBeenCalled();
  expect(h.setPermission).not.toHaveBeenCalled();
  await act(async () => button("publish").click());
  expect(h.publish).toHaveBeenCalledWith(
    expect.objectContaining({ mcpPublication: { expected_revision: 7, expected_checked_at: observed.checked_at } }),
  );
  expect(container.querySelector('[aria-current="step"]')!.textContent).toContain("activationStep");
  await act(async () => button("activateAndAuthorize").click());
  expect(h.update).toHaveBeenCalledWith(
    expect.objectContaining({ updateMcpConnection: expect.objectContaining({ expected_revision: 8, enabled: true }) }),
  );
  expect(h.update.mock.invocationCallOrder[0]).toBeLessThan(h.setPermission.mock.invocationCallOrder[0]);
  expect(container.querySelector("aside")!.textContent).toContain("rework.mcp.readyHint");
});

it("does not authorize when activation fails or returns an unavailable connection", async () => {
  reviewedConnection();
  h.update.mockRejectedValueOnce({ status: 409 });
  render();
  select();
  await act(async () => button("activateAndAuthorize").click());
  expect(h.setPermission).not.toHaveBeenCalled();
  expect(container.querySelector("aside")!.textContent).toContain("rework.mcp.conflict");
  await act(async () => button("activateAndAuthorize").click());
  expect(h.setPermission).not.toHaveBeenCalled();
  expect(container.querySelector("aside")!.textContent).not.toContain("rework.mcp.readyHint");
});

it("resumes authorization after partial success without activating a second time", async () => {
  reviewedConnection();
  h.update.mockImplementation(() => {
    h.rows = [
      { ...h.rows[0], enabled: true, available: true, revision: 8, published_revision: 8, observation_revision: 8 },
    ];
    return h.rows[0];
  });
  h.setPermission.mockRejectedValueOnce({ status: 503 }).mockImplementationOnce(() => {
    h.permission = true;
  });
  render();
  select();
  await act(async () => button("activateAndAuthorize").click());
  expect(container.querySelector("aside")!.textContent).toContain("rework.mcp.authorizationPending");
  expect(container.querySelector("aside")!.textContent).not.toContain("rework.mcp.readyHint");
  await act(async () => button("authorize").click());
  expect(h.update).toHaveBeenCalledTimes(1);
  expect(h.setPermission).toHaveBeenCalledTimes(2);
  expect(container.querySelector("aside")!.textContent).toContain("rework.mcp.readyHint");
});

it("blocks duplicate submissions while activation is pending", async () => {
  reviewedConnection();
  let finish!: (row: McpConnectionView) => void;
  h.update.mockImplementation(
    () =>
      new Promise<McpConnectionView>((resolve) => {
        finish = resolve;
      }),
  );
  render();
  select();
  const activate = button("activateAndAuthorize");
  act(() => {
    activate.click();
    activate.click();
  });
  expect(h.update).toHaveBeenCalledTimes(1);
  expect(h.setPermission).not.toHaveBeenCalled();
  await act(async () => finish({ ...h.rows[0], enabled: true, available: true }));
  expect(h.setPermission).toHaveBeenCalledTimes(1);
});

it("keeps the form and drawer mounted while access is rechecked but blocks saves", async () => {
  render();
  select();
  await act(async () => button("edit").click());
  const drawer = container.querySelector("aside");
  const input = document.querySelector<HTMLInputElement>('[role="dialog"] input')!;
  h.allowed = false;
  render();
  expect(container.querySelector("aside")).toBe(drawer);
  expect(document.querySelector('[role="dialog"] input')).toBe(input);
  const save = [...document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')].find(
    (item) => item.textContent === "rework.mcp.save",
  )!;
  expect(save.disabled).toBe(true);
  h.allowed = true;
  render();
  expect(document.querySelector('[role="dialog"] input')).toBe(input);
  expect(save.disabled).toBe(false);
});

it("blocks commissioning while organization authorization is unknown", () => {
  reviewedConnection();
  h.inventoryError = true;
  render();
  select();
  expect(button("activateAndAuthorize").disabled).toBe(true);
  expect(container.querySelector("aside")!.textContent).toContain("rework.mcp.permissionUnknown");
});

it("allows reviewing previous steps without publishing already validated tools", async () => {
  reviewedConnection();
  render();
  select();
  act(() => [...container.querySelectorAll("button")].find((item) => item.textContent === "rework.back")!.click());
  expect(container.querySelector('[aria-current="step"]')!.textContent).toContain("toolsStep");
  expect(button("applyChanges")).toBeUndefined();
  await act(async () => button("continue").click());
  expect(h.publish).not.toHaveBeenCalled();
  expect(container.querySelector('[aria-current="step"]')!.textContent).toContain("activationStep");
});
