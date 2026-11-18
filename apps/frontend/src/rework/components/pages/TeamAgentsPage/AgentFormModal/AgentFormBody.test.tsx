// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act, type ComponentProps } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { AgentFormBody } from "./AgentFormBody";
import { CAP_TABULAR } from "./toolPacks";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "fr" } }),
}));
vi.mock("react-redux", () => ({ useDispatch: () => vi.fn() }));
vi.mock("../../../../features/capabilities/configWidgetRegistry", () => ({ configWidgetFor: () => undefined }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePromptCatalogQuery: () => ({}),
  useListPromptCategoriesQuery: () => ({}),
  useLazyGetPromptQuery: () => [vi.fn(), {}],
}));
vi.mock("@shared/molecules/DocumentLibraryScopePicker/DocumentLibraryScopePicker", () => ({
  DocumentLibraryScopePicker: ({
    value,
    onChange,
    showDocuments,
  }: {
    value: { folderIds: string[] };
    onChange: (value: { folderIds: string[]; documentIds: string[] }) => void;
    showDocuments: boolean;
  }) => (
    <button
      data-testid="folders"
      data-documents={showDocuments}
      onClick={() => onChange({ folderIds: ["folder-a"], documentIds: [] })}
    >
      {value.folderIds.join(",")}
    </button>
  ),
}));

const bindingKey = "chat_options.libraries_binding";
const foldersKey = "chat_options.bound_library_ids";

it("edits and reopens the same tabular folder restriction in Simple and Advanced", () => {
  const container = document.createElement("div");
  let root = createRoot(container);
  let config: Record<string, unknown> = {};
  const props: Omit<ComponentProps<typeof AgentFormBody>, "capabilityConfigValues" | "onCapabilityConfigChange"> = {
    mode: "edit",
    templateId: "template",
    displayName: "Analyst",
    role: "",
    description: "",
    usageStatement: "",
    templates: [
      {
        template_id: "template",
        source_agent_id: "assistant",
        source_runtime_id: "pod",
        status: "available",
        display_name: "Assistant",
        description: "Assistant",
        category: "general",
        capabilities: [],
        default_capability_ids: [],
        default_tuning_fields: [],
        supports_hitl: false,
        supports_managed_mcp: true,
        tags: [],
        team_instantiable: true,
        supports_capabilities: true,
        available_capabilities: [
          {
            id: CAP_TABULAR,
            name: "Tabular",
            description: "CSV",
            config_fields: [
              { key: bindingKey, type: "boolean", title: "mcp.servers.tabular.libraryBinding.title", default: false },
              {
                key: foldersKey,
                type: "array",
                title: "Folders",
                default: [],
                ui: { widget: "document_libraries", visible_when: bindingKey },
              },
            ],
          },
        ],
      },
    ],
    tuningFieldValues: {},
    selectedCapabilityIds: [CAP_TABULAR],
    capabilityAssetFiles: {},
    isSubmitting: false,
    submitAttempted: false,
    activeSection: "tools",
    errorSections: new Set(),
    teamId: "space",
    recommendedModel: null,
    onRecommendedModelChange: vi.fn(),
    onSectionChange: vi.fn(),
    onDisplayNameChange: vi.fn(),
    onRoleChange: vi.fn(),
    onDescriptionChange: vi.fn(),
    onUsageStatementChange: vi.fn(),
    onTuningChange: vi.fn(),
    onCapabilitySelectionChange: vi.fn(),
    onCapabilitySelectionReplace: vi.fn(),
    onCapabilityAssetFileChange: vi.fn(),
    onCapabilityBlockingErrorChange: vi.fn(),
  };
  const render = () =>
    root.render(
      <MemoryRouter>
        <AgentFormBody
          {...props}
          capabilityConfigValues={{ [CAP_TABULAR]: config }}
          onCapabilityConfigChange={(id, key, value) => {
            expect(id).toBe(CAP_TABULAR);
            config = { ...config, [key]: value };
            render();
          }}
        />
      </MemoryRouter>,
    );
  const bindingToggle = () =>
    Array.from(container.querySelectorAll<HTMLInputElement>("input[type=checkbox]")).find((input) =>
      input.closest("label")?.parentElement?.textContent?.includes("mcp.servers.tabular.libraryBinding.title"),
    );
  act(render);
  expect(container.textContent).toContain("mcp.servers.tabular.libraryBinding.title");
  expect(container.querySelector('[data-testid="folders"]')).toBeNull();
  act(() => bindingToggle()?.click());
  expect(config[bindingKey]).toBe(true);
  act(() => container.querySelector<HTMLButtonElement>('[data-testid="folders"]')?.click());
  expect(config[foldersKey]).toEqual(["folder-a"]);
  expect(container.querySelector('[data-testid="folders"]')?.getAttribute("data-documents")).toBe("false");
  act(() => root.unmount());
  root = createRoot(container);
  act(render);
  expect(container.querySelector('[data-testid="folders"]')?.textContent).toBe("folder-a");
  act(() =>
    container
      .querySelector<HTMLInputElement>('input[aria-label="rework.teams.formAgent.capabilities.viewToggle.aria"]')
      ?.click(),
  );
  expect(container.querySelector('[data-testid="folders"]')?.textContent).toBe("folder-a");
  act(() => bindingToggle()?.click());
  expect(config[bindingKey]).toBe(false);
  expect(container.querySelector('[data-testid="folders"]')).toBeNull();
  expect(config[foldersKey]).toEqual(["folder-a"]);
  act(() => root.unmount());
});
