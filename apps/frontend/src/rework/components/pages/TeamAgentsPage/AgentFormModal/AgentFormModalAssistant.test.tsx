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
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements.ts", () => ({
  useTeamRoutingPolicyQuery: () => ({ currentData: undefined, isError: false }),
  useAvailableModelProfilesQuery: () => ({ currentData: undefined, isError: false }),
}));
vi.mock("../../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ agentsNicknameSingular: "agent" }),
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
const lastDialogProps = () =>
  h.dialog.mock.lastCall?.[0] as {
    open: boolean;
    capabilities: unknown[];
    onApply: (draft: unknown) => void;
    current: unknown;
  };

describe("AgentFormModal creation assistant", () => {
  it("stays hidden on the template step and appears once a template is chosen", () => {
    render("create");
    expect(assistantButton()).toBeUndefined();

    act(() => [...document.querySelectorAll("button")].find((node) => node.textContent === "pick-template")?.click());
    expect(assistantButton().disabled).toBe(false);
  });

  it("opens from the header in edit mode and writes the applied draft into the form", () => {
    render("edit");
    expect(assistantButton().disabled).toBe(false);
    expect(document.querySelector('[data-testid="assistant-dialog"]')).toBeNull();

    act(() => assistantButton().click());
    expect(document.querySelector('[data-testid="assistant-dialog"]')).not.toBeNull();
    expect(lastDialogProps().current).toEqual({
      name: "Existing",
      role: "Old role",
      description: "",
      systemPrompt: "Old prompt",
      capabilityIds: [],
      capabilityConfigValues: {},
    });

    act(() =>
      lastDialogProps().onApply({ name: "New name", systemPrompt: "New prompt", capabilityIds: ["team_wiki"] }),
    );

    const props = lastBodyProps();
    expect(props.displayName).toBe("New name");
    expect(props.role).toBe("Old role");
    expect(props.tuningFieldValues).toEqual({ "prompts.system": "New prompt" });
    expect(props.selectedCapabilityIds).toEqual(["team_wiki"]);
    expect(props.draftRevision).toBe(1);
    expect(document.querySelector('[data-testid="assistant-dialog"]')).toBeNull();
  });

  it("keeps included Graph capabilities and their saved configuration when applying a draft", () => {
    const config = {
      document_access: { schema_version: 1, config: { attachments: true, team_documents: false } },
    };
    render(
      "edit",
      {
        ...TEMPLATE,
        supports_capabilities: false,
        available_capabilities: [{ id: "document_access" }],
      } as AgentTemplateSummary,
      { ...INSTANCE, capability_config: config },
    );
    act(() => assistantButton().click());
    expect(lastDialogProps().capabilities).toEqual([]);

    act(() => lastDialogProps().onApply({ name: "Graph helper", capabilityIds: ["document_access"] }));

    expect(lastBodyProps().displayName).toBe("Graph helper");
    expect(lastBodyProps().selectedCapabilityIds).toEqual([]);
    expect(lastBodyProps().capabilityConfigValues).toEqual({ document_access: config.document_access.config });
  });
});
