// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import type { ModelMetadata, VectorReindex } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { OrganizationModels } from "./OrganizationModels";

const transcriptionLabel = "Transcription audio (STT)";
const realtimeTranscriptionLabel = "Transcription en direct (STT)";
const descriptiveMetadata: Record<string, ModelMetadata> = {
  fim: { chat: false, provider_capabilities: { completion_fim: true, classification: false } },
  classifier: { chat: false, provider_capabilities: { classification: true } },
  images: { chat: false, vision: true },
  "mistral-ocr-latest": { chat: false },
  recorder: {
    chat: false,
    audio_transcription: true,
    provider_capabilities: { audio_transcription: true, audio_transcription_realtime: true },
  },
  "live-caption": {
    chat: false,
    audio_transcription: false,
    provider_capabilities: { audio_transcription: false, audio_transcription_realtime: true },
  },
  "audio-chat": { chat: true, provider_capabilities: { audio: true } },
};

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const h = vi.hoisted(() => ({
  title: null as null | { source_id: string; upstream_model_id: string },
  creationAssistant: null as null | { source_id: string; upstream_model_id: string },
  locked: false,
  secondCatalog: false,
  configured: false,
  declared: false,
  additionalUses: false,
  unverifiedAllowed: false,
  manualChat: false,
  reindex: null as VectorReindex | null,
  metadataRevision: 0,
  modelsDevUnavailable: false,
  modelsDevEnabled: true,
  snapshotRevision: 1,
  refreshSucceeded: false,
  refreshError: undefined as { status: number; data: { detail: string } } | undefined,
  dictationSupported: true,
  tokenLimits: null as null | {
    context_window_tokens: number;
    max_input_tokens: number;
    max_output_tokens: number;
  },
  access: vi.fn(),
  remove: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
  rebuild: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
  save: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
  saveMetadata: vi.fn(),
  error: vi.fn(),
  refetch: vi.fn(() => ({ unwrap: () => Promise.resolve({ sources: [] }) })),
  refresh: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { value?: string; count?: number; name?: string }) => {
      if (key.endsWith(".usages.audio_transcription")) return transcriptionLabel;
      if (key.endsWith(".usages.audio_transcription_realtime")) return realtimeTranscriptionLabel;
      const value = options?.value ?? options?.count ?? options?.name;
      return value === undefined ? key : `${key}: ${value}`;
    },
  }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: h.error, showSuccess: vi.fn() }),
}));
vi.mock("@shared/molecules/InlineDrawer/InlineDrawer.tsx", () => ({
  InlineDrawer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock("@shared/molecules/Select/Select.tsx", () => ({
  default: ({
    label,
    value,
    options,
    onChange,
    disabled,
  }: {
    label: string;
    value: string;
    disabled: boolean;
    onChange: (value: string) => void;
    options: {
      key: string;
      value: string;
      label: string;
      disabled?: boolean;
      tooltip?: string;
      icon?: { type: string };
    }[];
  }) => (
    <select aria-label={label} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={o.key} value={o.value} disabled={o.disabled} data-icon={o.icon?.type} title={o.tooltip}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useOrganizationModelsQuery: () => ({
    currentData: {
      policy: {
        revision: 4,
        permitted: [
          ...(h.unverifiedAllowed ? ["unclassified"] : []),
          "chat",
          "withdrawn",
          "embed",
          "ranker",
          ...(h.additionalUses ? ["recorder", "live-caption"] : []),
        ].map((upstream_model_id) => ({ source_id: "a", upstream_model_id })),
        default: null,
        fallback: null,
        title: h.title,
        creation_assistant: h.creationAssistant,
        embedding: h.locked ? { source_id: "a", upstream_model_id: "embed" } : null,
        embedding_locked: h.locked,
        vision: null,
        ...(h.dictationSupported ? { transcription: null } : {}),
      },
      sources: [
        {
          name: "Catalogue A",
          url: h.declared ? null : "https://models-a.invalid/v1/models",
          api_root: "https://models-a.invalid/v1",
          platform_terms_url: "https://models-a.invalid/terms",
          dialect: "openai",
          wire: "openai_chat",
          managed: !h.configured,
          models_dev_enabled: h.modelsDevEnabled,
          observation: {
            source_id: "a",
            enabled: true,
            state: "ok",
            source_revision: 1,
            snapshot_revision: h.snapshotRevision,
            error_code: h.modelsDevUnavailable ? "models_dev_unavailable" : null,
          },
          offers: [
            ...["chat", "withdrawn", "not-permitted", "embed", "ranker"],
            ...(h.additionalUses ? Object.keys(descriptiveMetadata) : []),
            ...(h.unverifiedAllowed ? ["unclassified"] : []),
          ].map((id) => ({
            source_id: "a",
            upstream_model_id: id,
            selectable: id !== "withdrawn",
            advertised: id !== "withdrawn",
            uses:
              id === "unclassified"
                ? {
                    unverified: !h.manualChat,
                    chat: true,
                    vision: true,
                    embedding: !h.manualChat,
                    transcription: !h.manualChat,
                  }
                : undefined,
            metadata_revision: h.metadataRevision,
            metadata_complements:
              id === "unclassified" ? { max_output_tokens: 2048, ...(h.manualChat ? { chat: true } : {}) } : {},
            metadata:
              (id === "ranker" ? { chat: false, embedding: false, rerank: true } : descriptiveMetadata[id]) ??
              (id === "embed"
                ? { chat: false, embedding: true }
                : id === "unclassified"
                  ? {
                      max_output_tokens: 2048,
                      ...(h.manualChat ? { chat: true, provenance: { chat: "manual" } } : {}),
                    }
                  : {
                      chat: true,
                      vision: id === "chat" ? null : false,
                      ...(id === "chat" ? h.tokenLimits : {}),
                      ...(id === "not-permitted" ? { display_name: "A named model" } : {}),
                    }),
          })),
        },
        ...(h.secondCatalog
          ? [
              {
                name: "Catalogue B",
                url: "https://models-b.invalid/v1/models",
                api_root: "https://models-b.invalid/v1",
                platform_terms_url: "https://models-b.invalid/terms",
                dialect: "openai_compatible",
                wire: "openai_chat",
                managed: true,
                observation: { source_id: "b", enabled: true, state: "ok", source_revision: 1, snapshot_revision: 1 },
                offers: [],
              },
            ]
          : []),
      ],
    },
    isFetching: false,
    isError: false,
    refetch: h.refetch,
  }),
  useDeleteModelCatalogMutation: () => [h.remove, { isLoading: false }],
  useCreateModelCatalogMutation: () => [vi.fn(), { isLoading: false }],
  useUpdateModelCatalogMutation: () => [vi.fn(), { isLoading: false }],
  useReplaceModelComplementsMutation: () => [h.saveMetadata, { isLoading: false }],
  useStartVectorReindexMutation: () => [h.rebuild, { isLoading: false }],
  useVectorReindexStatusQuery: () => ({ currentData: h.reindex, refetch: h.refetch }),
  useRefreshModelSourceMutation: () => [
    h.refresh,
    { isLoading: false, isSuccess: h.refreshSucceeded, error: h.refreshError },
  ],
  useReplaceOrganizationModelPolicyMutation: () => [h.save, { isLoading: false }],
  useModelAccessMatrixQuery: (args: unknown) => {
    h.access(args);
    return {
      currentData: {
        revision: 4,
        organization_permitted: true,
        personal: "default",
        personal_effective: true,
        teams: [],
        next_cursor: null,
      },
      isError: false,
      isFetching: false,
      refetch: h.refetch,
    };
  },
  useSetModelAccessMutation: () => [vi.fn(), { isLoading: false }],
}));
let root: Root;
let container: HTMLDivElement;
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  window.localStorage.clear();
  vi.clearAllMocks();
  h.title = null;
  h.creationAssistant = null;
  h.locked = false;
  h.secondCatalog = false;
  h.configured = false;
  h.declared = false;
  h.additionalUses = false;
  h.unverifiedAllowed = false;
  h.manualChat = false;
  h.reindex = null;
  h.metadataRevision = 0;
  h.modelsDevUnavailable = false;
  h.modelsDevEnabled = true;
  h.snapshotRevision = 1;
  h.refreshSucceeded = false;
  h.refreshError = undefined;
  h.dictationSupported = true;
  h.tokenLimits = null;
});
it("uses the server choices, restores the saved title choice and reports conflicts", async () => {
  container = document.createElement("div");
  document.body.append(container);
  container.className = "fred-ui";
  root = createRoot(container);
  const render = () => root.render(<OrganizationModels organizationId="org" />);
  await act(async () => render());
  await openDefaults();
  const title = () => container.querySelector<HTMLSelectElement>('select[aria-label$=".title"]')!;
  expect([...title().options].map((o) => o.text)).toEqual([
    "rework.admin.capabilities.organizationModels.defaults.answerModel",
    "Catalogue A / chat",
  ]);
  await act(async () => {
    title().selectedIndex = 1;
    title().dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(h.save).toHaveBeenCalledWith({
    organizationId: "org",
    replaceModelPolicy: expect.objectContaining({
      expected_revision: 4,
      title: { source_id: "a", upstream_model_id: "chat" },
    }),
  });
  h.title = { source_id: "a", upstream_model_id: "chat" };
  await act(async () => render());
  expect(title().selectedIndex).toBe(1);
  h.save.mockReturnValueOnce({ unwrap: () => Promise.reject({ status: 409, data: { detail: "Reload policy" } }) });
  await act(async () => {
    title().selectedIndex = 0;
    title().dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(h.error).toHaveBeenCalledWith(
    expect.objectContaining({ summary: "rework.admin.capabilities.organizationModels.saveError" }),
  );
});
it("offers each document choice only its aptitude and keeps the corpus model locked", async () => {
  container = document.createElement("div");
  document.body.append(container);
  container.className = "fred-ui";
  root = createRoot(container);
  const render = () => root.render(<OrganizationModels organizationId="org" />);
  await act(async () => render());
  await openDefaults();
  const select = (field: string) => container.querySelector<HTMLSelectElement>(`select[aria-label$=".${field}"]`)!;
  const labels = (field: string) => [...select(field).options].map((o) => o.text);
  const none = "rework.admin.capabilities.organizationModels.none";
  expect(labels("default")).toEqual([none, "Catalogue A / chat"]);
  expect(labels("embedding")).toEqual([none, "Catalogue A / embed"]);
  expect(labels("reranker")).toEqual([none, "Catalogue A / ranker"]);
  // Unknown image input is offered; a source-reported refusal is not.
  expect(labels("vision")).toEqual([none, "Catalogue A / chat"]);
  await act(async () => {
    select("embedding").selectedIndex = 1;
    select("embedding").dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(h.save).toHaveBeenCalledWith({
    organizationId: "org",
    replaceModelPolicy: expect.objectContaining({
      embedding: { source_id: "a", upstream_model_id: "embed" },
      vision: null,
      reranker: null,
    }),
  });
  await act(async () => {
    select("reranker").selectedIndex = 1;
    select("reranker").dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(h.save).toHaveBeenCalledWith({
    organizationId: "org",
    replaceModelPolicy: expect.objectContaining({ reranker: { source_id: "a", upstream_model_id: "ranker" } }),
  });
  h.locked = true;
  await act(async () => render());
  expect(select("embedding").disabled).toBe(true);
  expect(container.textContent).toContain("rework.admin.capabilities.organizationModels.embeddingLockedHint");
});

it("hides only the dismissed completed reindex after remounting", async () => {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  const render = (key = "initial") => root.render(<OrganizationModels key={key} organizationId="org" />);
  const progress = () => container.querySelector('[role="progressbar"]');
  const dismiss = () =>
    [...container.querySelectorAll<HTMLButtonElement>("button")].find((button) =>
      button.textContent?.endsWith("reindex.dismiss"),
    );
  const completed: VectorReindex = {
    id: "first-reindex",
    status: "succeeded",
    cleanup_pending: false,
    completed: 502,
    total: 502,
    created_at: "2026-11-20T13:39:47Z",
    embedding: { source_id: "a", upstream_model_id: "embed" },
  };

  h.reindex = { ...completed, cleanup_pending: true };
  await act(async () => render());
  expect(progress()).not.toBeNull();
  expect(dismiss()).toBeUndefined();

  h.reindex = completed;
  await act(async () => render());
  await act(async () => dismiss()!.click());
  expect(progress()).toBeNull();
  await act(async () => render("reloaded"));
  expect(progress()).toBeNull();

  h.reindex = { ...completed, id: "next-reindex", status: "running", completed: 1 };
  await act(async () => render("reloaded"));
  expect(progress()).not.toBeNull();
  expect(dismiss()).toBeUndefined();

  h.reindex = { ...completed, id: "next-reindex" };
  await act(async () => render("reloaded"));
  expect(dismiss()).toBeDefined();
});

it("saves and clears a dedicated model for agent design", async () => {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  const render = () => root.render(<OrganizationModels organizationId="org" />);
  await act(async () => render());
  await openDefaults();
  const choice = container.querySelector<HTMLSelectElement>('select[aria-label$=".creation_assistant"]')!;
  expect([...choice.options].map((option) => option.text)).toEqual([
    "rework.admin.capabilities.organizationModels.defaults.spaceModel",
    "Catalogue A / chat",
  ]);
  const select = async (index: number) =>
    act(async () => {
      choice.selectedIndex = index;
      choice.dispatchEvent(new Event("change", { bubbles: true }));
    });
  const assistant = { source_id: "a", upstream_model_id: "chat" };
  await select(1);
  expect(h.save).toHaveBeenLastCalledWith({
    organizationId: "org",
    replaceModelPolicy: expect.objectContaining({ creation_assistant: assistant, expected_revision: 4 }),
  });
  h.creationAssistant = assistant;
  await act(async () => render());
  expect(choice.selectedIndex).toBe(1);
  await select(0);
  expect(h.save).toHaveBeenLastCalledWith({
    organizationId: "org",
    replaceModelPolicy: expect.objectContaining({ creation_assistant: null }),
  });
});

it.each([
  ["catalogs.add", "url"],
  ["catalogs.addModel", "modelId"],
])("opens the %s form from the add menu", async (choice, field) => {
  container = document.createElement("div");
  container.className = "fred-ui";
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<OrganizationModels organizationId="org" />));
  const actions = [
    ...container.querySelectorAll<HTMLButtonElement>(
      'button[aria-label$="catalogs.manage"], button[aria-label$="catalogs.addSource"]',
    ),
  ];
  expect(actions.map((button) => button.getAttribute("aria-label")?.split(".").slice(-2).join("."))).toEqual([
    "catalogs.manage",
    "catalogs.addSource",
  ]);
  const plus = actions[1];
  await act(async () => plus.click());
  const options = [...document.body.querySelectorAll<HTMLElement>('[role="listbox"] [role="option"]')];
  expect(options.map((option) => option.textContent?.split(".").slice(-2).join("."))).toEqual([
    "catalogs.add",
    "catalogs.addModel",
  ]);
  await act(async () => options.find((option) => option.textContent?.endsWith(choice))!.click());
  const label = [...catalogDialog().querySelectorAll("label")].find((item) =>
    item.textContent?.endsWith(`catalogs.${field} *`),
  );
  expect(label?.control).toBeInstanceOf(HTMLInputElement);
});

it("switches catalogue tabs and exposes their URL and deletion impact", async () => {
  h.secondCatalog = true;
  h.locked = true;
  container = document.createElement("div");
  document.body.append(container);
  container.className = "fred-ui";
  root = createRoot(container);
  await act(async () => root.render(<OrganizationModels organizationId="org" />));
  expect(container.textContent).not.toContain("https://models-a.invalid/v1/models");
  expect(container.textContent).not.toContain("catalogs.lastRefresh");
  const tabs = container.querySelectorAll<HTMLButtonElement>('[role="tab"]');
  const terms = () =>
    [...container.querySelectorAll("a")].find((link) => link.textContent?.endsWith("catalogs.platformTerms"));
  expect(terms()?.getAttribute("href")).toBe("https://models-a.invalid/terms");
  expect(tabs).toHaveLength(2);
  await act(async () => tabs[1].click());
  expect(terms()?.getAttribute("href")).toBe("https://models-b.invalid/terms");
  expect(tabs[1].getAttribute("aria-selected")).toBe("true");
  expect(container.querySelector('[role="dialog"]')).toBeNull();
  await openCatalog();
  expect(catalogDialog().querySelector<HTMLInputElement>('input[type="url"]')?.value).toBe(
    "https://models-b.invalid/v1/models",
  );
  await act(async () => catalogButton("common.cancel").click());
  await act(async () => tabs[0].click());
  expect(container.querySelector('[role="dialog"]')).toBeNull();
  await openCatalog();
  await act(async () => catalogButton("catalogs.delete").click());
  expect(container.querySelector('[role="dialog"]')).toBeNull();
  const dialog = document.body.querySelector('[role="alertdialog"]')!;
  expect(dialog.textContent).toContain("catalogs.deleteWarning");
  expect(dialog.textContent).toContain("catalogs.deleteEmbeddingWarning");
  expect(h.remove).not.toHaveBeenCalled();
  const confirm = [...dialog.querySelectorAll<HTMLButtonElement>("button")].find((button) =>
    button.textContent?.endsWith("catalogs.delete"),
  )!;
  await act(async () => confirm.click());
  expect(h.remove).toHaveBeenCalledWith({ organizationId: "org", sourceId: "a" });
});

it("keeps a withdrawn saved choice visible but disabled", async () => {
  h.title = { source_id: "a", upstream_model_id: "withdrawn" };
  container = document.createElement("div");
  document.body.append(container);
  container.className = "fred-ui";
  root = createRoot(container);
  await act(async () => root.render(<OrganizationModels organizationId="org" />));
  await openDefaults();
  const selected = container.querySelector<HTMLSelectElement>('select[aria-label$=".title"]')!;
  expect(selected.selectedOptions[0].text).toBe("Catalogue A / withdrawn");
  expect(selected.selectedOptions[0].disabled).toBe(true);
});

it.each([false, true])(
  "explains why a YAML catalogue (%s) can be refreshed but cannot be edited or deleted",
  async (declared) => {
    h.configured = true;
    h.declared = declared;
    container = document.createElement("div");
    container.className = "fred-ui";
    document.body.append(container);
    root = createRoot(container);
    await act(async () => root.render(<OrganizationModels organizationId="org" />));
    expect(container.textContent).not.toContain("catalogs.configured");
    expect(container.textContent).not.toContain("catalogs.lastRefresh");
    expect(container.querySelector('button[aria-label$="catalogs.delete"]')).toBeNull();
    await act(async () => container.querySelector<HTMLButtonElement>('[role="tab"]')!.click());
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    await openCatalog();
    expect(catalogDialog().querySelector<HTMLInputElement>('input[type="url"]')?.value).toBe(
      declared
        ? "rework.admin.capabilities.organizationModels.catalogs.declaredInventory"
        : "https://models-a.invalid/v1/models",
    );
    expect(catalogDialog().querySelector('[role="note"]')?.textContent).toContain("catalogs.configuredHint");
    expect(catalogDialog().querySelector<HTMLInputElement>('input[type="password"]')?.readOnly).toBe(true);
    expect(catalogButton("catalogs.delete").disabled).toBe(true);
    expect(catalogButton("discovery.refresh").disabled).toBe(false);
    h.refresh.mockClear();
    await act(async () => catalogButton("discovery.refresh").click());
    expect(h.refresh).toHaveBeenCalledWith({ organizationId: "org", sourceId: "a" });
    expect(h.remove).not.toHaveBeenCalled();
  },
);

it("opens catalogue editing and groups the defaults button with the model filter", async () => {
  container = document.createElement("div");
  container.className = "fred-ui";
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<OrganizationModels organizationId="org" />));
  const defaults = [...container.querySelectorAll("button")].find((button) =>
    button.textContent?.endsWith("platformModelBindings.openButton"),
  )!;
  expect(defaults.parentElement?.querySelector('input[aria-label$="discovery.filter"]')).not.toBeNull();
  expect(defaults.parentElement?.parentElement?.querySelector('[role="tab"]')).not.toBeNull();
  await act(async () => container.querySelector<HTMLButtonElement>('[role="tab"]')!.click());
  expect(container.querySelector('[role="dialog"]')).toBeNull();
  await openCatalog();
  expect(catalogButton("catalogs.delete").disabled).toBe(false);
  expect(container.querySelector('[role="dialog"]')?.textContent).toContain("catalogs.edit");
  expect(container.querySelector<HTMLInputElement>('input[type="url"]')?.value).toBe(
    "https://models-a.invalid/v1/models",
  );
  expect(container.querySelectorAll('[role="dialog"]')).toHaveLength(1);
});

it("reads the saved catalogues and refreshes only the selected source on request", async () => {
  h.secondCatalog = true;
  container = document.createElement("div");
  container.className = "fred-ui";
  document.body.append(container);
  root = createRoot(container);
  const render = () => root.render(<OrganizationModels organizationId="org" />);
  await act(async () => render());
  expect(h.refresh).not.toHaveBeenCalled();
  const tab = [...container.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find(
    (button) => button.textContent === "Catalogue B",
  )!;
  await act(async () => tab.click());
  expect(container.querySelector('[role="dialog"]')).toBeNull();
  await openCatalog();
  expect(catalogDialog()).not.toBeNull();
  await act(async () => catalogButton("common.cancel").click());
  expect(container.querySelector('[role="dialog"]')).toBeNull();
  await act(async () => tab.click());
  expect(container.querySelector('[role="dialog"]')).toBeNull();
  await openCatalog();
  expect(h.refresh).not.toHaveBeenCalled();
  await act(async () => {
    catalogButton("discovery.refresh").click();
    h.refreshError = { status: 502, data: { detail: "Catalogue unreachable" } };
    render();
  });
  expect(h.refresh).toHaveBeenCalledExactlyOnceWith({ organizationId: "org", sourceId: "b" });
  expect(catalogDialog().querySelector('[role="alert"]')?.textContent).toContain("Catalogue unreachable");
  await act(async () => {
    catalogButton("discovery.refresh").click();
    h.refreshError = undefined;
    render();
  });
  expect(catalogDialog().querySelector('[role="alert"]')).toBeNull();
  expect(catalogDialog().querySelector('[role="status"]')?.textContent).toContain("catalogs.lastRefresh");
});

it("shows a new models.dev warning only in the catalogue editor after a manual refresh", async () => {
  h.modelsDevUnavailable = true;
  container = document.createElement("div");
  container.className = "fred-ui";
  document.body.append(container);
  root = createRoot(container);
  const render = () => root.render(<OrganizationModels organizationId="org" />);
  await act(async () => render());
  await openCatalog();
  expect(catalogDialog().textContent).not.toContain("catalogs.modelsDevUnavailable");
  await act(async () => {
    catalogButton("discovery.refresh").click();
    h.refreshSucceeded = true;
    render();
  });
  expect(catalogDialog().textContent).not.toContain("catalogs.modelsDevUnavailable");
  await act(async () => {
    h.snapshotRevision += 1;
    render();
  });
  expect(catalogDialog().textContent).toContain("catalogs.modelsDevUnavailable");
  expect(container.querySelector('[role="tabpanel"]')?.textContent).not.toContain("catalogs.modelsDevUnavailable");
  await act(async () => catalogButton("common.cancel").click());
  await openCatalog();
  expect(catalogDialog().textContent).not.toContain("catalogs.modelsDevUnavailable");
  expect(h.refresh).toHaveBeenCalledExactlyOnceWith({ organizationId: "org", sourceId: "a" });
});

it("describes declared uses and never guesses a purpose from the model name", async () => {
  h.additionalUses = true;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<OrganizationModels organizationId="org" />));
  const row = (id: string) => modelRows().find((row) => modelName(row) === id)!.textContent;
  expect(row("chat")).toContain("usages.chat");
  expect(row("embed")).toContain("usages.embedding");
  expect(row("fim")).toContain("usages.completion_fim");
  expect(row("fim")).not.toContain("usages.classification");
  expect(row("classifier")).toContain("usages.classification");
  expect(row("images")).toContain("usages.vision");
  expect(row("mistral-ocr-latest")).toContain("usages.unknown");
});

it.each([true, false])(
  "keeps offers authorizable when models.dev sync is unavailable or disabled (%s)",
  async (enabled) => {
    h.additionalUses = true;
    h.modelsDevUnavailable = true;
    h.modelsDevEnabled = enabled;
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    await act(async () => root.render(<OrganizationModels organizationId="org" />));
    expect(container.textContent).not.toContain("catalogs.modelsDevUnavailable");
    expect(h.refresh).not.toHaveBeenCalled();
    const row = modelRows().find((row) => modelName(row) === "mistral-ocr-latest")!;
    const authorization = row.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    expect(authorization.disabled).toBe(false);
    await act(async () => authorization.click());
    const dialog = () => document.querySelector<HTMLElement>('[role="alertdialog"]')!;
    const button = (key: string) =>
      [...dialog().querySelectorAll("button")].find((item) => item.textContent?.endsWith(key))!;
    expect(dialog().textContent).toContain("authorizeUnverifiedTitle");
    expect(dialog().textContent).toContain("mistral-ocr-latest");
    expect(h.save).not.toHaveBeenCalled();
    await act(async () => button("defaultOffConfirm.cancel").click());
    expect(dialog()).toBeNull();
    expect(h.save).not.toHaveBeenCalled();
    await act(async () => authorization.click());
    await act(async () => button("authorizeUnverifiedConfirm").click());
    expect(h.save).toHaveBeenCalledTimes(1);
    expect(h.save).toHaveBeenCalledWith({
      organizationId: "org",
      replaceModelPolicy: expect.objectContaining({
        permitted: expect.arrayContaining([{ source_id: "a", upstream_model_id: "mistral-ocr-latest" }]),
      }),
    });
  },
);

it("puts permitted unclassified models after reported uses with an information icon", async () => {
  h.unverifiedAllowed = true;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<OrganizationModels organizationId="org" />));
  await openDefaults();
  const primary = container.querySelector<HTMLSelectElement>('select[aria-label$=".fields.default"]')!;
  expect([...primary.options].slice(1).map((option) => option.text)).toEqual([
    "Catalogue A / chat",
    "Catalogue A / unclassified",
  ]);
  const option = primary.options[2];
  expect(option.disabled).toBe(false);
  expect(option.dataset.icon).toBe("info");
  expect(option.title).toContain("usages.unverifiedHint");
  await act(async () => {
    primary.value = option.value;
    primary.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(h.save).toHaveBeenCalledWith({
    organizationId: "org",
    replaceModelPolicy: expect.objectContaining({ default: { source_id: "a", upstream_model_id: "unclassified" } }),
  });
});

it("assigns a use from the table and removes it while preserving other complements", async () => {
  h.unverifiedAllowed = true;
  h.saveMetadata.mockImplementation(({ replaceModelComplements: { values } }) => ({
    unwrap: async () => {
      h.manualChat = values.chat === true;
      h.metadataRevision += 1;
      return values;
    },
  }));
  container = document.createElement("div");
  container.className = "fred-ui";
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<OrganizationModels organizationId="org" />));

  const usageCell = () => modelRows().find((row) => modelName(row) === "unclassified")!.children[2];
  const edit = () => usageCell().querySelector<HTMLButtonElement>('button[aria-label*="usages.editForModel"]')!;
  const checkbox = (field: string) => {
    const label = [...catalogDialog().querySelectorAll("label")].find((item) =>
      item.textContent?.endsWith(`usages.${field}`),
    )!;
    return label.control as HTMLInputElement;
  };
  expect(usageCell().textContent).toContain("usages.unknown");
  await act(async () => edit().click());
  expect(catalogDialog().textContent).toContain("usages.edit - unclassified");
  expect(catalogDialog().querySelectorAll('input[type="checkbox"]')).toHaveLength(4);
  expect(checkbox("vision").disabled).toBe(true);
  await act(async () => checkbox("chat").click());
  expect(checkbox("vision").disabled).toBe(false);
  expect(checkbox("embedding").disabled).toBe(true);
  await act(async () => catalogButton("common.save").click());
  expect(h.saveMetadata).toHaveBeenLastCalledWith({
    organizationId: "org",
    sourceId: "a",
    replaceModelComplements: {
      expected_revision: 0,
      upstream_model_id: "unclassified",
      values: { chat: true, max_output_tokens: 2048 },
    },
  });
  expect(usageCell().textContent).toContain("usages.chat");
  expect(usageCell().textContent).toContain("usages.manual");

  await act(async () => edit().click());
  expect(checkbox("chat").checked).toBe(true);
  await act(async () => checkbox("chat").click());
  await act(async () => catalogButton("common.save").click());
  expect(h.saveMetadata).toHaveBeenLastCalledWith({
    organizationId: "org",
    sourceId: "a",
    replaceModelComplements: {
      expected_revision: 1,
      upstream_model_id: "unclassified",
      values: { max_output_tokens: 2048 },
    },
  });
  expect(usageCell().textContent).toContain("usages.unknown");
  expect(usageCell().textContent).not.toContain("usages.manual");
});

it("labels file and live transcription separately and finds both by STT", async () => {
  h.additionalUses = true;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<OrganizationModels organizationId="org" />));
  const usage = (name: string) =>
    modelRows()
      .find((row) => modelName(row) === name)
      ?.children[2]?.querySelector("span")?.textContent;
  expect(usage("recorder")).toBe(transcriptionLabel);
  expect(usage("live-caption")).toBe(realtimeTranscriptionLabel);
  expect(usage("audio-chat")).toContain("usages.chat");
  expect(usage("audio-chat")).not.toContain(transcriptionLabel);

  const filter = container.querySelector<HTMLInputElement>('input[aria-label$="discovery.filter"]')!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(filter, "STT");
    filter.dispatchEvent(new Event("input", { bubbles: true }));
  });
  expect(modelRows().map(modelName)).toEqual(["recorder", "live-caption"]);
});

