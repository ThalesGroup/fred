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
}));

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ agentsNicknameSingular: "Assistant" }),
}));
vi.mock("./WordTemplatePreparationStatus", () => ({ WordTemplatePreparationStatus: () => null }));
import { WordTemplateLibraryForm } from "./WordTemplateLibraryForm";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: Root;

const existing = { template_key: "old-key", label: "Old template", parts_summary: { kept: true } };
function render(library: unknown[] = [existing]) {
  act(() =>
    root.render(
      <WordTemplateLibraryForm
        capabilityId="word_template"
        disabled={false}
        configValues={{ template_library: library }}
        assetFiles={{}}
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
  });
});
