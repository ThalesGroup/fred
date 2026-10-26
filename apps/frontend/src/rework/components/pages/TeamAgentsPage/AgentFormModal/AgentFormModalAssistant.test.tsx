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
  description: "Template description",
  default_capability_ids: [],
  available_capabilities: [{ id: "team_wiki" }, { id: "html_artifact" }],
  default_tuning_fields: [{ key: "prompts.system", type: "prompt", title: "Prompt", default: "" }],
} as unknown as AgentTemplateSummary;

const INSTANCE = {
  template_id: "runtime:agent",
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

function render(mode: "create" | "edit", template = TEMPLATE, instance = INSTANCE) {
  act(() => {
    root.render(
      <AgentFormModal
        isOpen
        isSubmitting={false}
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
  it("retains its place after template selection but cannot open an unconnected dialog", () => {
    render("create");
    expect(assistantButton()).toBeUndefined();
    act(() => [...document.querySelectorAll("button")].find((node) => node.textContent === "pick-template")?.click());
    expect(assistantButton().disabled).toBe(true);
    expect(assistantButton().title).toBe("rework.weaverAgents.notConnected");
    act(() => assistantButton().click());
    expect(h.dialog).not.toHaveBeenCalled();
  });
  it("keeps the saved prompt and does not mount the assistant while editing", () => {
    render("edit");
    expect(lastBodyProps().tuningFieldValues).toEqual(INSTANCE.tuning_field_values);
    expect(assistantButton().disabled).toBe(true);
    expect(h.dialog).not.toHaveBeenCalled();
  });
});