it("offers only file transcription models for dictation and saves the chosen model", async () => {
  h.additionalUses = true;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<OrganizationModels organizationId="org" />));
  await openDefaults();
  const dictation = container.querySelector<HTMLSelectElement>('select[aria-label$=".transcription"]')!;
  expect([...dictation.options].map((option) => option.text)).toEqual([
    "rework.admin.capabilities.organizationModels.defaults.dictationDisabled",
    "Catalogue A / recorder",
  ]);
  await act(async () => {
    dictation.selectedIndex = 1;
    dictation.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(h.save).toHaveBeenCalledWith({
    organizationId: "org",
    replaceModelPolicy: expect.objectContaining({
      expected_revision: 4,
      transcription: { source_id: "a", upstream_model_id: "recorder" },
    }),
  });
});

it("activates an ordinary model with the policy schema served by the running Control Plane", async () => {
  h.dictationSupported = false;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<OrganizationModels organizationId="org" />));
  const checkbox = modelRows()
    .find((row) => modelName(row) === "A named model")!
    .querySelector<HTMLInputElement>('input[type="checkbox"]')!;
  await act(async () => checkbox.click());
  expect(h.save).toHaveBeenCalledWith({
    organizationId: "org",
    replaceModelPolicy: expect.objectContaining({
      permitted: expect.arrayContaining([{ source_id: "a", upstream_model_id: "not-permitted" }]),
    }),
  });
  expect(h.save).not.toHaveBeenCalledWith({
    organizationId: "org",
    replaceModelPolicy: expect.objectContaining({ transcription: null }),
  });
});

