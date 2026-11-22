// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CapabilityEnablementItem } from "../../../../slices/controlPlane/controlPlaneOpenApi";

const h = vi.hoisted(() => ({
  selection: undefined as
    | undefined
    | {
        active?: {
          preparation_id: string;
          assets: { asset_id: string; filename: string; sha256: string; size: number; slot_key: string }[];
          public_config?: { template_labels: string[] };
        };
        candidate?: { state: string; assets: { filename: string }[]; public_config?: { template_labels: string[] } };
      },
  refetch: vi.fn(),
  retry: vi.fn(),
  reset: vi.fn(),
  showError: vi.fn(),
  showSuccess: vi.fn(),
  translate: vi.fn((key: string) => key),
}));

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: h.translate }) }));
vi.mock("../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ siteDisplayName: "Acme", agentsNicknamePlural: "Assistants" }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: h.showError, showSuccess: h.showSuccess }),
}));
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetPlatformCapabilityPreparationControlPlaneV1PlatformCapabilityPreparationsRuntimeIdCapabilityIdSlotKeyGetQuery:
    () => ({ data: h.selection, isLoading: false, isError: false, refetch: h.refetch }),
  usePostPlatformCapabilityCandidateRetryControlPlaneV1PlatformCapabilityPreparationsRuntimeIdCapabilityIdSlotKeyCandidateRetryPostMutation:
    () => [h.retry, { isLoading: false }],
  useDeletePlatformCapabilityPreparationControlPlaneV1PlatformCapabilityPreparationsRuntimeIdCapabilityIdSlotKeyDeleteMutation:
    () => [h.reset, { isLoading: false }],
}));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialog", () => ({
  ConfirmationDialog: ({ open, onConfirm }: { open: boolean; onConfirm: () => void }) =>
    open ? <button onClick={onConfirm}>Confirm reset</button> : null,
}));
import { WordTemplatePlatformPanel } from "./WordTemplatePlatformPanel";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const capability = { id: "word_template", runtime_id: "runtime" } as CapabilityEnablementItem;
let container: HTMLDivElement;
let root: Root;

function render(canManage = true) {
  act(() => root.render(<WordTemplatePlatformPanel capability={capability} canManage={canManage} />));
}

