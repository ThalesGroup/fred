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

// The visible half of the JavaScript posture: a page whose script will not run
// must SAY so. Silent inertness is the failure this notice exists to prevent —
// the page was produced while the team could run script, the right was withdrawn,
// and without a word it simply looks broken.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const SCRIPTED = '<h1>hi</h1><button onclick="go()">go</button>';
const STATIC = "<h1>hi</h1>";

const artifact = {
  type: "html_artifact" as const,
  artifact_id: "a1",
  title: "Landing",
  html: SCRIPTED,
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
  artifact.html = SCRIPTED;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("HtmlArtifactPane suppressed-script notice", () => {
  const NOTICE =
    "This page contains JavaScript, which your team is not allowed to run. It is shown without interaction.";

  const render = () =>
    act(() => {
      root.render(<HtmlArtifactPane capabilityId="html_artifact" onClose={() => undefined} />);
    });

  it("tells the reader when the page carries script the team may not run", () => {
    allowJavaScript = false;

    render();

    expect(container.textContent).toContain(NOTICE);
  });

  it("stays silent for a team that may run script", () => {
    allowJavaScript = true;

    render();

    expect(container.textContent).not.toContain(NOTICE);
  });

  it("stays silent for a static page, even in the restricted mode", () => {
    // The everyday case: nothing was suppressed, so there is nothing to say.
    // A notice here would sit on every page a restricted team ever produces.
    allowJavaScript = false;
    artifact.html = STATIC;

    render();

    expect(container.textContent).not.toContain(NOTICE);
  });
});
