// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import type { ManagedAgentInstanceSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { INSTANCE, SPACE_A, SPACE_B, SPACES, TEMPLATE } from "./weaverAgentFixtures";

vi.mock("../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({
    agentsNicknameSingular: "Agent",
    agentsNicknamePlural: "Agents",
    agentIconName: "smart_toy",
  }),
}));
const notices = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), confirm: vi.fn() }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetToken: () => "fixture",
    GetUserId: () => "reader",
    GetSessionIdentity: () => "reader-session",
    ensureFreshToken: vi.fn(async () => false),
    CallLogout: vi.fn(),
  },
}));
vi.mock("../../../../common/platformAccess", () => ({ handlePlatformAccessDenial: vi.fn() }));
vi.mock("../../../../app/userPreferences", () => ({
  useCurrentUserPreference: () => "name",
  persistUserPreference: vi.fn(),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: notices.success, showError: notices.error }),
}));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: notices.confirm }),
}));
vi.mock("@shared/organisms/SettingsModal/SettingsModal", () => ({
  default: ({ children, actions, footer }: { children: ReactNode; actions: ReactNode; footer: ReactNode }) => (
    <section data-form>
      {actions}
      {children}
      {footer}
    </section>
  ),
}));
vi.mock("@shared/molecules/PromptEditor/PromptEditor", () => ({
  PROMPT_EDITOR_ROWS: 10,
  PromptEditor: ({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) => (
    <textarea aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} />
  ),
}));

import { enhancedControlPlaneApi as api } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { legacyControlPlaneApi as legacy } from "../../../../slices/legacyControlPlane/legacyControlPlaneApi";
import TeamAgentsPage from "./TeamAgentsPage";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const NativeRequest = globalThis.Request;
let root: Root;
let host: HTMLDivElement;
let store: ReturnType<typeof makeStore>;
let router: ReturnType<typeof createMemoryRouter>;
let rows: ManagedAgentInstanceSummary[];
let writable: boolean;
let catalogEmpty: boolean;
let emptyContext: boolean;
let failure: { target: "list" | "catalog" | "write" | "authorize" | "get"; status: number | "network" } | undefined;
let blockedSpace: string | undefined;
let releaseList: (() => void) | undefined;
let calls: { method: string; path: string; body: Record<string, unknown> | undefined }[];
const makeStore = () =>
  configureStore({
    reducer: { [api.reducerPath]: api.reducer, [legacy.reducerPath]: legacy.reducer },
    middleware: (defaults) => defaults().concat(api.middleware, legacy.middleware),
  });
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  rows = [structuredClone(INSTANCE)];
  writable = true;
  catalogEmpty = false;
  emptyContext = false;
  failure = undefined;
  calls = [];
  blockedSpace = undefined;
  releaseList = undefined;
  vi.clearAllMocks();
  vi.stubGlobal(
    "Request",
    class extends NativeRequest {
      constructor(input: RequestInfo | URL, init?: RequestInit) {
        super(typeof input === "string" ? new URL(input, "http://localhost") : input, init);
      }
    },
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      const path = new URL(request.url).pathname;
      const body = request.method === "GET" || request.method === "DELETE" ? undefined : await request.json();
      calls.push({ path, method: request.method, body });
      const target = path.endsWith("/authorize/space")
        ? "authorize"
        : path.endsWith("/agent-templates")
          ? "catalog"
          : request.method !== "GET"
            ? "write"
            : path.endsWith("/agent-instances")
              ? "list"
              : "get";
      if (failure?.target === target) {
        if (failure.status === "network") throw new TypeError("Offline");
        return json(
          { detail: "Rejected", code: failure.status === 409 ? "agent_name_conflict" : "refused" },
          failure.status,
        );
      }
      if (path.endsWith("/me/spaces")) return json(emptyContext ? [] : SPACES);
      if (target === "authorize") return json({ allowed: writable });
      if (target === "catalog") return json(catalogEmpty ? [] : [TEMPLATE]);
      const match = path.match(/\/spaces\/([^/]+)\/agent-instances(?:\/([^/]+))?$/);
      if (!match) throw new Error(`Unexpected request ${path}`);
      const [, spaceId, id] = match;
      if (request.method === "GET" && !id && spaceId === blockedSpace)
        await new Promise<void>((resolve) => {
          releaseList = resolve;
        });
      if (request.method === "GET")
        return json(
          id
            ? rows.find((row) => row.space_id === spaceId && row.agent_instance_id === id)
            : rows.filter((row) => row.space_id === spaceId),
        );
      if (request.method === "POST") {
        const row = {
          ...INSTANCE,
          ...body,
          space_id: spaceId,
          agent_instance_id: "created",
          tuning_field_values: body.tuning_field_values ?? {},
          selected_capability_ids: body.capability_ids,
          capability_config: {},
        };
        rows.push(row);
        return json(row, 201);
      }
      if (request.method === "PATCH") {
        rows = rows.map((row) => (row.agent_instance_id === id ? { ...row, ...body } : row));
        return json(rows.find((row) => row.agent_instance_id === id));
      }
      rows = rows.filter((row) => row.agent_instance_id !== id);
      return new Response(null, { status: 204 });
    }),
  );
  store = makeStore();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  releaseList?.();
  act(() => root.unmount());
  router?.dispose();
  store.dispatch(api.util.resetApiState());
  store.dispatch(legacy.util.resetApiState());
  host.remove();
  expect(
    calls.every(({ path }) =>
      /^\/control-plane\/v1\/(me\/spaces|authorize\/space|spaces\/[^/]+\/agent-(instances|templates))/.test(path),
    ),
  ).toBe(true);
  vi.unstubAllGlobals();
});
async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 40));
  });
}
async function mount(id = SPACE_A) {
  router = createMemoryRouter([{ path: "/team/:teamId/agents", element: <TeamAgentsPage /> }], {
    initialEntries: [`/team/${id}/agents`],
  });
  await act(async () => {
    root.render(
      <Provider store={store}>
        <RouterProvider router={router} />
      </Provider>,
    );
  });
  await settle();
}
function button(text: string) {
  return [...document.querySelectorAll<HTMLButtonElement>("button, [role=option]")].find(
    (item) => item.textContent?.includes(text) || item.getAttribute("aria-label") === text,
  )!;
}
async function click(text: string) {
  const node = button(text);
  expect(node, text).toBeTruthy();
  await act(async () => node.click());
  await settle();
}
async function input(label: string, value: string) {
  const labelNode = [...document.querySelectorAll("label")].find((item) => item.textContent?.includes(label));
  const node = (
    labelNode?.htmlFor ? document.getElementById(labelNode.htmlFor) : document.querySelector(`[aria-label="${label}"]`)
  ) as HTMLInputElement | HTMLTextAreaElement;
  expect(node, label).toBeTruthy();
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      node instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype,
      "value",
    )!.set!.call(node, value);
    node.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
