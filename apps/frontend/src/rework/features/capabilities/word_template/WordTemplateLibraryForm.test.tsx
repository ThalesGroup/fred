// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  configChange: vi.fn(),
  assetChange: vi.fn(),
  blockingChange: vi.fn(),
  platformQuery: vi.fn(),
  platformSelection: undefined as
    | undefined
    | { source: string; files: { file: { id: string; name: string }; label: string }[] },
}));

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ agentsNicknameSingular: "Assistant" }),
}));
vi.mock("./WordTemplatePreparationStatus", () => ({ WordTemplatePreparationStatus: () => null }));
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useResolveWordTemplateLibraryQuery: (...args: unknown[]) => {
    h.platformQuery(...args);
    return { currentData: h.platformSelection, isLoading: false, isError: false };
  },
}));
import { WordTemplateLibraryForm } from "./WordTemplateLibraryForm";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: Root;

const existing = {
  template_key: "old-key",
  label: "Old template",
  filename: "Original_template.docx",
  parts_summary: { kept: true },
};
function render(library: unknown[] = [existing], assetFiles: Record<string, File[]> = {}) {
  act(() =>
    root.render(
      <WordTemplateLibraryForm
        capabilityId="word_template"
        runtimeId="runtime"
        teamId="team"
        disabled={false}
        configValues={{ template_library: library }}
        assetFiles={assetFiles}
        onConfigChange={h.configChange}
        onAssetFileChange={h.assetChange}
        onBlockingErrorChange={h.blockingChange}
      />,
    ),
  );
}

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  h.configChange.mockClear();
  h.assetChange.mockClear();
  h.blockingChange.mockClear();
  h.platformQuery.mockClear();
  h.platformSelection = { source: "builtin", files: [] };
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("WordTemplateLibraryForm", () => {
  it("shows a blocking library error without opening the editor", () => {
    render([existing, { template_key: "other-key", label: "Old template" }]);
    expect(container.querySelector('[role="alert"]')?.textContent).toContain(
      "capability.word_template.form.duplicateLabel",
    );
  });

  it("updates the agent form from the inline list", () => {
    render();
    expect(container.querySelector('[data-color="info"]')).toBeNull();
    expect(container.textContent).toContain("Original_template.docx");
    const remove = () =>
      container.querySelector<HTMLButtonElement>('[aria-label="capability.word_template.form.removeAria"]')!;
    act(() => remove().click());
    expect(h.configChange).toHaveBeenCalledWith("template_library", []);
    expect(h.assetChange).toHaveBeenCalledWith("word_template_library", null);
    expect(container.querySelector('[role="dialog"]')).toBeNull();
  });

  it("adds multiple files to the form and preserves the existing template", () => {
    render();
    const files = [new File(["one"], "First.docx"), new File(["two"], "Second.docx")];
    const input = container.querySelector<HTMLInputElement>('[aria-label="capability.word_template.form.uploadAria"]')!;
    Object.defineProperty(input, "files", { configurable: true, value: files });
    act(() => input.dispatchEvent(new Event("change", { bubbles: true })));
    expect(h.configChange).toHaveBeenCalledWith("template_library", [
      existing,
      { label: "First" },
      { label: "Second" },
    ]);
    expect(h.assetChange).toHaveBeenCalledWith("word_template_library", files);
    render([existing, { label: "First" }, { label: "Second" }], { word_template_library: files });
    expect(container.textContent).toContain("First.docx");
    expect(container.textContent).toContain("Second.docx");
  });

  it("shows only active platform templates as read-only when the agent has none", () => {
    h.platformSelection = {
      source: "organization",
      files: [
        { file: { id: "one", name: "First.docx" }, label: "Annual report" },
        { file: { id: "two", name: "Second.docx" }, label: "Project plan" },
      ],
    };
    render([]);
    expect(container.querySelectorAll('[data-color="info"]')).toHaveLength(1);
    expect(container.textContent).toContain("capability.word_template.form.platformDescription");
    expect(container.textContent).toContain("capability.word_template.form.platformTitle");
    expect(container.textContent).toContain("Annual report");
    expect(container.textContent).toContain("Project plan");
    expect(container.textContent).not.toContain("Pending.docx");
    expect(container.querySelector('[aria-label="capability.word_template.form.removeAria"]')).toBeNull();
    expect(container.querySelector('[aria-label="capability.word_template.form.editOne"]')).toBeNull();
    expect(h.platformQuery).toHaveBeenCalledWith(
      { spaceId: "team", agentInstanceId: undefined, runtimeId: "runtime" },
      expect.objectContaining({ skip: false }),
    );
  });

  it("allows an agent library to replace a full platform library", () => {
    h.platformSelection = {
      source: "organization",
      files: Array.from({ length: 8 }, (_, index) => ({
        file: { id: `common-${index}`, name: `Common-${index}.docx` },
        label: `Common-${index}.docx`,
      })),
    };
    render([]);
    const input = container.querySelector<HTMLInputElement>('[aria-label="capability.word_template.form.uploadAria"]')!;
    expect(input.disabled).toBe(false);
    const file = new File(["one"], "Own.docx");
    Object.defineProperty(input, "files", { configurable: true, value: [file] });
    act(() => input.dispatchEvent(new Event("change", { bubbles: true })));
    expect(h.configChange).toHaveBeenCalledWith("template_library", [{ label: "Own" }]);
    render([{ label: "Own" }]);
    expect(container.textContent).toContain("Own");
    expect(container.textContent).not.toContain("Platform-0.docx");
    expect(h.platformQuery).toHaveBeenLastCalledWith(expect.anything(), expect.objectContaining({ skip: false }));
  });
});
