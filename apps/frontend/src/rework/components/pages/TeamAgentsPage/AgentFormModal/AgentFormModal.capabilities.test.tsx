// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { INSTANCE, TEMPLATE } from "../weaverAgentFixtures";
import { createAgentRequest, updateAgentRequest } from "../weaverAgents";
import type {
  AgentTemplateSummary,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import AgentFormModal, { type AgentFormPayload } from "./AgentFormModal";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
vi.mock("react-redux", () => ({ useDispatch: () => () => {} }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { user?: string }) => (options?.user ? `${key}: ${options.user}` : key),
    i18n: { language: "en" },
  }),
}));
vi.mock("../../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ agentsNicknameSingular: "Agent" }),
}));
vi.mock("@shared/organisms/SettingsModal/SettingsModal.tsx", () => ({
  default: ({ children, actions }: { children: ReactNode; actions: ReactNode }) => (
    <div>
      {children}
      <footer>{actions}</footer>
    </div>
  ),
}));
vi.mock("./TemplateBrowser/TemplateBrowser.tsx", () => ({
  TemplateBrowser: ({ onSelect }: { onSelect: (id: string) => void }) => (
    <button onClick={() => onSelect(TEMPLATE.template_id)}>choose</button>
  ),
}));
vi.mock("./TuningFieldRenderer.tsx", () => ({ TuningFieldRenderer: () => null }));
vi.mock("../../../../features/capabilities/configWidgetRegistry.ts", () => ({ configWidgetFor: () => undefined }));

const template: AgentTemplateSummary = {
  ...TEMPLATE,
  default_tuning_fields: [],
  available_capabilities: [
    {
      id: "document_access",
      version: "0.2.0",
      name: "capability.document_access.name",
      description: "capability.document_access.description",
    },
  ],
};
const corpus = { team_documents: true, attachments: false };
const submitted = vi.fn<(payload: AgentFormPayload) => Promise<void>>(async () => {});
let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  submitted.mockClear();
});
function render(tpl = template, saved?: ManagedAgentInstanceSummary) {
  act(() =>
    root.render(
      <MemoryRouter>
        <AgentFormModal
          isOpen
          isSubmitting={false}
          mode={saved ? "edit" : "create"}
          templates={[tpl]}
          editInstance={saved}
          onClose={() => {}}
          onSubmit={submitted}
        />
      </MemoryRouter>,
    ),
  );
}
function button(text: string) {
  const found = [...container.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent?.includes(text));
  if (!found) throw new Error(`Missing button: ${text}`);
  return found;
}
function click(element: HTMLElement) {
  act(() => element.click());
}
function section(name: string) {
  click(button(`rework.teams.formAgent.sections.${name}`));
}
function advanced() {
  click(
    container.querySelector<HTMLInputElement>('[aria-label="rework.teams.formAgent.capabilities.viewToggle.aria"]')!,
  );
}
function capability(id: string) {
  return container.querySelector<HTMLInputElement>(`input[aria-label="capability.${id}.name"]`)!;
}
function createForm(tpl = template) {
  render(tpl);
  click(button("choose"));
  section("commitments");
  const input = container.querySelector("textarea")!;
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(input, "Internal use");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  section("tools");
}
async function submit() {
  await act(async () => button("rework.create").click());
  expect(submitted).toHaveBeenCalledOnce();
  return createAgentRequest(submitted.mock.calls[0][0]);
}
const teamPack = () => button("packs.teamDocuments.title");
const attachmentsPack = () => button("packs.attachments.title");

it("offers both document packs from the inventory and creates team documents", async () => {
  createForm();
  expect(attachmentsPack().disabled).toBe(false);
  expect(teamPack().disabled).toBe(false);
  click(teamPack());
  expect(teamPack().getAttribute("aria-checked")).toBe("true");
  advanced();
  expect(capability("document_access").checked).toBe(true);
  expect(await submit()).toMatchObject({
    capability_ids: ["document_access"],
    capability_config_values: { document_access: corpus },
  });
});
it("removes the Simple selection in Advanced", async () => {
  createForm();
  click(teamPack());
  advanced();
  click(capability("document_access"));
  expect(await submit()).toMatchObject({ capability_ids: [] });
});
it("hides document packs when the inventory lacks document_access", () => {
  createForm({ ...template, available_capabilities: [] });
  expect(container.textContent).not.toContain("packs.teamDocuments.title");
  advanced();
  expect(capability("document_access")).toBeNull();
});
it("keeps the defaults of a fixed template without switches", async () => {
  createForm({ ...template, supports_capabilities: false, default_capability_ids: ["document_access"] });
  expect(container.querySelector('button[role="switch"]')).toBeNull();
  expect(await submit()).toMatchObject({ capability_ids: ["document_access"] });
});
it("edits the saved selection and resubmits it for validation", async () => {
  const saved = {
    ...INSTANCE,
    selected_capability_ids: ["document_access"],
    capability_config: { document_access: { schema_version: "0.2.0", config: corpus } },
  };
  render(template, saved);
  section("tools");
  expect(teamPack().disabled).toBe(false);
  expect(teamPack().getAttribute("aria-checked")).toBe("true");
  click(teamPack());
  await act(async () => button("rework.save").click());
  expect(updateAgentRequest(submitted.mock.calls[0][0], saved)).toMatchObject({ capability_ids: [] });
});

