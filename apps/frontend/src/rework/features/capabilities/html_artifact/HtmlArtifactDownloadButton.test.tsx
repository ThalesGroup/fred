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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  showError: vi.fn(),
  downloadHtmlArtifactPng: vi.fn(),
  downloadHtmlArtifactPdf: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_k: string, o?: { defaultValue?: string; format?: string }) =>
      (o?.defaultValue ?? "").replace("{{format}}", o?.format ?? ""),
  }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: h.showError }) }));
// One plain button per option, so a test can pick a format without the real menu.
vi.mock("@shared/molecules/IconButtonMenu/IconButtonMenu", () => ({
  default: ({ options, onSelect }: { options: { value: string }[]; onSelect: (v: string) => void }) =>
    options.map((o) => (
      <button key={o.value} data-format={o.value} onClick={() => onSelect(o.value)}>
        {o.value}
      </button>
    )),
}));
vi.mock("./htmlArtifactDocument", () => ({ downloadHtmlArtifact: vi.fn() }));
vi.mock("./htmlArtifactExport", () => ({
  downloadHtmlArtifactPng: h.downloadHtmlArtifactPng,
  downloadHtmlArtifactPdf: h.downloadHtmlArtifactPdf,
}));

import HtmlArtifactDownloadButton from "./HtmlArtifactDownloadButton";

describe("HtmlArtifactDownloadButton", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => root.render(<HtmlArtifactDownloadButton html="<p>x</p>" css="" title="Report" />));
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.restoreAllMocks();
    h.showError.mockReset();
  });

  it("logs a failed PNG export and shows the error toast with its detail", async () => {
    const error = new DOMException("Tainted canvases may not be exported.", "SecurityError");
    h.downloadHtmlArtifactPng.mockRejectedValueOnce(error);
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);

    await act(async () => container.querySelector<HTMLButtonElement>('[data-format="png"]')!.click());

    expect(consoleError).toHaveBeenCalledWith("HTML artifact png export failed", error);
    expect(h.showError).toHaveBeenCalledWith({
      summary: "Could not export the PNG.",
      detail: "SecurityError: Tainted canvases may not be exported.",
    });
  });

  it("stays silent when the PDF export succeeds", async () => {
    h.downloadHtmlArtifactPdf.mockResolvedValueOnce(undefined);
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);

    await act(async () => container.querySelector<HTMLButtonElement>('[data-format="pdf"]')!.click());

    expect(h.downloadHtmlArtifactPdf).toHaveBeenCalledWith("<p>x</p>", "", "Report");
    expect(consoleError).not.toHaveBeenCalled();
    expect(h.showError).not.toHaveBeenCalled();
  });
});
