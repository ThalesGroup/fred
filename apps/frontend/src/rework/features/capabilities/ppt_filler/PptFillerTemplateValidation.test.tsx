// @vitest-environment jsdom
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

import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import en from "../../../../locales/en/translation.json";
import fr from "../../../../locales/fr/translation.json";
import type { StagedAssetFile } from "../types";
import type { ParseResult } from "./api/pptFillerCapabilityOpenApi";

const api = vi.hoisted(() => ({ result: { schema: [], errors: [] } as ParseResult, success: vi.fn() }));
vi.mock("./api/pptFillerCapabilityOpenApi", () => ({
  useAnalyzeAnalyzePostMutation: () => [() => ({ unwrap: async () => api.result }), { isLoading: false }],
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showSuccess: api.success }) }));
vi.mock("./PptTemplateDownloadButton", () => ({ PptTemplateDownloadButton: () => null }));

const { PptFillerConfigForm } = await import("./PptFillerConfigForm");
const { PptFillerPackOptions } = await import("./PptFillerPackOptions");
const surfaces = [
  ["Advanced", PptFillerConfigForm],
  ["Simple", PptFillerPackOptions],
] as const;
let root: Root;
let container: HTMLDivElement;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  api.result = { schema: [], errors: [] };
  api.success.mockClear();
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

describe.each(surfaces)("%s template validation", (_label, Surface) => {
  async function render(locale: "en" | "fr") {
    const i18n = createInstance();
    await i18n.init({ lng: locale, resources: { en: { translation: en }, fr: { translation: fr } } });
    const onBlockingErrorChange = vi.fn();
    function Form() {
      const [assetFiles, setAssetFiles] = useState<Record<string, StagedAssetFile | undefined>>({});
      return (
        <Surface
          capabilityId="ppt_filler"
          disabled={false}
          configValues={{}}
          assetFiles={assetFiles}
          onConfigChange={() => {}}
          onBlockingErrorChange={onBlockingErrorChange}
          onAssetFileChange={(slot, file) => setAssetFiles({ [slot]: file ?? undefined })}
        />
      );
    }
    await act(async () =>
      root.render(
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>
            <Form />
          </MemoryRouter>
        </I18nextProvider>,
      ),
    );
    const input = container.querySelector("input[type=file]") as HTMLInputElement;
    Object.defineProperty(input, "files", { value: [new File(["deck"], "template.pptx")] });
    await act(async () => input.dispatchEvent(new Event("change", { bubbles: true })));
    return onBlockingErrorChange;
  }

  it.each(["en", "fr"] as const)("blocks an empty deck with helpful %s text and guide link", async (locale) => {
    const blocking = await render(locale);
    const text = container.textContent ?? "";
    expect(text).toContain(locale === "en" ? "No template fields found" : "Aucun champ de modèle trouvé");
    expect(text).toContain("{{title}}");
    expect(text).toContain(locale === "en" ? "slide notes" : "notes des diapositives");
    expect(blocking.mock.lastCall?.[0]).toContain(locale === "en" ? "No template fields" : "Aucun champ");
    expect(container.querySelector('a[href="/ppt-filler-help"]')?.textContent).toBe(
      locale === "en" ? en.capability.ppt_filler.form.learnMore : fr.capability.ppt_filler.form.learnMore,
    );
    expect(api.success).not.toHaveBeenCalled();
  });

  it("rejects a schema containing only fixed slides", async () => {
    api.result = { schema: [{ slide: 1, keys: [] }], errors: [] };
    const blocking = await render("en");
    expect(blocking.mock.lastCall?.[0]).toContain("No template fields found");
    expect(api.success).not.toHaveBeenCalled();
  });

  it("accepts fields alongside fixed slides", async () => {
    api.result = {
      schema: [
        { slide: 1, keys: [] },
        { slide: 2, keys: [{ key: "title", description: "The title" }] },
      ],
      errors: [],
    };
    const blocking = await render("en");
    expect(blocking.mock.lastCall?.[0]).toBeNull();
    expect(container.textContent).not.toContain("No template fields found");
  });
});
