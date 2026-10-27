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
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      key === "rework.weaverAgents.documentSources" ? `${values?.corpus}/${values?.attachments}` : key,
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
    "document_access",
    "document_summarize",
    "document_similarity",
    "team_wiki",
    "writable_document",
  ].map((id) => ({
    id,
    version: "0.2.0",
    name: `capability.${id}.name`,
    description: `capability.${id}.description`,
  })),
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

it("creates corpus-only from the existing pack and reflects it in Advanced", async () => {
  createForm();
  for (const pack of container.querySelectorAll<HTMLButtonElement>('button[role="switch"]')) {
    expect(pack.disabled).toBe(pack !== teamPack());
  }
  click(teamPack());
  expect(teamPack().getAttribute("aria-checked")).toBe("true");
  advanced();
  expect(capability("document_access").checked).toBe(true);
  for (const id of ["document_summarize", "document_similarity", "team_wiki", "writable_document"]) {
    expect(capability(id).disabled).toBe(true);
    expect(capability(id).checked).toBe(false);
  }
  expect(container.querySelector('input[type="file"]')).toBeNull();
  expect(await submit()).toEqual({
    template_id: TEMPLATE.template_id,
    display_name: "Custom",
    role: undefined,
    description: "Template description",
    usage_statement: "Internal use",
    tuning_field_values: {},
    capability_ids: ["document_access"],
    capability_config_values: { document_access: corpus },
  });
});
it("activates in Advanced and removes document_access in Simple before creation", async () => {
  createForm();
  advanced();
  click(capability("document_access"));
  advanced();
  expect(teamPack().getAttribute("aria-checked")).toBe("true");
  click(teamPack());
  expect(teamPack().getAttribute("aria-checked")).toBe("false");
  expect(await submit()).toMatchObject({ capability_ids: [], capability_config_values: {} });
});
it("removes the Simple selection in Advanced", async () => {
  createForm();
  click(teamPack());
  advanced();
  click(capability("document_access"));
  expect(await submit()).toMatchObject({ capability_ids: [], capability_config_values: {} });
});
it("retains creation without capabilities and does not activate template defaults", async () => {
  createForm({ ...template, default_capability_ids: ["document_access", "team_wiki"] });
  expect(await submit()).toMatchObject({ capability_ids: [], capability_config_values: {} });
});
it("cannot activate corpus search when absent from the catalog", () => {
  createForm({
    ...template,
    available_capabilities: template.available_capabilities.filter((c) => c.id !== "document_access"),
  });
  expect(container.textContent).not.toContain("packs.teamDocuments.title");
  advanced();
  expect(capability("document_access")).toBeNull();
  expect(capability("team_wiki").disabled).toBe(true);
});
it("does not open fixed-capability templates", () => {
  createForm({ ...template, supports_capabilities: false, default_capability_ids: ["document_access"] });
  expect(container.querySelector('button[role="switch"]')).toBeNull();
  advanced();
  expect(capability("document_access")).toBeNull();
});
it("reads saved sources, keeps both views locked and omits capabilities from metadata PATCH", async () => {
  const saved = {
    ...INSTANCE,
    selected_capability_ids: ["document_access"],
    capability_config: {
      document_access: { schema_version: "0.2.0", config: corpus },
    },
  };
  render(template, saved);
  section("tools");
  expect(teamPack().disabled).toBe(true);
  expect(teamPack().getAttribute("aria-checked")).toBe("true");
  expect(container.textContent).toContain("rework.weaverAgents.sourceEnabled/rework.weaverAgents.sourceDisabled");
  advanced();
  expect(capability("document_access").checked).toBe(true);
  expect(capability("document_access").disabled).toBe(true);
  await act(async () => button("rework.save").click());
  const payload = submitted.mock.calls[0][0];
  expect(payload.capabilityConfigValues).toEqual({ document_access: corpus });
  expect(updateAgentRequest({ ...payload, displayName: "Renamed" }, saved)).toEqual({ display_name: "Renamed" });
});
