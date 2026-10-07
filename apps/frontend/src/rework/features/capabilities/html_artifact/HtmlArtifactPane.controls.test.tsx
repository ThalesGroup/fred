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

// The viewer's two reader-facing controls.
//
// STOP: an artifact runs on arrival (RFC §4.7: a run gate was declined for the
// friction it puts on every artifact), so the remedy is to stop one that hangs the
// tab or shows something it should not. The kill is UNMOUNTING the frames — that
// destroys the browsing contexts, so scripts, timers and workers stop with them.
// What these tests can assert is that the frames really leave the DOM; the
// browser's part is a primitive jsdom cannot show.
//
// CLOSE: each tab carries a close control, and the active underline has to run
// under it so the pair reads as one tab. That means the active class belongs to the
// WRAPPER, not the label button — the regression these tests pin.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const WITH_SCRIPT = "<h1>hi</h1><script>setInterval(function(){},10)</script>";
const STATIC_ONLY = "<h1>hi</h1><p>nothing to run</p>";

let html = WITH_SCRIPT;
let artifactId = "a1";
let extraIds: string[] = [];

const snapshot = (id: string) => ({
  type: "html_artifact" as const,
  artifact_id: id,
  title: `Page ${id}`,
  html,
  css: "",
  version: "v1",
});

vi.mock("./htmlArtifactSlice", () => ({
  selectHtmlArtifactsById: () => Object.fromEntries([artifactId, ...extraIds].map((id) => [id, snapshot(id)])),
  selectHtmlArtifactSessionId: () => "s1",
  selectHtmlArtifactSelectedId: () => artifactId,
  selectHtmlArtifact: (id: string) => ({ type: "select", payload: id }),
  selectHtmlArtifactClosedIds: () => ({}),
  closeHtmlArtifact: (id: string) => ({ type: "close", payload: id }),
}));
vi.mock("../useOpenSessionId", () => ({ useOpenSessionId: () => "s1" }));
// The posture is resolved through RTK Query; these tests are about the tabs.
vi.mock("./useHtmlArtifactJavaScript", () => ({ useHtmlArtifactJavaScriptAllowed: () => true }));
vi.mock("react-redux", () => ({
  useSelector: (fn: (s: unknown) => unknown) => fn({}),
  useDispatch: () => () => undefined,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, o?: { defaultValue?: string }) => o?.defaultValue ?? key }),
}));
vi.mock("@shared/atoms/Icon/Icon", () => ({ default: () => null }));
// A real button, so the control can be found by its label and clicked.
vi.mock("@shared/atoms/IconButton/IconButton", () => ({
  default: (props: { "aria-label"?: string; onClick?: () => void }) => (
    <button aria-label={props["aria-label"]} onClick={props.onClick} />
  ),
}));
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

const render = () =>
  act(() => {
    root.render(<HtmlArtifactPane capabilityId="html_artifact" onClose={() => undefined} />);
  });
const button = (label: string) => container.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`);
const frames = () => container.querySelectorAll("iframe").length;

beforeEach(() => {
  html = WITH_SCRIPT;
  artifactId = "a1";
  extraIds = [];
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("HtmlArtifactPane stop control", () => {
  it("unmounts the preview frames, which is what ends execution", () => {
    render();
    expect(frames()).toBe(1);

    act(() => button("Stop the page")!.click());

    // No frame left to run anything, and the reader is told why it is blank.
    expect(frames()).toBe(0);
    expect(container.textContent).toContain("The page has been stopped.");
  });

  it("runs the page again on a second click", () => {
    render();
    act(() => button("Stop the page")!.click());
    expect(button("Stop the page")).toBeNull();

    act(() => button("Run the page again")!.click());

    expect(frames()).toBe(1);
    expect(container.textContent).not.toContain("The page has been stopped.");
  });

  it("offers nothing to stop on a page that cannot execute", () => {
    html = STATIC_ONLY;
    render();

    expect(frames()).toBe(1);
    expect(button("Stop the page")).toBeNull();
  });

  it("starts the next artifact running instead of inheriting a stopped state", () => {
    render();
    act(() => button("Stop the page")!.click());
    expect(frames()).toBe(0);

    // Selecting another artifact is a fresh page; it must not open dead.
    artifactId = "a2";
    render();

    expect(frames()).toBe(1);
    expect(button("Stop the page")).not.toBeNull();
  });
});

describe("HtmlArtifactPane tab close control", () => {
  it("puts the active underline on the WRAPPER, so it runs under the close button", () => {
    extraIds = ["a2"];
    render();

    const wraps = Array.from(container.querySelectorAll('[role="tab"]')).map((tab) => tab.parentElement!);
    const [active, inactive] = wraps;
    // The label button must NOT own the underline any more — if it does, the close
    // button sits outside the primary rule and the tab reads as two controls.
    expect(active.className).toMatch(/tabWrapActive/);
    expect(inactive.className).not.toMatch(/tabWrapActive/);
    // The close control is a sibling inside that same wrapper.
    expect(active.querySelector('button[aria-label="Close this artifact"]')).not.toBeNull();
  });

  it("shows a tab even for a single artifact, so it can be closed", () => {
    render();

    expect(container.querySelectorAll('[role="tab"]').length).toBe(1);
    expect(container.querySelector('button[aria-label="Close this artifact"]')).not.toBeNull();
  });
});