async function menu(action: string) {
  await click("rework.agentCard.moreMenu");
  await click(action);
}
const writes = () => calls.filter((call) => call.method !== "GET" && !call.path.endsWith("/authorize/space"));

describe("Weaver agent management and unavailable adjacent actions", () => {
  it("reads canonical space routes, asks Write rather than inferring roles, and keeps unsupported actions disabled", async () => {
    await mount();
    expect(host.textContent).toContain("Saved Agent");
    expect(calls.find((call) => call.path.endsWith("/authorize/space"))?.body).toEqual({
      space_id: SPACE_A,
      permission: "write",
    });
    expect(button("rework.agentCard.chat").disabled).toBe(true);
    await click("rework.agentCard.moreMenu");
    for (const text of [
      "rework.agentCard.duplicate",
      "rework.agentCard.copyTo",
      "rework.agentMarketplace.menu.publish",
    ]) {
      expect(button(text).getAttribute("aria-disabled")).toBe("true");
      await click(text);
    }
    expect(writes()).toHaveLength(0);
  });
  it("does not read the creation catalog or expose management to a reader", async () => {
    writable = false;
    await mount();
    expect(host.textContent).toContain("Saved Agent");
    expect(button("rework.teams.agents.create")).toBeUndefined();
    expect(button("rework.agentCard.moreMenu")).toBeUndefined();
    expect(calls.some((call) => call.path.endsWith("/agent-templates"))).toBe(false);
  });
  it("distinguishes an empty list and an empty catalog without hiding existing agents", async () => {
    catalogEmpty = true;
    await mount();
    expect(host.textContent).toContain("Saved Agent");
    expect(host.textContent).toContain("rework.teams.formAgent.noTemplates");
    expect(button("rework.teams.agents.create").disabled).toBe(true);
  });
  it("shows the existing empty state with a working create action", async () => {
    rows = [];
    await mount();
    expect(host.textContent).toContain("rework.teams.agents.noAgent");
    expect(button("rework.teams.agents.firstCreate").disabled).toBe(false);
  });
  it("keeps the list available when the management catalog is refused", async () => {
    failure = { target: "catalog", status: 403 };
    await mount();
    expect(host.textContent).toContain("Saved Agent");
    expect(host.textContent).toContain("rework.weaverAgents.errors.forbidden");
  });
  it("keeps readable instances when the Write authorization request fails", async () => {
    failure = { target: "authorize", status: 403 };
    await mount();
    expect(host.textContent).toContain("Saved Agent");
    expect(calls.some((call) => call.path.endsWith("/agent-templates"))).toBe(false);
  });
  it.each([
    [401, "unauthorized"],
    [403, "forbidden"],
    [404, "notFound"],
    [500, "server"],
    [503, "server"],
    ["network", "network"],
  ] as const)("classifies list error %s", async (status, key) => {
    failure = { target: "list", status };
    await mount();
    expect(host.textContent).toContain(`rework.weaverAgents.errors.${key}`);
    expect(host.textContent).not.toContain("rework.serviceNotice.controlPlane");
  });
  it("opens GET state and changes metadata without resending tuning, capabilities or profile", async () => {
    await mount();
    await menu("rework.agentCard.edit");
    expect(calls.some((call) => call.method === "GET" && call.path.endsWith(INSTANCE.agent_instance_id))).toBe(true);
    await input("rework.teams.formAgent.fields.name.label", "Renamed");
    await click("rework.save");
    expect(writes()[writes().length - 1]?.body).toEqual({ display_name: "Renamed" });
    expect(host.textContent).toContain("Renamed");
    expect(rows[0].tuning_field_values).toEqual(INSTANCE.tuning_field_values);
    expect(rows[0].selected_capability_ids).toBeNull();
    expect(rows[0].capability_config).toEqual(INSTANCE.capability_config);
  });
  it("edits metadata even with no catalog", async () => {
    catalogEmpty = true;
    await mount();
    await menu("rework.agentCard.edit");
    await input("rework.teams.formAgent.fields.name.label", "No catalog");
    await click("rework.save");
    expect(writes()[writes().length - 1]?.body).toEqual({ display_name: "No catalog" });
  });
  it("shows the saved prompt and preserves hidden values when changing one tuning value", async () => {
    await mount();
    await menu("rework.agentCard.edit");
    await click("rework.teams.formAgent.sections.prompts");
    expect((document.querySelector('[aria-label="Prompt"]') as HTMLTextAreaElement).value).toBe("SAVED PROMPT");
    expect(button("rework.teams.formAgent.promptField.pickFromLibrary").disabled).toBe(true);
    await input("Prompt", "Edited prompt");
    await click("rework.save");
    expect(writes()[writes().length - 1]?.body).toEqual({
      tuning_field_values: { ...INSTANCE.tuning_field_values, prompt: "Edited prompt" },
    });
  });
  it("creates with the canonical template then rereads the saved instance", async () => {
    rows = [];
    await mount();
    await click("rework.teams.agents.firstCreate");
    await click("Custom");
    expect(button("rework.teams.formAgent.creationAssistant.open").disabled).toBe(true);
    await click("rework.teams.formAgent.sections.commitments");
    await input("rework.teams.formAgent.fields.usageStatement.label", "My use");
    await click("rework.create");
    expect(writes()[0].body).toMatchObject({
      template_id: TEMPLATE.template_id,
      capability_ids: [],
      recommended_chat_profile_id: null,
      tuning_field_values: { prompt: "CATALOG DEFAULT", temperature: 0.8 },
    });
    await menu("rework.agentCard.edit");
    expect(calls.some((call) => call.path.endsWith("/agent-instances/created") && call.method === "GET")).toBe(true);
  });
  it.each([
    [401, "unauthorized"],
    [403, "forbidden"],
    [404, "notFound"],
    [409, "conflict"],
    [422, "validation"],
    [500, "server"],
    ["network", "network"],
  ] as const)("keeps input and reports failed mutation %s", async (status, key) => {
    await mount();
    await menu("rework.agentCard.edit");
    await input("rework.teams.formAgent.fields.name.label", "My draft");
    failure = { target: "write", status };
    await click("rework.save");
    expect(notices.error).toHaveBeenCalledWith({
      summary: expect.stringContaining(`rework.weaverAgents.errors.${key}`),
    });
    expect(notices.success).not.toHaveBeenCalled();
    expect([...document.querySelectorAll("input")].some((node) => node.value === "My draft")).toBe(true);
  });
  it("does not infer lost space Write from an instance-level 403", async () => {
    await mount();
    await menu("rework.agentCard.edit");
    await input("rework.teams.formAgent.fields.name.label", "My draft");
    failure = { target: "write", status: 403 };
    await click("rework.save");
    await click("rework.cancel");
    failure = undefined;
    await menu("rework.agentCard.delete");
    await act(async () => notices.confirm.mock.lastCall![0].onConfirm());
    await settle();
    expect(writes().some((call) => call.method === "DELETE")).toBe(true);
  });
  it("toggles both ways and deletes only after confirmation, refreshing the list", async () => {
    await mount();
    await menu("rework.agentCard.deactivate");
    expect(writes()[writes().length - 1]?.body).toEqual({ status: "disabled" });
    await menu("rework.agentCard.activate");
    expect(writes()[writes().length - 1]?.body).toEqual({ status: "enabled" });
    await menu("rework.agentCard.delete");
    expect(writes().some((call) => call.method === "DELETE")).toBe(false);
    await act(async () => {
      await notices.confirm.mock.lastCall![0].onConfirm();
    });
    await settle();
    expect(host.textContent).not.toContain("Saved Agent");
    expect(host.textContent).toContain("rework.teams.agents.noAgent");
  });
  it("discards the old list and open form on a space change, including the personal alias", async () => {
    await mount();
    await menu("rework.agentCard.edit");
    blockedSpace = SPACE_B;
    await act(async () => {
      await router.navigate("/team/personal/agents");
    });
    await settle();
    expect(host.textContent).not.toContain("Saved Agent");
    expect(host.textContent).toContain("rework.teams.agents.loading");
    await act(async () => releaseList?.());
    await settle();
    expect(host.textContent).not.toContain("Saved Agent");
    expect(document.querySelector("[data-form]")).toBeNull();
    expect(calls.some((call) => call.path === `/control-plane/v1/spaces/${SPACE_B}/agent-instances`)).toBe(true);
    const queries = Object.values(store.getState()[api.reducerPath].queries);
    expect(queries.filter((query) => query?.endpointName === "listAgentInstances")).toHaveLength(2);
  });
  it("invalidates only the mutated space and rereads an edited instance", async () => {
    await mount();
    const other = store.dispatch(api.endpoints.listAgentInstances.initiate({ spaceId: SPACE_B }));
    await act(async () => {
      await other.unwrap();
    });
    const otherReads = () =>
      calls.filter((call) => call.path === `/control-plane/v1/spaces/${SPACE_B}/agent-instances`).length;
    expect(otherReads()).toBe(1);
    await menu("rework.agentCard.edit");
    await input("rework.teams.formAgent.fields.name.label", "New saved name");
    await click("rework.save");
    await menu("rework.agentCard.edit");
    expect([...document.querySelectorAll("input")].some((node) => node.value === "New saved name")).toBe(true);
    expect(otherReads()).toBe(1);
    expect(
      calls.filter((call) => call.method === "GET" && call.path.endsWith(INSTANCE.agent_instance_id)).length,
    ).toBeGreaterThanOrEqual(2);
    other.unsubscribe();
  });
  it("does not send a stale delete confirmation after changing spaces", async () => {
    await mount();
    await menu("rework.agentCard.delete");
    await act(async () => {
      await router.navigate(`/team/${SPACE_B}/agents`);
    });
    await settle();
    await act(async () => notices.confirm.mock.lastCall![0].onConfirm());
    expect(writes()).toHaveLength(0);
  });
  it("shows a failed reread rather than editing stale list data", async () => {
    await mount();
    failure = { target: "get", status: 404 };
    await menu("rework.agentCard.edit");
    expect(host.textContent).toContain("rework.weaverAgents.errors.notFound");
    expect(document.querySelector("[data-form]")).toBeNull();
  });
  it("refuses an unresolved legacy team id instead of treating it as a space id", async () => {
    await mount("legacy-team");
    expect(host.textContent).toContain("rework.weaverAgents.scopeUnavailable");
    expect(calls).toHaveLength(1);
  });
});