beforeEach(() => {
  h.selection = undefined;
  for (const fn of [h.refetch, h.retry, h.reset, h.showError, h.showSuccess]) fn.mockReset();
  h.retry.mockReturnValue({ unwrap: () => Promise.resolve() });
  h.reset.mockReturnValue({ unwrap: () => Promise.resolve() });
  h.translate.mockClear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("WordTemplatePlatformPanel", () => {
  it("shows the active library while its replacement prepares", () => {
    h.selection = {
      active: {
        preparation_id: "active-1",
        assets: [
          {
            asset_id: "asset-1",
            filename: "Rapport.docx",
            sha256: "a".repeat(64),
            size: 10,
            slot_key: "word_template_library",
          },
          {
            asset_id: "asset-2",
            filename: "Note.docx",
            sha256: "b".repeat(64),
            size: 10,
            slot_key: "word_template_library",
          },
        ],
      },
      candidate: { state: "running", assets: [{ filename: "Nouveau.docx" }] },
    };
    render();
    expect(container.textContent).toContain("Rapport.docx");
    expect(container.textContent).toContain("Note.docx");
    expect(container.textContent).toContain("Nouveau.docx");
    expect(container.textContent).toContain("capability.word_template.platform.activeTitle");
    expect(container.textContent).toContain("capability.word_template.platform.candidateTitle");
    expect(container.textContent).toContain("capability.word_template.platform.candidate.running");
    expect(container.querySelector('[aria-label="capability.word_template.platform.editOne"]')).not.toBeNull();
    expect(h.translate).toHaveBeenCalledWith("capability.word_template.platform.intro", {
      siteDisplayName: "Acme",
      agentsNicknamePlural: "Assistants",
    });
  });

  it("edits one active file without reuploading the retained original", async () => {
    h.selection = {
      active: {
        preparation_id: "active-1",
        assets: [
          {
            asset_id: "asset-1",
            filename: "Rapport.docx",
            sha256: "a".repeat(64),
            size: 10,
            slot_key: "word_template_library",
          },
          {
            asset_id: "asset-2",
            filename: "Note.docx",
            sha256: "b".repeat(64),
            size: 10,
            slot_key: "word_template_library",
          },
        ],
      },
    };
    const fetch = vi.fn(async (_url: string, _init: RequestInit) => ({ ok: true, json: async () => ({}) }));
    vi.stubGlobal("fetch", fetch);
    render();
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(container.textContent).toContain("Rapport.docx");
    expect(container.textContent).toContain("Note.docx");
    await act(async () =>
      container
        .querySelectorAll<HTMLButtonElement>('[aria-label="capability.word_template.platform.removeOne"]')[1]
        ?.click(),
    );
    expect(fetch).not.toHaveBeenCalled();
    await act(async () =>
      [...container.querySelectorAll<HTMLButtonElement>("button")]
        .find((button) => button.textContent?.includes("capability.word_template.platform.save"))
        ?.click(),
    );
    const form = fetch.mock.calls[0]![1].body as FormData;
    expect(JSON.parse(form.get("retained_asset_ids_json") as string)).toEqual(["asset-1"]);
    expect(form.get("expected_active_preparation_id")).toBe("active-1");
    expect(JSON.parse(form.get("config_json") as string)).toEqual({
      preparation_hashes: ["a".repeat(64)],
      template_labels: ["Rapport"],
    });
    expect(form.getAll("file")).toEqual([]);
    vi.unstubAllGlobals();
  });

  it("shows stored display names and stages renaming until one platform save", async () => {
    h.selection = {
      active: {
        preparation_id: "active-1",
        assets: [
          {
            asset_id: "asset-1",
            filename: "Rapport.docx",
            sha256: "a".repeat(64),
            size: 10,
            slot_key: "word_template_library",
          },
        ],
        public_config: { template_labels: ["Rapport annuel"] },
      },
    };
    const fetch = vi.fn(async (_url: string, _init: RequestInit) => ({ ok: true, json: async () => ({}) }));
    vi.stubGlobal("fetch", fetch);
    render();
    expect(container.textContent).toContain("Rapport annuel");
    act(() =>
      container.querySelector<HTMLButtonElement>('[aria-label="capability.word_template.platform.editOne"]')?.click(),
    );
    const input = container.querySelector<HTMLInputElement>(
      '[aria-label="capability.word_template.platform.labelField"]',
    )!;
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      setter.call(input, "Compte rendu");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(fetch).not.toHaveBeenCalled();
    await act(async () =>
      [...container.querySelectorAll<HTMLButtonElement>("button")]
        .find((button) => button.textContent?.includes("capability.word_template.platform.save"))
        ?.click(),
    );
    const form = fetch.mock.calls[0]![1].body as FormData;
    expect(JSON.parse(form.get("config_json") as string).template_labels).toEqual(["Compte rendu"]);
    expect(form.get("expected_active_preparation_id")).toBe("active-1");
    expect(fetch).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });

  it("keeps the original revision fence when the active library changes during a rename", async () => {
    const asset = {
      asset_id: "asset-1",
      filename: "Rapport.docx",
      sha256: "a".repeat(64),
      size: 10,
      slot_key: "word_template_library",
    };
    h.selection = { active: { preparation_id: "active-1", assets: [asset] } };
    const fetch = vi.fn(async (_url: string, _init: RequestInit) => ({ ok: true, json: async () => ({}) }));
    vi.stubGlobal("fetch", fetch);
    render();
    act(() =>
      container.querySelector<HTMLButtonElement>('[aria-label="capability.word_template.platform.editOne"]')?.click(),
    );
    h.selection = { active: { preparation_id: "active-2", assets: [asset] } };
    render();
    const input = container.querySelector<HTMLInputElement>(
      '[aria-label="capability.word_template.platform.labelField"]',
    )!;
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "Nouveau nom");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () =>
      [...container.querySelectorAll<HTMLButtonElement>("button")]
        .find((button) => button.textContent?.includes("capability.word_template.platform.save"))
        ?.click(),
    );
    const form = fetch.mock.calls[0]![1].body as FormData;
    expect(form.get("expected_active_preparation_id")).toBe("active-1");
    vi.unstubAllGlobals();
  });

  it("closes an unfinished rename when the platform draft is canceled", () => {
    h.selection = {
      active: {
        preparation_id: "active-1",
        assets: [
          {
            asset_id: "asset-1",
            filename: "Rapport.docx",
            sha256: "a".repeat(64),
            size: 10,
            slot_key: "word_template_library",
          },
        ],
      },
    };
    render();
    act(() =>
      container.querySelector<HTMLButtonElement>('[aria-label="capability.word_template.platform.editOne"]')?.click(),
    );
    const input = container.querySelector<HTMLInputElement>(
      '[aria-label="capability.word_template.platform.labelField"]',
    )!;
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "Nouveau nom");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    act(() =>
      [...container.querySelectorAll<HTMLButtonElement>("button")]
        .find((button) => button.textContent?.includes("capability.word_template.platform.cancel"))
        ?.click(),
    );
    expect(container.querySelector('[aria-label="capability.word_template.platform.labelField"]')).toBeNull();
    expect(container.textContent).toContain("Rapport");
    expect(container.textContent).not.toContain("Nouveau nom");
  });

  it("shows proposed display names while a replacement prepares", () => {
    h.selection = {
      candidate: {
        state: "running",
        assets: [{ filename: "Rapport.docx" }],
        public_config: { template_labels: ["Rapport annuel"] },
      },
    };
    render();
    expect(container.textContent).toContain("Rapport annuel");
  });

  it("offers retry for a failed candidate only to managers", async () => {
    h.selection = { candidate: { state: "failed", assets: [{ filename: "Nouveau.docx" }] } };
    render(false);
    expect(container.querySelector("button")).toBeNull();
    render(true);
    const retry = [...container.querySelectorAll("button")].find((button) =>
      button.textContent?.includes("capability.word_template.platform.retry"),
    );
    expect(retry).toBeDefined();
    await act(async () => retry?.click());
    expect(h.retry).toHaveBeenCalledWith({
      runtimeId: "runtime",
      capabilityId: "word_template",
      slotKey: "word_template_library",
    });
    expect(h.refetch).toHaveBeenCalledTimes(1);
  });

  it("fences a reset to the library visible when confirmation opened", async () => {
    h.selection = {
      active: {
        preparation_id: "active-1",
        assets: [
          {
            asset_id: "asset-1",
            filename: "Rapport.docx",
            sha256: "a".repeat(64),
            size: 10,
            slot_key: "word_template_library",
          },
        ],
      },
    };
    render();
    await act(async () =>
      [...container.querySelectorAll<HTMLButtonElement>("button")]
        .find((button) => button.textContent?.includes("capability.word_template.platform.reset"))
        ?.click(),
    );
    h.selection = {
      active: {
        preparation_id: "active-2",
        assets: [
          {
            asset_id: "asset-2",
            filename: "Nouveau.docx",
            sha256: "b".repeat(64),
            size: 10,
            slot_key: "word_template_library",
          },
        ],
      },
    };
    render();
    await act(async () =>
      [...container.querySelectorAll<HTMLButtonElement>("button")]
        .find((button) => button.textContent === "Confirm reset")
        ?.click(),
    );
    expect(h.reset).toHaveBeenCalledWith({
      runtimeId: "runtime",
      capabilityId: "word_template",
      slotKey: "word_template_library",
      expectedActivePreparationId: "active-1",
    });
  });
});
