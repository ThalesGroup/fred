// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act, type ReactNode, type InputHTMLAttributes } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { ModelCatalogForm } from "./ModelCatalogForm";
import { ModelMetadataDialog } from "./ModelMetadataDialog";
import type {
  ModelInventory,
  ModelMetadata,
  StoredModelOffer,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const h = vi.hoisted(() => ({
  create: vi.fn(() => ({ unwrap: () => Promise.resolve("new-source") })),
  update: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
  metadata: vi.fn(() => ({ unwrap: () => Promise.resolve<ModelMetadata>({}) })),
  refresh: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: vi.fn() }) }));
vi.mock("@shared/atoms/TextInput/TextInput", () => ({
  default: ({
    label,
    explanation: _explanation,
    compact: _compact,
    size: _size,
    icon,
    showCharacterCount: _showCharacterCount,
    ...props
  }: Omit<InputHTMLAttributes<HTMLInputElement>, "size"> & {
    label?: string;
    explanation?: string;
    compact?: boolean;
    size?: string;
    icon?: { type: string };
    showCharacterCount?: boolean;
  }) => (
    <label>
      {label}
      <input aria-label={label} data-icon={icon?.type} {...props} />
    </label>
  ),
}));
vi.mock("@shared/molecules/Select/Select", () => ({
  default: ({
    label,
    ariaLabel,
    value,
    options,
    onChange,
    disabled,
  }: {
    label?: string;
    ariaLabel?: string;
    value: string;
    options: { value: string; label: string }[];
    onChange: (value: string) => void;
    disabled?: boolean;
  }) => (
    <select
      aria-label={ariaLabel ?? label}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useCreateModelCatalogMutation: () => [h.create, { isLoading: false }],
  useUpdateModelCatalogMutation: () => [h.update, { isLoading: false }],
  useReplaceModelComplementsMutation: () => [h.metadata, { isLoading: false }],
  useRefreshModelSourceMutation: () => [h.refresh, { isLoading: false }],
}));
let root: Root;
let host: HTMLDivElement;
const render = async (node: ReactNode) => {
  host = document.createElement("div");
  host.className = "fred-ui";
  document.body.append(host);
  root = createRoot(host);
  await act(async () => root.render(node));
};
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.clearAllMocks();
});
async function input(suffix: string, value: string) {
  const element = host.querySelector<HTMLInputElement>(`input[aria-label$=".${suffix}"]`)!;
  await changeInput(element, value);
}

