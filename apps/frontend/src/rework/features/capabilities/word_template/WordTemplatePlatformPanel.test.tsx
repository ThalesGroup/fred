// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Library } from "../../../../slices/controlPlane/controlPlaneOpenApi";

const h = vi.hoisted(() => ({
  library: undefined as Library | undefined,
  save: vi.fn(),
  upload: vi.fn(),
  refetch: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: vi.fn(), showSuccess: vi.fn() }),
}));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useResolveWordTemplateLibraryQuery: () => ({ currentData: h.library, isLoading: false, refetch: h.refetch }),
  useSaveWordTemplateLibraryMutation: () => [h.save, { isLoading: false }],
  useUploadWordTemplateMutation: () => [h.upload],
}));
vi.mock("./WordTemplateLibraryEditor", () => ({
  WordTemplateLibraryEditor: ({
    onRemove,
    status,
    canEdit,
    disabled,
  }: {
    onRemove: (index: number) => void;
    status: React.ReactNode;
    canEdit: boolean;
    disabled: boolean;
  }) => (
    <>
      <button disabled={!canEdit || disabled} onClick={() => onRemove(1)}>
        Remove second
      </button>
      {status}
    </>
  ),
}));
import { WordTemplatePlatformPanel } from "./WordTemplatePlatformPanel";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: Root;
function library(ids: string[]): Library {
  return {
    source: "organization",
    activation_ready: true,
    own_file_ids: ids,
    files: ids.map((id, slot) => ({
      label: id,
      preparation_state: "ready",
      preparation_error: null,
      file: {
        id,
        slot,
        name: `${id}.docx`,
        agent_instance_id: null,
        capability_id: "word_template",
        cleaned_at: null,
        error_code: null,
        mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        published_at: null,
        request_key: id,
        runtime_id: "runtime",
        sha256: "a".repeat(64),
        size: 10,
        space_id: "org",
        status: "stored",
      },
    })),
  };
}
function render(canManage = true) {
  act(() =>
    root.render(
      <WordTemplatePlatformPanel
        capability={{ id: "word_template", name: "Word" }}
        organizationId="org"
        runtimeId="runtime"
        baseUrl={null}
        canManage={canManage}
      />,
    ),
  );
}
beforeEach(() => {
  h.library = library(["first", "second"]);
  h.save.mockReset().mockReturnValue({ unwrap: async () => undefined });
  h.upload.mockReset();
  h.refetch.mockReset();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});
async function save() {
  const button = [...container.querySelectorAll("button")].find((button) => button.textContent === "common.save")!;
  await act(async () => button.click());
}
describe("organization Word library", () => {
  it("retains stored originals without reuploading them", async () => {
    render();
    act(() => container.querySelector("button")!.click());
    await save();
    expect(h.upload).not.toHaveBeenCalled();
    expect(h.save).toHaveBeenCalledWith({
      spaceId: "org",
      runtimeId: "runtime",
      libraryChange: {
        files: [{ file_id: "first", label: "first" }],
        expected_file_ids: ["first", "second"],
      },
    });
  });
  it("keeps the original revision when polling reports a concurrent replacement", async () => {
    render();
    act(() => container.querySelector("button")!.click());
    h.library = library(["replacement"]);
    render();
    await save();
    expect(h.save.mock.calls[0][0].libraryChange.expected_file_ids).toEqual(["first", "second"]);
    expect(h.save.mock.calls[0][0].libraryChange.files).toEqual([{ file_id: "first", label: "first" }]);
  });
  it("retries the failed saved library with the current CAS receipts", async () => {
    h.library!.files[0].preparation_state = "failed";
    render();
    const retry = [...container.querySelectorAll("button")].find(
      (button) => button.textContent === "capability.word_template.preparation.retry",
    )!;
    await act(async () => retry.click());
    expect(h.upload).not.toHaveBeenCalled();
    expect(h.save).toHaveBeenCalledWith({
      spaceId: "org",
      runtimeId: "runtime",
      libraryChange: {
        files: [
          { file_id: "first", label: "first" },
          { file_id: "second", label: "second" },
        ],
        expected_file_ids: ["first", "second"],
      },
    });
  });
  it("offers no mutation without organization management permission", () => {
    render(false);
    expect(container.querySelector("button")!.disabled).toBe(true);
    expect([...container.querySelectorAll("button")].some((button) => button.textContent === "common.save")).toBe(
      false,
    );
  });
});