it("opens team and personal-space access for the chosen model and keeps embedding organization-wide", async () => {
  container = document.createElement("div");
  container.className = "fred-ui";
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<OrganizationModels organizationId="org" />));
  const button = (model: string) =>
    [
      ...modelRows()
        .find((row) => modelName(row) === model)!
        .querySelectorAll<HTMLButtonElement>("button"),
    ].find((button) => button.textContent?.endsWith("access.manage"))!;
  expect(button("embed").disabled).toBe(true);
  await act(async () => button("chat").click());
  expect(h.access).toHaveBeenCalledWith(
    expect.objectContaining({ organizationId: "org", sourceId: "a", upstreamModelId: "chat" }),
  );
  expect(catalogDialog().textContent).toContain("access.personal");
});

it("shows the model name once and keeps properties and access in separate columns", async () => {
  container = document.createElement("div");
  container.className = "fred-ui";
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<OrganizationModels organizationId="org" />));
  const headers = [...container.querySelectorAll('[class*="datatable-header"] [class*="header-content"]')].map(
    (element) => element.textContent,
  );
  expect(headers).toEqual([
    "rework.admin.capabilities.organizationModels.permitted",
    "rework.admin.capabilities.col.capability",
    "rework.admin.capabilities.organizationModels.usages.label",
    "rework.admin.capabilities.organizationModels.metadata.details",
    "rework.admin.capabilities.organizationModels.access.manage",
  ]);
  const cells = modelRows()[0].children;
  expect(cells[1].textContent).toBe("chat");
  expect(cells[3].querySelectorAll("button")).toHaveLength(1);
  expect(cells[3].textContent).toContain("metadata.details");
  expect(cells[4].querySelectorAll("button")).toHaveLength(1);
  expect(cells[4].textContent).toContain("access.manage");
  await act(async () => cells[3].querySelector<HTMLButtonElement>("button")!.click());
  expect(catalogDialog().querySelector('a[href="https://models-a.invalid/terms"]')?.textContent).toMatch(
    /catalogs\.platformTermsBadge$/,
  );
});

