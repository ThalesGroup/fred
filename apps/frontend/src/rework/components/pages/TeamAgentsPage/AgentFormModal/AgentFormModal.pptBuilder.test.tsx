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

import { act, useContext } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import type {
  AgentTemplateSummary,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { PptBuilderUploadContext } from "../../../../features/capabilities/ppt_builder/PptBuilderUploadContext";

const { postDraftMock } = vi.hoisted(() => ({ postDraftMock: vi.fn() }));

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
vi.mock("../../../../../slices/controlPlane/controlPlaneOpenApi.ts", () => ({
  usePostTeamCapabilityPreparationDraftControlPlaneV1TeamsTeamIdCapabilityPreparationDraftsPostMutation: () => [
    (args: unknown) => ({ unwrap: () => postDraftMock(args) }),
  ],
  useDeleteTeamCapabilityPreparationDraftControlPlaneV1TeamsTeamIdCapabilityPreparationDraftsDraftIdDeleteMutation:
    () => [() => ({ unwrap: () => Promise.resolve() })],
  usePostTeamCapabilityPreparationDraftRetryControlPlaneV1TeamsTeamIdCapabilityPreparationDraftsDraftIdRetryPostMutation:
    () => [() => ({ unwrap: () => Promise.reject(new Error("offline")) })],
  useGetTeamCapabilityPreparationDraftControlPlaneV1TeamsTeamIdCapabilityPreparationDraftsDraftIdGetQuery: () => ({
    currentData: undefined,
  }),
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
vi.mock("./CreationAssistantDialog/CreationAssistantDialog.tsx", () => ({ CreationAssistantDialog: () => null }));
vi.mock("./TemplateBrowser/TemplateBrowser.tsx", () => ({
  TemplateBrowser: ({ onSelect }: { onSelect: (id: string) => void }) => (
    <button onClick={() => onSelect("runtime:template")}>Select template</button>
  ),
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
      <span data-testid="upload-phase">{useContext(PptBuilderUploadContext)?.phase ?? "none"}</span>
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
  agent_instance_id: "agent",
  team_id: "team",
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

it("uploads a selected template before Save and attaches its preparation on Save", async () => {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  const onSubmit = vi.fn(async (_payload: AgentFormPayload) => undefined);
  let finishUpload: ((value: unknown) => void) | undefined;
  postDraftMock.mockImplementation(
    () =>
      new Promise((resolve) => {
        finishUpload = resolve;
      }),
  );
  try {
    act(() =>
      root.render(
        <AgentFormModal
          isOpen
          isSubmitting={false}
          mode="edit"
          teamId="team"
          editInstance={instance}
          templates={[template]}
          onClose={() => undefined}
          onSubmit={onSubmit}
        />,
      ),
    );
    const button = (label: string) =>
      [...container.querySelectorAll("button")].find((item) => item.textContent === label);
    expect(postDraftMock).not.toHaveBeenCalled();
    act(() => button("Stage")?.click());
    expect(postDraftMock).toHaveBeenCalledOnce();
    const data = postDraftMock.mock.calls[0][0]
      .bodyPostTeamCapabilityPreparationDraftControlPlaneV1TeamsTeamIdCapabilityPreparationDraftsPost as FormData;
    expect(data.get("target_kind")).toBe("agent");
    expect(data.get("target_id")).toBe("agent");
    expect(container.querySelector('[data-testid="upload-phase"]')?.textContent).toBe("uploading");
    expect(button("rework.save")?.disabled).toBe(true);
    act(() => button("rework.save")?.click());
    expect(onSubmit).not.toHaveBeenCalled();
    await act(async () =>
      finishUpload?.({
        draft_id: "draft-id",
        expires_at: "2099-11-13T11:00:00Z",
        config: { template_sha256: "new-sha", use_vision: false },
        preparation: { state: "pending", summary: null },
      }),
    );
    expect(container.querySelector('[data-testid="upload-phase"]')?.textContent).toBe("pending");
    expect(button("rework.save")?.disabled).toBe(false);
    await act(async () => button("rework.save")?.click());
    expect(onSubmit.mock.calls[0][0].capabilityPreparationDrafts).toEqual({ ppt_builder: "draft-id" });
    expect(onSubmit.mock.calls[0][0].capabilityAssetFiles).toEqual({});
    expect(onSubmit.mock.calls[0][0].capabilityConfigValues.ppt_builder.template_sha256).toBe("new-sha");
  } finally {
    act(() => root.unmount());
    container.remove();
    postDraftMock.mockReset();
  }
});

it("starts upload during agent creation without creating the agent", () => {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  const onSubmit = vi.fn(async (_payload: AgentFormPayload) => undefined);
  postDraftMock.mockImplementation(() => new Promise(() => undefined));
  try {
    act(() =>
      root.render(
        <AgentFormModal
          isOpen
          isSubmitting={false}
          mode="create"
          teamId="team"
          templates={[{ ...template, template_id: "runtime:template" }]}
          onClose={() => undefined}
          onSubmit={onSubmit}
        />,
      ),
    );
    const click = (label: string) =>
      [...container.querySelectorAll("button")].find((item) => item.textContent === label)?.click();
    act(() => click("Select template"));
    act(() => click("Stage"));
    expect(postDraftMock).toHaveBeenCalledOnce();
    const data = postDraftMock.mock.calls[0][0]
      .bodyPostTeamCapabilityPreparationDraftControlPlaneV1TeamsTeamIdCapabilityPreparationDraftsPost as FormData;
    expect(data.get("target_kind")).toBe("template");
    expect(data.get("target_id")).toBe("runtime:template");
    expect(onSubmit).not.toHaveBeenCalled();
  } finally {
    act(() => root.unmount());
    container.remove();
    postDraftMock.mockReset();
  }
});

it("requires reselecting an expired temporary template before Save", async () => {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  const onSubmit = vi.fn(async (_payload: AgentFormPayload) => undefined);
  postDraftMock.mockResolvedValue({
    draft_id: "expired-draft",
    expires_at: "2000-01-01T00:00:00Z",
    config: { template_sha256: "new-sha", use_vision: false },
    preparation: { state: "succeeded", summary: "Analysed 4 layouts" },
  });
  try {
    act(() =>
      root.render(
        <AgentFormModal
          isOpen
          isSubmitting={false}
          mode="edit"
          teamId="team"
          editInstance={instance}
          templates={[template]}
          onClose={() => undefined}
          onSubmit={onSubmit}
        />,
      ),
    );
    const button = (label: string) =>
      [...container.querySelectorAll("button")].find((item) => item.textContent === label);
    await act(async () => button("Stage")?.click());
    expect(container.querySelector('[data-testid="upload-phase"]')?.textContent).toBe("failed");
    expect(button("rework.save")?.disabled).toBe(true);
    expect(onSubmit).not.toHaveBeenCalled();
  } finally {
    act(() => root.unmount());
    container.remove();
    postDraftMock.mockReset();
  }
});

it("keeps the transfer alive when the form closes and reopens", async () => {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  let finishUpload: ((value: unknown) => void) | undefined;
  postDraftMock.mockImplementation(
    () =>
      new Promise((resolve) => {
        finishUpload = resolve;
      }),
  );
  const render = (isOpen: boolean) =>
    act(() =>
      root.render(
        <AgentFormModal
          isOpen={isOpen}
          isSubmitting={false}
          mode="edit"
          teamId="team"
          editInstance={instance}
          templates={[template]}
          onClose={() => undefined}
          onSubmit={async () => undefined}
        />,
      ),
    );
  try {
    render(true);
    act(() => [...container.querySelectorAll("button")].find((item) => item.textContent === "Stage")?.click());
    expect(container.querySelector('[data-testid="upload-phase"]')?.textContent).toBe("uploading");
    render(false);
    await act(async () =>
      finishUpload?.({
        draft_id: "draft-id",
        expires_at: "2099-11-13T11:00:00Z",
        config: { template_sha256: "new-sha" },
        preparation: { state: "pending", summary: null },
      }),
    );
    render(true);
    expect(container.querySelector('[data-testid="upload-phase"]')?.textContent).toBe("pending");
    expect(postDraftMock).toHaveBeenCalledOnce();
  } finally {
    act(() => root.unmount());
    container.remove();
    postDraftMock.mockReset();
  }
});
