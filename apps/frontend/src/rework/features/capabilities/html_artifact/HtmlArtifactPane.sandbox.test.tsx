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

// Sandbox regression guard (RFC §4.7). Two levels, and the test covers both.
//
// The Preview iframes host our TRUSTED shell, so they stay exactly
// `sandbox="allow-scripts"`: the shell's bootstrap is a script. The ARTIFACT's own
// permission sits one level down, on the inner frame the shell writes — and that
// one follows the team's posture: `allow-scripts` for a team that may run script,
// NO token at all for a team that may not.
//
// `allow-same-origin` must never join either: the pair is what would let untrusted
// content clear its own sandbox and reach the app's DOM, cookies and storage, and
// the isolation rests entirely on these attributes since the markup is no longer
// sanitized.

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
let allowJavaScript = true;
vi.mock("./useHtmlArtifactJavaScript", () => ({
  useHtmlArtifactJavaScriptAllowed: () => allowJavaScript,
}));
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
  allowJavaScript = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("HtmlArtifactPane preview sandbox", () => {
  it('renders the shell-hosting preview iframes as sandbox="allow-scripts", never same-origin', () => {
    act(() => {
      root.render(<HtmlArtifactPane capabilityId="html_artifact" onClose={() => undefined} />);
    });

    const iframes = container.querySelectorAll("iframe");
    // Executable pages use one frame: keeping a second one alive would let
    // hidden script continue after a switch or revocation.
    expect(iframes.length).toBe(1);
    for (const frame of iframes) {
      // The shell's own bootstrap must run; this token is structural, not a
      // decision about the artifact.
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
    allowJavaScript = false;
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

describe("HtmlArtifactPane artifact frame posture", () => {
  const innerSandbox = (srcdoc: string) => /<iframe id="a" sandbox="([^"]*)"/.exec(srcdoc)?.[1];

  it("grants the inner artifact frame allow-scripts for an opted-in team", () => {
    allowJavaScript = true;

    act(() => {
      root.render(<HtmlArtifactPane capabilityId="html_artifact" onClose={() => undefined} />);
    });

    const [loaded] = container.querySelectorAll("iframe");
    expect(innerSandbox(loaded.getAttribute("srcdoc") ?? "")).toBe("allow-scripts");
  });

  it("destroys the executable frame when the team's right is withdrawn", () => {
    allowJavaScript = true;
    act(() => root.render(<HtmlArtifactPane capabilityId="html_artifact" onClose={() => undefined} />));
    const executable = container.querySelector("iframe")!;
    expect(innerSandbox(executable.getAttribute("srcdoc") ?? "")).toBe("allow-scripts");

    allowJavaScript = false;
    act(() => root.render(<HtmlArtifactPane capabilityId="html_artifact" onClose={() => undefined} />));

    expect(executable.isConnected).toBe(false);
    for (const frame of container.querySelectorAll("iframe")) {
      expect(frame.getAttribute("srcdoc") ?? "").not.toContain('sandbox="allow-scripts"');
    }
  });

  it("gives the inner artifact frame NO token for a team that may not run script", () => {
    allowJavaScript = false;

    act(() => {
      root.render(<HtmlArtifactPane capabilityId="html_artifact" onClose={() => undefined} />);
    });

    const [, loaded] = container.querySelectorAll("iframe");
    const srcdoc = loaded.getAttribute("srcdoc") ?? "";
    // Empty, not absent: an iframe with no sandbox attribute at all is UNsandboxed.
    expect(innerSandbox(srcdoc)).toBe("");
    expect(srcdoc).not.toContain("allow-scripts");
    expect(srcdoc).not.toContain("allow-same-origin");
  });

  it("keeps the CSP in the restricted mode — denying script is not denying egress", () => {
    allowJavaScript = false;

    act(() => {
      root.render(<HtmlArtifactPane capabilityId="html_artifact" onClose={() => undefined} />);
    });

    const [, loaded] = container.querySelectorAll("iframe");
    const srcdoc = loaded.getAttribute("srcdoc") ?? "";
    // Markup alone still reaches the network (`<img src="https://host/?d=…">`),
    // so the policy has to hold in both modes.
    expect(srcdoc).toContain("default-src 'none'");
    expect(srcdoc).toContain("webrtc 'block'");
  });
});