it("keeps central selection across Simple and Advanced and submits its distinct identity", async () => {
  const id = "managed-mcp:8cfd2a56-2d35-4d18-b67c-5e42b0a9c122";
  createForm({
    ...template,
    available_capabilities: [
      ...template.available_capabilities,
      {
        id,
        name: "Central search",
        description: "External tools",
        version: "1",
        icon: "extension",
        config_fields: [],
      },
    ],
  });
  const toggle = container.querySelector<HTMLInputElement>('[aria-label="Central search"]')!;
  click(toggle);
  advanced();
  expect(container.querySelector<HTMLInputElement>('[aria-label="Central search"]')!.checked).toBe(true);
  expect(await submit()).toMatchObject({ capability_ids: [id] });
});

it("uses resolved audit names and a neutral label for inaccessible authors", () => {
  render(template, {
    ...INSTANCE,
    created_by: "author-one",
    updated_by: "unresolved-author",
    created_by_name: "Alice Martin",
    updated_by_name: null,
  });
  expect(container.textContent).toContain("Alice Martin");
  expect(container.textContent).toContain("rework.mcp.authorUnavailable");
  expect(container.textContent).not.toContain("unresolved-author");
  expect(container.textContent).not.toContain("author-one");
});
it("preserves unresolved MCP selections until explicitly removed, without exposing the reference", async () => {
  const id = "managed-mcp:8cfd2a56-2d35-4d18-b67c-5e42b0a9c122";
  render(template, { ...INSTANCE, selected_capability_ids: [id] });
  section("tools");
  expect(container.textContent).toContain("rework.mcp.connectionUnavailable");
  expect(container.textContent).not.toContain(id);
  click(container.querySelector<HTMLInputElement>('[aria-label="rework.mcp.connectionUnavailable"]')!);
  expect(container.textContent).not.toContain("rework.mcp.connectionUnavailable");
});

it("names a selected withdrawn connection from the canonical agent projection", () => {
  const id = "managed-mcp:unavailable";
  render(template, { ...INSTANCE, selected_capability_ids: [id], selected_capability_names: { [id]: "Postal Demo" } });
  section("tools");
  expect(container.textContent).toContain("Postal Demo");
  expect(container.textContent).toContain("rework.mcp.unavailableSelection");
  expect(container.textContent).not.toContain(id);
  expect(container.textContent).not.toContain("rework.mcp.connectionUnavailable");
});

it.each(["react", "deep"])(
  "selects native Tabular alone in the %s form without a managed connection",
  async (category) => {
    const id = "mcp-knowledge-flow-mcp-tabular";
    createForm({
      ...template,
      category,
      available_capabilities: [
        { id, version: "1", name: "mcp.servers.tabular.name", description: "mcp.servers.tabular.description" },
      ],
    });
    const toggle = button("mcp.servers.tabular.name");
    click(toggle);
    const pack = toggle.closest("li")!;
    click(pack.querySelector<HTMLButtonElement>("button[aria-expanded]")!);
    expect(pack.querySelector('[role="img"]')?.getAttribute("aria-label")).toBe(
      "rework.teams.formAgent.capabilities.included.activeTooltip",
    );
    expect(container.textContent).not.toContain("rework.mcp.title");
    expect(await submit()).toMatchObject({ capability_ids: [id] });
  },
);

it("explains a withdrawn native Tabular selection and lets the editor remove it", () => {
  const id = "mcp-knowledge-flow-mcp-tabular";
  render(template, {
    ...INSTANCE,
    selected_capability_ids: [id],
    selected_capability_names: { [id]: "mcp.servers.tabular.name" },
  });
  section("tools");
  expect(container.textContent).toContain("mcp.servers.tabular.name");
  expect(container.textContent).toContain("rework.teams.formAgent.capabilities.included.unavailableTooltip");
  click(container.querySelector<HTMLInputElement>('[aria-label="mcp.servers.tabular.name"]')!);
  expect(container.textContent).not.toContain("mcp.servers.tabular.name");
});
