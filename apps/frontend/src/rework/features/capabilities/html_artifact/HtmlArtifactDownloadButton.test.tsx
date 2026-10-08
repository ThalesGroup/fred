// @vitest-environment happy-dom
//
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

// The PNG/PDF capture happens in a frame that cannot run script (RFC §4.7), so an
// interactive artifact rasterizes before its JS runs. The menu warns about that,
// and only for the formats it affects — the .html download carries the live page.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const infos: string[] = [];
type Format = "html" | "pdf" | "png";
let select: ((format: Format) => void | Promise<void>) | null = null;
let freshPermission = true;

vi.mock("./useHtmlArtifactJavaScript", () => ({
  useCheckHtmlArtifactJavaScriptAllowed: () => async () => freshPermission,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    // Echo the key so a test can tell which message fired, and prove the format
    // actually reaches the interpolation.
    t: (key: string, o?: { format?: string }) => (o?.format ? `${key}:${o.format}` : key),
  }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({
    showInfo: ({ summary }: { summary: string }) => infos.push(summary),
    showError: () => undefined,
    showSuccess: () => undefined,
    showWarn: () => undefined,
  }),
}));
// Capture the menu's onSelect so the branch can be driven without UI plumbing.
vi.mock("@shared/molecules/IconButtonMenu/IconButtonMenu", () => ({
  default: (props: { onSelect: (format: Format) => void | Promise<void> }) => {
    select = props.onSelect;
    return null;
  },
}));

const downloadHtml = vi.fn();
const downloadPdf = vi.fn(() => Promise.resolve());
const downloadPng = vi.fn(() => Promise.resolve());
vi.mock("./htmlArtifactDocument", async (original) => ({
  ...(await original<typeof import("./htmlArtifactDocument")>()),
  downloadHtmlArtifact: (...args: unknown[]) => downloadHtml(...args),
}));
vi.mock("./htmlArtifactExport", () => ({
  downloadHtmlArtifactPdf: () => downloadPdf(),
  downloadHtmlArtifactPng: () => downloadPng(),
}));

const { default: HtmlArtifactDownloadButton } = await import("./HtmlArtifactDownloadButton");

let container: HTMLDivElement;
let root: Root;

// The posture is explicit here, and the prop now defaults to DENIED: the warning
// below is about script that will actually run, so it only applies to a team that
// may run it.
function mount(html: string, allowJavaScript = true) {
  act(() => {
    root.render(<HtmlArtifactDownloadButton html={html} css="" title="My Page" allowJavaScript={allowJavaScript} />);
  });
}

beforeEach(() => {
  infos.length = 0;
  select = null;
  freshPermission = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.clearAllMocks();
});

describe("HtmlArtifactDownloadButton pre-script capture warning", () => {
  it("warns on PDF and names the format when the artifact runs script", async () => {
    mount("<script>window.x=1</script><h1>hi</h1>");
    await act(async () => void (await select!("pdf")));

    expect(infos).toEqual(["capability.html_artifact.exportStaticCapture:PDF"]);
    expect(downloadPdf).toHaveBeenCalledOnce();
  });

  it("warns on PNG too", async () => {
    mount('<button onclick="f()">x</button>');
    await act(async () => void (await select!("png")));

    expect(infos).toEqual(["capability.html_artifact.exportStaticCapture:PNG"]);
    expect(downloadPng).toHaveBeenCalledOnce();
  });

  it("stays silent for an artifact with nothing to execute", async () => {
    mount("<h1>hi</h1><p>static page</p>");
    await act(async () => void (await select!("pdf")));

    expect(infos).toEqual([]);
    expect(downloadPdf).toHaveBeenCalledOnce();
  });

  it("stays silent for a team that may not run script — nothing is captured early", async () => {
    // The page carries script, but it will not run in any frame this team sees,
    // so the export is faithful and the "before its JavaScript runs" caveat would
    // describe a thing that never happens.
    mount("<script>window.x=1</script><h1>hi</h1>", false);
    await act(async () => void (await select!("pdf")));

    expect(infos).toEqual([]);
    expect(downloadPdf).toHaveBeenCalledOnce();
  });

  it("never warns on the HTML download, which carries the live page", async () => {
    mount("<script>window.x=1</script>");
    await act(async () => void (await select!("html")));

    expect(infos).toEqual([]);
    expect(downloadHtml).toHaveBeenCalledOnce();
    expect(downloadPdf).not.toHaveBeenCalled();
    expect(downloadPng).not.toHaveBeenCalled();
  });

  it("saves a restricted file when a fresh check withdraws a cached grant", async () => {
    mount("<script>window.x=1</script>", true);
    freshPermission = false;
    await act(async () => void (await select!("html")));

    expect(downloadHtml).toHaveBeenCalledWith("<script>window.x=1</script>", "", "My Page", false);
  });
});
