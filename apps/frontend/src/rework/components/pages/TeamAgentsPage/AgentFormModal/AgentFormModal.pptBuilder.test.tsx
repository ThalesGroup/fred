import { INSTANCE } from "../weaverAgentFixtures";
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

import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import type {
  AgentTemplateSummary,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements.ts", () => ({
  useTeamRoutingPolicyQuery: () => ({ currentData: undefined, isError: false }),
  useAvailableModelProfilesQuery: () => ({ currentData: undefined, isError: false }),
}));
vi.mock("../../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ agentsNicknameSingular: "Agent" }),
}));
vi.mock("@shared/organisms/SettingsModal/SettingsModal.tsx", () => ({
  default: ({ isOpen, children, actions }: { isOpen: boolean; children: React.ReactNode; actions: React.ReactNode }) =>
    isOpen ? (
      <div>
        {children}
        <footer>{actions}</footer>
      </div>
    ) : null,
}));
vi.mock("./AgentFormBody.tsx", () => ({
  AgentFormBody: ({
    capabilityConfigValues,
    onCapabilityConfigChange,
    onCapabilityAssetFileChange,
  }: {
    capabilityConfigValues: Record<string, Record<string, unknown>>;
    onCapabilityConfigChange: (id: string, key: string, value: unknown) => void;
    onCapabilityAssetFileChange: (id: string, slot: string, file: File | null) => void;
  }) => (
    <div>
      <span data-testid="template-sha">{String(capabilityConfigValues.ppt_builder?.template_sha256)}</span>
      <button
        onClick={() => onCapabilityAssetFileChange("ppt_builder", "template", new File(["deck"], "replacement.pptx"))}
      >
        Stage
      </button>
      <button
        onClick={() => {
          onCapabilityAssetFileChange("ppt_builder", "template", null);
          onCapabilityConfigChange("ppt_builder", "template_sha256", null);
          onCapabilityConfigChange("ppt_builder", "template_key", null);
          onCapabilityConfigChange("ppt_builder", "overrides", []);
        }}
      >
        Use platform template
      </button>
    </div>
  ),
}));

import AgentFormModal, { type AgentFormPayload } from "./AgentFormModal";

const template = {
  template_id: "tpl",
  display_name: "Presenter",
  default_tuning_fields: [],
  available_capabilities: [{ id: "ppt_builder", config_fields: [] }],
} as unknown as AgentTemplateSummary;
const instance = {
  ...INSTANCE,
  agent_instance_id: "agent",
  space_id: "team",
  template_id: "tpl",
  display_name: "Presenter",
  role: "Presenter",
  usage_statement: "Team presentations",
  status: "enabled",
  selected_capability_ids: ["ppt_builder"],
  capability_config: {
    ppt_builder: {
      schema_version: "1",
      config: { template_sha256: "saved", template_key: "template:saved", overrides: [{ pattern_id: "slide:1" }] },
    },
  },
} as ManagedAgentInstanceSummary;

it("discards a pending template reset on close and submits it only after Save", async () => {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  const onClose = vi.fn();
  const onSubmit = vi.fn(async (_payload: AgentFormPayload) => undefined);
  const render = (isOpen: boolean) => {
    act(() =>
      root.render(
        <AgentFormModal
          isOpen={isOpen}
          isSubmitting={false}
          mode="edit"
          editInstance={instance}
          templates={[template]}
          onClose={onClose}
          onSubmit={onSubmit}
        />,
      ),
    );
  };
  const click = (label: string) => {
    const button = [...container.querySelectorAll("button")].find((item) => item.textContent === label);
    expect(button).toBeDefined();
    act(() => button?.click());
  };

  try {
    render(true);
    expect(container.querySelector('[data-testid="template-sha"]')?.textContent).toBe("saved");
    click("Use platform template");
    expect(container.querySelector('[data-testid="template-sha"]')?.textContent).toBe("null");
    click("rework.cancel");
    expect(onClose).toHaveBeenCalledOnce();
    expect(onSubmit).not.toHaveBeenCalled();

    render(false);
    render(true);
    expect(container.querySelector('[data-testid="template-sha"]')?.textContent).toBe("saved");
    click("Stage");
    click("Use platform template");
    await act(async () => click("rework.save"));
    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit.mock.calls[0][0].capabilityConfigValues.ppt_builder).toEqual({
      template_sha256: null,
      template_key: null,
      overrides: [],
    });
    expect(onSubmit.mock.calls[0][0].capabilityAssetFiles).toEqual({});
  } finally {
    act(() => root.unmount());
    container.remove();
  }
});
