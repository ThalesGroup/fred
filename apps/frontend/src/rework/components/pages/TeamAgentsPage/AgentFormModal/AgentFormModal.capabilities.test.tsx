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
    t: (key: string) => key,
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
