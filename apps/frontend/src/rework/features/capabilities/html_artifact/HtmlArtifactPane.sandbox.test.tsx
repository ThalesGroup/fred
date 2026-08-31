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

// Layer B regression guard (RFC §4.7): the Preview iframes MUST stay `sandbox=""`
// — no `allow-scripts`, no `allow-same-origin`. That empty sandbox is the
// browser-enforced no-script guarantee for the in-app preview; a future edit that
// added a token or dropped the attribute would silently re-enable script
// execution. This renders the pane and asserts the attribute directly, so such a
// regression fails the build rather than shipping.

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
  it('renders the preview iframes as sandbox="" with no script/same-origin escape', () => {
    act(() => {
      root.render(<HtmlArtifactPane capabilityId="html_artifact" onClose={() => undefined} />);
    });

    const iframes = container.querySelectorAll("iframe");
    // The double-buffered preview mounts two stacked frames.
    expect(iframes.length).toBe(2);
    for (const frame of iframes) {
      expect(frame.getAttribute("sandbox")).toBe("");
      expect(frame.outerHTML).not.toContain("allow-scripts");
      expect(frame.outerHTML).not.toContain("allow-same-origin");
    }
  });
});