it.each([
  ["organizationModels.permitted", ["A named model", "chat", "embed", "ranker"]],
  ["col.capability", ["A named model", "chat", "embed", "ranker"]],
  ["organizationModels.usages.label", ["chat", "A named model", "embed", "ranker"]],
])("sorts %s in both directions and restores catalogue order on the third click", async (suffix, ascending) => {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<OrganizationModels organizationId="org" />));
  const header = [...container.querySelectorAll<HTMLButtonElement>('[class*="datatable-header"] button')].find(
    (button) => button.textContent?.includes(`rework.admin.capabilities.${suffix}`),
  )!;
  const order = () => modelRows().map(modelName);
  const original = order();
  await act(async () => header.click());
  expect(order()).toEqual(ascending);
  await act(async () => header.click());
  expect(order()).toEqual([...ascending].reverse());
  await act(async () => header.click());
  expect(order()).toEqual(original);
  expect(h.save).not.toHaveBeenCalled();
});

it.each([
  [1048576, "1M"],
  [131072, "131K"],
  [1000, "1K"],
  [999, "999"],
  [999999, "1M"],
])("groups compact token limits (%s -> %s) and exposes exact counts in the tooltip", async (count, compact) => {
  h.tokenLimits = { context_window_tokens: count, max_input_tokens: 922000, max_output_tokens: 128000 };
  container = document.createElement("div");
  container.className = "fred-ui";
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<OrganizationModels organizationId="org" />));
  const chips = modelRows()[0].querySelectorAll<HTMLElement>('[class*="modelSpecChip"]');
  expect(chips).toHaveLength(1);
  expect(chips[0].textContent).toContain(`modelSpecs.context: ${compact}`);
  expect(chips[0].textContent).toContain("modelSpecs.input: 922K");
  expect(chips[0].textContent).toContain("modelSpecs.output: 128K");
  expect(chips[0].textContent?.match(/modelSpecs\.tokens/g)).toHaveLength(1);
  await act(async () => chips[0].dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
  const tooltip = document.body.querySelector('[role="tooltip"]')!;
  expect(tooltip.textContent).toContain(`context_window_tokens: ${count}`);
  expect(tooltip.textContent).toContain("max_input_tokens: 922000");
  expect(tooltip.textContent).toContain("max_output_tokens: 128000");
});

function modelRows() {
  return [...container.querySelectorAll<HTMLElement>('[role="tabpanel"] [class*="datatable-row"]')];
}

function modelName(row: HTMLElement) {
  return row.children[1].querySelector("span")!.textContent;
}

async function openDefaults() {
  const button = [...container.querySelectorAll<HTMLButtonElement>("button")].find((button) =>
    button.textContent?.endsWith("platformModelBindings.openButton"),
  )!;
  await act(async () => button.click());
}

function catalogDialog() {
  return container.querySelector<HTMLDivElement>('[role="dialog"]')!;
}

async function openCatalog() {
  await act(async () => container.querySelector<HTMLButtonElement>('button[aria-label$="catalogs.manage"]')!.click());
}

function catalogButton(suffix: string) {
  return [...catalogDialog().querySelectorAll<HTMLButtonElement>("button")].find((button) =>
    (button.getAttribute("aria-label") ?? button.textContent)?.endsWith(suffix),
  )!;
}
