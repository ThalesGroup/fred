// @vitest-environment jsdom
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

// Sandbox regression guard (RFC §4.7): the Preview iframes MUST stay exactly
// `sandbox="allow-scripts"` — author JS runs, and `allow-same-origin` never joins
// it. The pair is what would let untrusted content clear its own sandbox and reach
// the app's DOM, cookies and storage, and the isolation now rests entirely on this
// attribute since the markup is no longer sanitized. This renders the pane and
// asserts the attribute directly, so such a regression fails the build rather
// than shipping.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const artifact = {
  type: "html_artifact" as const,
  artifact_id: "a1",
  title: "Landing",
  html: "<h1>hi</h1>",
  css: "h1{color:red}",
  version: "v1",
};

// The slice is the pane's data source; feed it one artifact for the open session.
vi.mock("./htmlArtifactSlice", () => ({
  selectHtmlArtifactsById: () => ({ a1: artifact }),
  selectHtmlArtifactSessionId: () => "s1",
  selectHtmlArtifactSelectedId: () => "a1",
  selectHtmlArtifact: (id: string) => ({ type: "select", payload: id }),
  selectHtmlArtifactClosedIds: () => ({}),
  closeHtmlArtifact: (id: string) => ({ type: "close", payload: id }),
}));
vi.mock("../useOpenSessionId", () => ({ useOpenSessionId: () => "s1" }));
vi.mock("react-redux", () => ({
  useSelector: (fn: (s: unknown) => unknown) => fn({}),
  useDispatch: () => () => undefined,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? "" }),
}));
vi.mock("@shared/atoms/Icon/Icon", () => ({ default: () => null }));
vi.mock("@shared/atoms/IconButton/IconButton", () => ({ default: () => null }));
vi.mock("@shared/atoms/Tooltip/Tooltip", () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("@shared/molecules/CodeBlock/CodeBlock", () => ({ CodeBlock: () => null }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({
    showSuccess: () => undefined,
    showError: () => undefined,
    showInfo: () => undefined,
    showWarn: () => undefined,
  }),
}));
vi.mock("./HtmlArtifactDownloadButton", () => ({ default: () => null }));

const { HtmlArtifactPane } = await import("./HtmlArtifactPane");

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("HtmlArtifactPane preview sandbox", () => {
  it('renders the preview iframes as sandbox="allow-scripts" with no same-origin escape', () => {
    act(() => {
      root.render(<HtmlArtifactPane capabilityId="html_artifact" onClose={() => undefined} />);
    });

    const iframes = container.querySelectorAll("iframe");
    // The double-buffered preview mounts two stacked frames.
    expect(iframes.length).toBe(2);
    for (const frame of iframes) {
      // Author JS must run — the artifact needs it for tabs and animations.
      expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
      // …but NEVER alongside same-origin: together the two would let the content
      // clear its own sandbox and reach the app's DOM, cookies and storage.
      expect(frame.outerHTML).not.toContain("allow-same-origin");
    }
  });
});

describe("HtmlArtifactPane preview buffers", () => {
  // Chromium paints a frame blank when its doc lands while an empty srcdoc is still loading.
  it("leaves an empty buffer without a srcdoc attribute", () => {
    act(() => {
      root.render(<HtmlArtifactPane capabilityId="html_artifact" onClose={() => undefined} />);
    });

    const [back, loaded] = container.querySelectorAll("iframe");
    expect(back.hasAttribute("srcdoc")).toBe(false);
    // The preview renders the shell, which carries the artifact in its bootstrap
    // string literal with every `<` escaped — hence `\u003ch1>`, not `<h1>`.
    expect(loaded.getAttribute("srcdoc")).toContain("\\u003ch1>hi\\u003c/h1>");
    expect(loaded.getAttribute("srcdoc")).toContain("frame-src blob:");
  });
});
