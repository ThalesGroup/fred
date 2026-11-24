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

// The creation assistant's single entry point: the form header button, and
// what applying a draft writes into the form.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  AgentTemplateSummary,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const h = vi.hoisted(() => ({
  body: vi.fn(),
  dialog: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
// Model reads are outside these form interaction tests; keep them isolated from Redux.
vi.mock("../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements.ts", () => ({
  useTeamRoutingPolicyQuery: () => ({ currentData: undefined, isError: false }),
  useAvailableModelProfilesQuery: () => ({ currentData: undefined, isError: false }),
}));
vi.mock("../../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ agentsNicknameSingular: "agent" }),
}));
// These form-only tests have no Redux provider; model selection is outside their scope.
vi.mock("../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements.ts", () => ({
  useTeamRoutingPolicyQuery: () => ({ currentData: undefined }),
  useAvailableModelProfilesQuery: () => ({ currentData: undefined }),
}));
vi.mock("./AgentFormBody.tsx", () => ({
  AgentFormBody: (props: Record<string, unknown>) => {
    h.body(props);
    return <div data-testid="form-body" />;
  },
}));
vi.mock("./TemplateBrowser/TemplateBrowser.tsx", () => ({
  TemplateBrowser: ({ onSelect }: { onSelect: (id: string) => void }) => (
    <button onClick={() => onSelect("runtime:agent")}>pick-template</button>
  ),
}));
vi.mock("./CreationAssistantDialog/CreationAssistantDialog.tsx", () => ({
  CreationAssistantDialog: (props: { open: boolean }) => {
    h.dialog(props);
    return props.open ? <div data-testid="assistant-dialog" /> : null;
  },
}));

import AgentFormModal from "./AgentFormModal";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const TEMPLATE = {
  template_id: "runtime:agent",
  display_name: "Template name",
  creation_assistant_prompt_key: "prompts.system",
  supports_capabilities: true,
  description: "Template description",
  default_capability_ids: [],
  available_capabilities: [{ id: "team_wiki" }, { id: "html_artifact" }],
  default_tuning_fields: [{ key: "prompts.system", type: "prompt", title: "Prompt", default: "" }],
} as unknown as AgentTemplateSummary;

const INSTANCE = {
  template_id: "runtime:agent",
  agent_instance_id: "instance-1",
  configuration_revision: 1,
  display_name: "Existing",
  role: "Old role",
  description: "",
  usage_statement: "",
  tuning_field_values: { "prompts.system": "Old prompt" },
  selected_capability_ids: [],
} as unknown as ManagedAgentInstanceSummary;

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  h.body.mockReset();
  h.dialog.mockReset();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.getElementById("modal-portal")?.remove();
});

function render(mode: "create" | "edit", template = TEMPLATE, instance = INSTANCE, isSubmitting = false) {
  act(() => {
    root.render(
      <AgentFormModal
        isOpen
        isSubmitting={isSubmitting}
        mode={mode}
        teamId="team-1"
        templates={[template]}
        editInstance={mode === "edit" ? instance : undefined}
        onClose={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );
  });
}

const assistantButton = () =>
  [...document.querySelectorAll("button")].find((node) =>
    node.textContent?.includes("rework.teams.formAgent.creationAssistant.open"),
  ) as HTMLButtonElement;
const lastBodyProps = () => h.body.mock.lastCall?.[0] as Record<string, unknown>;
describe("Weaver creation assistant", () => {
  it("opens only after an eligible template is selected", () => {
    render("create");
    expect(assistantButton()).toBeUndefined();
    act(() => [...document.querySelectorAll("button")].find((node) => node.textContent === "pick-template")?.click());
    expect(assistantButton().disabled).toBe(false);
    act(() => assistantButton().click());
    expect(h.dialog.mock.lastCall?.[0]).toMatchObject({ open: true, spaceId: "team-1", templateId: "runtime:agent" });
  });
  it("applies only selected draft values to the canonical field and preserves unrelated form values", () => {
    render("edit");
    const props = h.dialog.mock.lastCall?.[0] as unknown as { onApply: (draft: object) => void };
    act(() => props.onApply({ name: "New name", systemPrompt: "New prompt" }));
    expect(lastBodyProps()).toMatchObject({
      displayName: "New name",
      role: "Old role",
      tuningFieldValues: { "prompts.system": "New prompt" },
    });
  });
  it("applies identity, prompt and capabilities together without overwriting the generated fields", () => {
    render("edit");
    const props = h.dialog.mock.lastCall?.[0] as unknown as { onApply: (draft: object) => void };
    act(() =>
      props.onApply({
        name: "Draft name",
        role: "Draft role",
        description: "Draft description",
        systemPrompt: "Draft prompt",
        capabilityIds: ["team_wiki"],
      }),
    );
    expect(lastBodyProps()).toMatchObject({
      displayName: "Draft name",
      role: "Draft role",
      description: "Draft description",
      tuningFieldValues: { "prompts.system": "Draft prompt" },
      selectedCapabilityIds: ["team_wiki"],
      usageStatement: "",
    });
  });
  it("unmounts the assistant when writing becomes unavailable or the saved revision changes", () => {
    render("edit");
    act(() => assistantButton().click());
    expect(document.querySelector('[data-testid="assistant-dialog"]')).not.toBeNull();
    render("edit", TEMPLATE, INSTANCE, true);
    expect(document.querySelector('[data-testid="assistant-dialog"]')).toBeNull();
    render("edit");
    render("edit", TEMPLATE, { ...INSTANCE, configuration_revision: 2 });
    expect(document.querySelector('[data-testid="assistant-dialog"]')).toBeNull();
    expect(assistantButton().disabled).toBe(true);
  });
  it("closes the assistant when mode or edited instance changes", () => {
    render("edit");
    act(() => assistantButton().click());
    render("edit", TEMPLATE, { ...INSTANCE, agent_instance_id: "instance-2" });
    expect(document.querySelector('[data-testid="assistant-dialog"]')).toBeNull();
    act(() => assistantButton().click());
    render("create");
    expect(document.querySelector('[data-testid="assistant-dialog"]')).toBeNull();
  });
  it("does not infer eligibility from tuning fields when the server omits the canonical key", () => {
    render("edit", { ...TEMPLATE, creation_assistant_prompt_key: null });
    expect(assistantButton().disabled).toBe(true);
    expect(h.dialog).not.toHaveBeenCalled();
  });
  it("uses the server key even when another prompt field is present", () => {
    render("edit", { ...TEMPLATE, creation_assistant_prompt_key: "prompts.custom" });
    const props = h.dialog.mock.lastCall?.[0] as unknown as { onApply: (draft: object) => void };
    act(() => props.onApply({ systemPrompt: "Custom" }));
    expect(lastBodyProps().tuningFieldValues).toEqual({ "prompts.system": "Old prompt", "prompts.custom": "Custom" });
  });
});