async function changeInput(element: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(element, value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function metadataValue(field: string) {
  return host.querySelector<HTMLInputElement | HTMLSelectElement>(
    `[aria-label*="fields.${field} -"][aria-label$=".value"]`,
  )!;
}

async function selectMetadata(field: string, value: string) {
  const select = metadataValue(field) as HTMLSelectElement;
  await act(async () => {
    select.value = value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

it("registers a write-only token, visible catalogue identity and explicit inference root", async () => {
  const created = vi.fn();
  await render(<ModelCatalogForm organizationId="org" onCreated={created} onClose={() => {}} />);
  const save = [...host.querySelectorAll<HTMLButtonElement>("button")].find(
    (button) => button.textContent === "common.save",
  )!;
  expect(save.disabled).toBe(true);
  await input("name", "My provider");
  await input("url", "https://models.invalid/v1/models");
  await input("apiRoot", "https://inference.invalid/v1");
  expect(host.querySelector('input[aria-label$=".platformTermsUrl"]')).toBeNull();
  await input("token", "synthetic-token");
  await input("metadataProvider", "example-registry-id");
  expect(host.querySelector<HTMLInputElement>('input[type="password"]')!.value).toBe("synthetic-token");
  await act(async () => save.click());
  expect(h.create).toHaveBeenCalledWith({
    organizationId: "org",
    createModelCatalog: {
      name: "My provider",
      url: "https://models.invalid/v1/models",
      api_root: "https://inference.invalid/v1",
      token: "synthetic-token",
      dialect: "openai_compatible",
      wire: "openai_chat",
      metadata_provider: "example-registry-id",
    },
  });
  expect(h.refresh).toHaveBeenCalledWith({ organizationId: "org", sourceId: "new-source" });
  expect(created).toHaveBeenCalledWith("new-source");
});

it("registers a single model without a catalogue URL", async () => {
  await render(<ModelCatalogForm organizationId="org" singleModel onCreated={() => {}} onClose={() => {}} />);
  expect(host.querySelector('input[aria-label$=".url"]')).toBeNull();
  const save = [...host.querySelectorAll<HTMLButtonElement>("button")].find(
    (button) => button.textContent === "common.save",
  )!;
  await input("name", "Test provider");
  await input("apiRoot", "https://inference.invalid/v1");
  await input("token", "synthetic-token");
  expect(save.disabled).toBe(true);
  await input("modelId", "test/embeddings");
  const usage = host.querySelector<HTMLSelectElement>('select[aria-label$=".modelUse"]')!;
  await act(async () => {
    usage.value = "embedding";
    usage.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await act(async () => save.click());
  expect(h.create).toHaveBeenCalledExactlyOnceWith({
    organizationId: "org",
    createModelCatalog: {
      name: "Test provider",
      model: { id: "test/embeddings", usage: "embedding" },
      api_root: "https://inference.invalid/v1",
      token: "synthetic-token",
      dialect: "openai_compatible",
      wire: "openai_chat",
    },
  });
  expect(h.refresh).toHaveBeenCalledExactlyOnceWith({ organizationId: "org", sourceId: "new-source" });
});

it.each(["", "synthetic-replacement"])(
  "saves with the original revision and refreshes on token rotation (%j)",
  async (token) => {
    const source = {
      name: "Old",
      url: "https://models.invalid/models",
      api_root: "https://inference.invalid/v1",
      dialect: "openai",
      wire: "openai_responses",
      managed: true,
      observation: { source_id: "s", source_revision: 8 },
    } as ModelInventory;
    await render(<ModelCatalogForm organizationId="org" source={source} onCreated={() => {}} onClose={() => {}} />);
    expect(host.querySelector<HTMLInputElement>('input[type="password"]')!.value).toBe("");
    for (const [field, value] of [
      ["url", source.url],
      ["apiRoot", source.api_root],
      ["dialect", "OpenAI"],
      ["wire", "Responses"],
    ]) {
      const control = host.querySelector<HTMLInputElement>(`input[aria-label$=".${field}"]`);
      expect(control?.value).toBe(value);
      expect(control?.readOnly).toBe(true);
      expect(control?.disabled).toBe(false);
      expect(control?.dataset.icon).toBe("lock");
    }
    await input("name", "Renamed");
    if (token) await input("token", token);
    await act(async () =>
      root.render(
        <ModelCatalogForm
          organizationId="org"
          source={{ ...source, name: "Changed elsewhere", observation: { ...source.observation, source_revision: 9 } }}
          onCreated={() => {}}
          onClose={() => {}}
        />,
      ),
    );
    await act(async () =>
      [...host.querySelectorAll<HTMLButtonElement>("button")]
        .find((button) => button.textContent === "common.save")!
        .click(),
    );
    expect(h.update).toHaveBeenCalledWith({
      organizationId: "org",
      sourceId: "s",
      updateModelCatalog: { name: "Renamed", expected_revision: 8, token: token || undefined },
    });
    if (token) expect(h.refresh).toHaveBeenCalledExactlyOnceWith({ organizationId: "org", sourceId: "s" });
    else expect(h.refresh).not.toHaveBeenCalled();
  },
);

it("clears a saved registry ID without offering a platform terms field", async () => {
  const source = {
    name: "Example gateway",
    metadata_provider: "example-registry-id",
    platform_terms_url: "https://example.org/terms",
    managed: true,
    observation: { source_id: "s", source_revision: 8 },
  } as ModelInventory;
  await render(<ModelCatalogForm organizationId="org" source={source} onCreated={() => {}} onClose={() => {}} />);
  const field = host.querySelector<HTMLInputElement>('input[aria-label$=".metadataProvider"]')!;
  expect(field.value).toBe("example-registry-id");
  await changeInput(field, "");
  const save = [...host.querySelectorAll<HTMLButtonElement>("button")].find(
    (button) => button.textContent === "common.save",
  )!;
  expect(host.querySelector('input[aria-label$=".platformTermsUrl"]')).toBeNull();
  expect(host.querySelector('input[value="https://example.org/terms"]')).toBeNull();
  await act(async () => save.click());
  expect(h.update).toHaveBeenCalledWith({
    organizationId: "org",
    sourceId: "s",
    updateModelCatalog: {
      name: "Example gateway",
      expected_revision: 8,
      token: undefined,
      metadata_provider: null,
    },
  });
  expect(h.refresh).not.toHaveBeenCalled();
});

it.each(["create", "edit"] as const)("can turn off models.dev in %s mode", async (mode) => {
  const source =
    mode === "edit"
      ? ({
          name: "Test",
          managed: true,
          models_dev_enabled: true,
          observation: { source_id: "s", source_revision: 8 },
        } as ModelInventory)
      : undefined;
  await render(<ModelCatalogForm organizationId="org" source={source} onCreated={() => {}} onClose={() => {}} />);
  if (!source) {
    await input("name", "Test");
    await input("url", "https://models.invalid/v1/models");
    await input("apiRoot", "https://models.invalid/v1");
    await input("token", "synthetic-token");
  }
  const sync = host.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
  expect(sync.checked).toBe(true);
  await act(async () => sync.click());
  expect(host.querySelector<HTMLInputElement>('input[aria-label$=".metadataProvider"]')?.disabled).toBe(true);
  await act(async () =>
    [...host.querySelectorAll<HTMLButtonElement>("button")]
      .find((button) => button.textContent === "common.save")!
      .click(),
  );
  const mutation = source ? h.update : h.create;
  expect(mutation).toHaveBeenCalledWith(
    expect.objectContaining({
      [source ? "updateModelCatalog" : "createModelCatalog"]: expect.objectContaining({ models_dev_enabled: false }),
    }),
  );
  if (source) expect(h.refresh).not.toHaveBeenCalled();
  else expect(h.refresh).toHaveBeenCalledExactlyOnceWith({ organizationId: "org", sourceId: "new-source" });
});

it("places the read-only provider name and editable platform name first", async () => {
  const detected: ModelMetadata = { display_name: "Provider name", provenance: { display_name: "provider" } };
  const offer: StoredModelOffer = {
    source_id: "s",
    upstream_model_id: "provider/model",
    advertised: true,
    selectable: true,
    first_seen_at: "2026-01-01",
    last_seen_at: "2026-01-01",
    metadata: detected,
    detected_metadata: detected,
    metadata_complements: {},
    metadata_revision: 4,
  };
  await render(<ModelMetadataDialog organizationId="org" offer={offer} onClose={() => {}} />);
  const [providerName, platformName] = host.querySelectorAll<HTMLInputElement>("input, select");
  const providerLabel = providerName.labels?.[0];
  expect(providerLabel?.textContent).toContain("metadata.providerName");
  expect(providerLabel?.closest("div")?.textContent).toContain("metadata.origins.provider");
  expect(providerName.value).toBe("Provider name");
  expect(providerName.readOnly).toBe(true);
  expect(providerName.dataset.icon).toBeUndefined();
  expect(platformName).toBe(metadataValue("display_name"));
  expect(platformName.value).toBe("Provider name");
  expect(platformName.disabled || platformName.readOnly).toBe(false);
  expect(host.textContent).toContain("metadata.origins.platform");
  expect(host.textContent?.match(/metadata\.origins\.provider/g)).toHaveLength(1);
  await changeInput(platformName, "Weaver name");
  expect(providerName.value).toBe("Provider name");
  const save = [...host.querySelectorAll<HTMLButtonElement>("button")].find(
    (button) => button.textContent === "common.save",
  )!;
  await act(async () => save.click());
  expect(h.metadata).toHaveBeenCalledExactlyOnceWith({
    organizationId: "org",
    sourceId: "s",
    replaceModelComplements: {
      expected_revision: 4,
      upstream_model_id: "provider/model",
      values: { display_name: "Weaver name" },
    },
  });
});

it("resets persisted complements in place and saves subsequent edits against the new revision", async () => {
  const offer: StoredModelOffer = {
    source_id: "s",
    upstream_model_id: "model",
    advertised: true,
    selectable: true,
    first_seen_at: "2026-01-01",
    last_seen_at: "2026-01-01",
    metadata: { chat: true, max_output_tokens: 100, display_name: "Custom name" },
    detected_metadata: {
      chat: true,
      max_output_tokens: 100,
      provenance: { chat: "provider", max_output_tokens: "provider" },
    },
    metadata_complements: { vision: null, display_name: "Custom name" },
    metadata_revision: 4,
  };
  const onClose = vi.fn();
  await render(<ModelMetadataDialog organizationId="org" offer={offer} onClose={onClose} />);
  const dialog = host.querySelector('[role="dialog"]')!;
  expect(dialog.getAttribute("aria-modal")).toBe("true");
  expect(dialog.textContent).toContain("metadata.details - Custom name");
  expect(host.querySelector<HTMLInputElement>('input[aria-label*="fields.max_output_tokens"]')?.value).toBe("100");
  expect(host.querySelector<HTMLInputElement>('input[aria-label*="fields.max_output_tokens"]')?.disabled).toBe(true);
  expect(metadataValue("chat").disabled).toBe(true);
  expect(metadataValue("embedding").disabled).toBe(true);
  expect(metadataValue("vision").value).toBe("");
  h.metadata.mockReturnValueOnce({
    unwrap: () => Promise.resolve({ ...offer.detected_metadata, vision: true }),
  });
  const reset = [...host.querySelectorAll<HTMLButtonElement>("button")].find((button) =>
    button.textContent?.endsWith(".reset"),
  )!;
  await act(async () => reset.click());
  expect(h.metadata).toHaveBeenCalledWith({
    organizationId: "org",
    sourceId: "s",
    replaceModelComplements: { expected_revision: 4, upstream_model_id: "model", values: {} },
  });
  expect(onClose).not.toHaveBeenCalled();
  expect(host.querySelector('[role="dialog"]')).toBe(dialog);
  expect(dialog.textContent).toContain("metadata.details - model");
  expect(metadataValue("vision").value).toBe("true");
  expect(metadataValue("display_name").value).toBe("model");
  await selectMetadata("vision", "");
  await selectMetadata("tool_calling", "true");
  const save = [...host.querySelectorAll<HTMLButtonElement>("button")].find(
    (button) => button.textContent === "common.save",
  )!;
  await act(async () => save.click());
  expect(h.metadata).toHaveBeenLastCalledWith({
    organizationId: "org",
    sourceId: "s",
    replaceModelComplements: {
      expected_revision: 5,
      upstream_model_id: "model",
      values: { vision: null, tool_calling: true },
    },
  });
  expect(onClose).toHaveBeenCalledOnce();
});

it("closes the properties dialog from the header button", async () => {
  const offer: StoredModelOffer = {
    source_id: "s",
    upstream_model_id: "model",
    advertised: true,
    selectable: true,
    first_seen_at: "2026-01-01",
    last_seen_at: "2026-01-01",
    metadata: {},
    detected_metadata: {},
    metadata_complements: {},
    metadata_revision: 0,
  };
  const onClose = vi.fn();
  await render(<ModelMetadataDialog organizationId="org" offer={offer} onClose={onClose} />);
  const title = host.querySelector('[role="dialog"]')!.getAttribute("aria-labelledby");
  const close = document
    .getElementById(title!)!
    .parentElement!.querySelector<HTMLButtonElement>('button[aria-label="common.close"]')!;
  await act(async () => close.click());
  expect(onClose).toHaveBeenCalledOnce();
});

it("shows the model license and platform terms next to the properties title", async () => {
  const license = { name: "MIT", url: "https://example.org/mit" };
  const metadata = { license, provenance: { license: "models_dev" } };
  const platformTermsUrl = "https://example.org/terms";
  const offer: StoredModelOffer = {
    source_id: "s",
    upstream_model_id: "model",
    advertised: true,
    selectable: true,
    first_seen_at: "2026-01-01",
    last_seen_at: "2026-01-01",
    metadata,
    detected_metadata: metadata,
    metadata_complements: {},
    metadata_revision: 0,
  };
  await render(
    <ModelMetadataDialog organizationId="org" offer={offer} platformTermsUrl={platformTermsUrl} onClose={() => {}} />,
  );
  const titleId = host.querySelector('[role="dialog"]')!.getAttribute("aria-labelledby")!;
  const header = document.getElementById(titleId)!.parentElement!;
  const modelLink = header.querySelector(`a[href="${license.url}"]`);
  expect(modelLink?.textContent).toBe("MIT");
  expect(modelLink?.getAttribute("aria-label")).toContain("metadata.origins.models_dev");
  expect(header.querySelector(`a[href="${platformTermsUrl}"]`)?.textContent).toMatch(/catalogs\.platformTermsBadge$/);
  expect(host.querySelectorAll('input[type="url"]')).toHaveLength(0);
});

it("displays the detected name-only license and preserves stored complements", async () => {
  const license = { name: "Apache-2.0" };
  const offer: StoredModelOffer = {
    source_id: "s",
    upstream_model_id: "model",
    advertised: true,
    selectable: true,
    first_seen_at: "2026-01-01",
    last_seen_at: "2026-01-01",
    metadata: { license: { name: "User input" }, provenance: { license: "manual" } },
    detected_metadata: { license, provenance: { license: "models_dev" } },
    metadata_complements: { license: { name: "User input" } },
    metadata_revision: 0,
  };
  await render(<ModelMetadataDialog organizationId="org" offer={offer} onClose={() => {}} />);
  const titleId = host.querySelector('[role="dialog"]')!.getAttribute("aria-labelledby")!;
  const header = document.getElementById(titleId)!.parentElement!;
  expect(header.textContent).toContain("Apache-2.0");
  expect(header.textContent).not.toContain("User input");
  expect(header.querySelector("a")).toBeNull();
  await selectMetadata("chat", "true");
  const save = [...host.querySelectorAll<HTMLButtonElement>("button")].find(
    (button) => button.textContent === "common.save",
  )!;
  await act(async () => save.click());
  expect(h.metadata).toHaveBeenCalledWith({
    organizationId: "org",
    sourceId: "s",
    replaceModelComplements: {
      expected_revision: 0,
      upstream_model_id: "model",
      values: { license: { name: "User input" }, chat: true },
    },
  });
});

it("shows automatic and saved manual values in their fields and restores detection when the override is cleared", async () => {
  const offer: StoredModelOffer = {
    source_id: "s",
    upstream_model_id: "gpt-6.1-sol",
    advertised: true,
    selectable: true,
    first_seen_at: "2026-01-01",
    last_seen_at: "2026-01-01",
    metadata: { context_window_tokens: 64000, reasoning: false, vision: false },
    detected_metadata: {
      context_window_tokens: 1050000,
      reasoning: true,
      vision: false,
      reasoning_efforts: ["low", "medium", "high", "xhigh", "max"],
      provenance: { context_window_tokens: "models_dev", reasoning: "models_dev", vision: "provider" },
    },
    metadata_complements: { context_window_tokens: 64000, reasoning: false },
    metadata_revision: 7,
  };
  await render(<ModelMetadataDialog organizationId="org" offer={offer} onClose={() => {}} />);
  const value = metadataValue;
  expect(value("context_window_tokens")?.value).toBe("64000");
  expect(value("reasoning")?.value).toBe("false");
  expect(value("vision")?.value).toBe("false");
  expect(value("vision")?.disabled).toBe(true);
  expect(value("reasoning_efforts")?.value).toBe("low, medium, high, xhigh, max");
  expect(value("reasoning_efforts")?.disabled).toBe(false);
  const reset = host.querySelector<HTMLButtonElement>(
    'button[aria-label*="fields.context_window_tokens -"][aria-label$=".resetField"]',
  )!;
  await act(async () => reset.click());
  expect(value("context_window_tokens")?.value).toBe("1050000");
  expect(value("context_window_tokens")?.disabled).toBe(false);
  expect(
    host.querySelector('button[aria-label*="fields.context_window_tokens -"][aria-label$=".resetField"]'),
  ).toBeNull();
  const save = [...host.querySelectorAll<HTMLButtonElement>("button")].find(
    (button) => button.textContent === "common.save",
  )!;
  await act(async () => save.click());
  expect(h.metadata).toHaveBeenCalledWith({
    organizationId: "org",
    sourceId: "s",
    replaceModelComplements: { expected_revision: 7, upstream_model_id: "gpt-6.1-sol", values: { reasoning: false } },
  });
});

it("edits a single control per property, validates numeric limits and persists cleared values as unknown", async () => {
  const offer: StoredModelOffer = {
    source_id: "s",
    upstream_model_id: "model",
    advertised: true,
    selectable: true,
    first_seen_at: "2026-01-01",
    last_seen_at: "2026-01-01",
    metadata: { context_window_tokens: 64000, tool_calling: true },
    detected_metadata: {
      context_window_tokens: 64000,
      tool_calling: true,
      provenance: { context_window_tokens: "models_dev", tool_calling: "models_dev" },
    },
    metadata_complements: {},
    metadata_revision: 2,
  };
  await render(<ModelMetadataDialog organizationId="org" offer={offer} onClose={() => {}} />);
  expect(host.querySelectorAll('[aria-label$=".value"]')).toHaveLength(16);
  expect(host.textContent).not.toContain("metadata.fields.license");
  expect(host.textContent).not.toContain("catalogs.platformTermsBadge");
  expect(host.querySelector('[aria-label$=".mode"]')).toBeNull();
  const save = [...host.querySelectorAll<HTMLButtonElement>("button")].find(
    (button) => button.textContent === "common.save",
  )!;
  await changeInput(metadataValue("context_window_tokens") as HTMLInputElement, "-1");
  expect(save.disabled).toBe(true);
  await changeInput(metadataValue("context_window_tokens") as HTMLInputElement, "");
  expect(save.disabled).toBe(false);
  await selectMetadata("tool_calling", "false");
  await selectMetadata("audio_transcription", "true");
  await selectMetadata("reasoning_transport", "responses");
  await changeInput(metadataValue("reasoning_efforts") as HTMLInputElement, "low, high");
  await changeInput(metadataValue("display_name") as HTMLInputElement, "My model");
  await act(async () => save.click());
  expect(h.metadata).toHaveBeenLastCalledWith({
    organizationId: "org",
    sourceId: "s",
    replaceModelComplements: {
      expected_revision: 2,
      upstream_model_id: "model",
      values: {
        context_window_tokens: null,
        tool_calling: false,
        audio_transcription: true,
        reasoning_transport: "responses",
        reasoning_efforts: ["low", "high"],
        display_name: "My model",
      },
    },
  });
  await selectMetadata("tool_calling", "");
  await selectMetadata("audio_transcription", "");
  await selectMetadata("reasoning_transport", "");
  await changeInput(metadataValue("reasoning_efforts") as HTMLInputElement, "");
  await changeInput(metadataValue("display_name") as HTMLInputElement, "");
  await act(async () => save.click());
  expect(h.metadata).toHaveBeenLastCalledWith({
    organizationId: "org",
    sourceId: "s",
    replaceModelComplements: {
      expected_revision: 2,
      upstream_model_id: "model",
      values: {
        context_window_tokens: null,
        tool_calling: null,
        audio_transcription: null,
        reasoning_transport: null,
        reasoning_efforts: null,
        display_name: null,
      },
    },
  });
});
