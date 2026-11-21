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
        active?: { assets: { filename: string }[] };
        candidate?: { state: string; assets: { filename: string }[] };
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
  ConfirmationDialog: () => null,
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
      active: { assets: [{ filename: "Rapport.docx" }, { filename: "Note.docx" }] },
      candidate: { state: "running", assets: [{ filename: "Nouveau.docx" }] },
    };
    render();
    expect(h.translate).toHaveBeenCalledWith("capability.word_template.platform.active", {
      names: "Rapport.docx, Note.docx",
    });
    expect(container.textContent).toContain("capability.word_template.platform.candidate.running");
    expect(container.textContent).toContain("capability.word_template.platform.replace");
    expect(h.translate).toHaveBeenCalledWith("capability.word_template.platform.intro", {
      siteDisplayName: "Acme",
      agentsNicknamePlural: "Assistants",
    });
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
});
