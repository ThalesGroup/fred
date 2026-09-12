// @vitest-environment happy-dom
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

// The panel drawer: once a launcher opens a panel, the host mounts it in an
// InlineDrawer. A pane that renders its own header suppresses the drawer's title
// band so the two don't stack. (The launcher rail itself lives in
// CapabilityLauncherRail — see its own test.)

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CapabilitySidePanelHost } from "./CapabilitySidePanelHost";
import type { CapabilitySidePanelProps } from "./types";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const state = vi.hoisted(() => ({ entries: [] as unknown[] }));

const hasContent = vi.hoisted(() => ({ value: true }));

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

// The restorer's three dependencies, so the drawer tests below are unaffected
// by it and the restore tests can drive it.
const dispatch = vi.hoisted(() => vi.fn());
const restore = vi.hoisted(() => ({ sessionId: "session-1", openPanels: [] as string[] }));

vi.mock("react-redux", () => ({ useDispatch: () => dispatch }));

vi.mock("./useOpenSessionId", () => ({ useOpenSessionId: () => restore.sessionId }));

vi.mock("./capabilityPanelMemory", () => ({
  wasPanelOpen: (_sessionId: string, panelKey: string) => restore.openPanels.includes(panelKey),
}));

vi.mock("./sidePanelRegistry", () => ({ sidePanelsForCapabilities: () => state.entries }));

vi.mock("@shared/atoms/IconButton/IconButton", () => ({
  default: ({ icon, ...rest }: { icon: { type: string }; "aria-label": string }) => (
    <button data-icon={icon.type} aria-label={rest["aria-label"]} />
  ),
}));

vi.mock("@shared/molecules/InlineDrawer/InlineDrawer", () => ({
  // Mirrors the real drawer on the two things these tests read: its own title
  // band unless the panel renders one, and open/closed as an ATTRIBUTE — the
  // real drawer never unmounts its children, it animates width and visibility,
  // which is what lets a closing panel leave with the slide.
  InlineDrawer: ({
    open,
    title,
    hideHeader,
    children,
  }: {
    open: boolean;
    title: string;
    hideHeader?: boolean;
    children: React.ReactNode;
  }) => (
    <div data-drawer data-open={open}>
      {!hideHeader && <div data-drawer-title>{title}</div>}
      {children}
    </div>
  ),
}));

function StubPanel(_props: CapabilitySidePanelProps) {
  return <div data-panel />;
}

const entry = (
  capabilityId: string,
  icon: string,
  useHasContent: () => boolean = () => hasContent.value,
  ownsHeader = false,
) => ({
  capabilityId,
  widget: `${capabilityId}_pane`,
  Component: StubPanel,
  icon,
  useHasContent,
  ownsHeader,
});

const render = (activeKey: string | null = null) =>
  renderToStaticMarkup(
    <CapabilitySidePanelHost
      capabilityIds={["ppt_filler"]}
      activeKey={activeKey}
      onActiveKeyChange={() => undefined}
    />,
  );

describe("CapabilitySidePanelHost panel drawer", () => {
  beforeEach(() => {
    state.entries = [];
  });

  it("drops the drawer's own title band for a panel that renders one", () => {
    // Two stacked title rows - the drawer naming the panel, the pane naming the
    // artefact - said the same thing twice and ate the top of the column.
    state.entries = [entry("writable_document", "edit_document", () => true, true)];

    expect(render("writable_document:writable_document_pane")).not.toContain("data-drawer-title");
  });

  it("keeps the drawer's title band for a panel that has no header of its own", () => {
    state.entries = [entry("demo_echo", "edit_note", undefined, false)];

    expect(render("demo_echo:demo_echo_pane")).toContain("data-drawer-title");
  });
});

// A pane's first render can be a long synchronous task — the writable-document
// editor parses the whole document at mount — and anything synchronous while
// the drawer is sliding stops the slide dead: a large document made the panel
// snap open instead of animating. So the drawer animates empty, and the panel
// mounts once it has landed.
describe("CapabilitySidePanelHost — the drawer animates before the panel mounts", () => {
  let container: HTMLDivElement;
  let root: Root;

  const KEY = "writable_document:writable_document_pane";
  const OTHER = "demo_echo:demo_echo_pane";

  const show = (activeKey: string | null) =>
    act(() => {
      root.render(
        <CapabilitySidePanelHost
          capabilityIds={["writable_document"]}
          activeKey={activeKey}
          onActiveKeyChange={() => undefined}
        />,
      );
    });

  const slideEnds = () =>
    act(() => {
      vi.advanceTimersByTime(250);
    });

  const drawerIsOpen = () => container.querySelector('[data-drawer][data-open="true"]') !== null;
  const panelIsMounted = () => container.querySelector("[data-panel]") !== null;
  const isLoadingShown = () => container.querySelector("[data-pane-loading]") !== null;

  beforeEach(() => {
    vi.useFakeTimers();
    state.entries = [entry("writable_document", "edit_document", () => true, true), entry("demo_echo", "edit_note")];
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    show(null);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.useRealTimers();
  });

  it("opens the drawer empty, then mounts the panel once the slide has landed", () => {
    show(KEY);

    expect(drawerIsOpen()).toBe(true);
    expect(panelIsMounted()).toBe(false);

    slideEnds();

    expect(panelIsMounted()).toBe(true);
  });

  // The Suspense fallback only covers a chunk in flight — the first open of a
  // page load. Every open after that resolves without suspending, so without a
  // placeholder of its own the drawer would slide open showing nothing at all.
  it("shows the loading placeholder for the whole slide, whether or not a chunk is in flight", () => {
    show(KEY);

    expect(isLoadingShown()).toBe(true);

    slideEnds();

    expect(isLoadingShown()).toBe(false);
    expect(panelIsMounted()).toBe(true);
  });

  it("shows nothing at all while the drawer is closed", () => {
    expect(isLoadingShown()).toBe(false);
  });

  it("swaps immediately between two panels — the drawer is already open, nothing is sliding", () => {
    show(KEY);
    slideEnds();

    show(OTHER);

    expect(panelIsMounted()).toBe(true);
  });

  it("keeps the panel mounted through the closing slide, then drops it", () => {
    show(KEY);
    slideEnds();

    show(null);
    expect(panelIsMounted()).toBe(true);

    slideEnds();
    expect(panelIsMounted()).toBe(false);
  });

  it("does not mount the panel if the drawer is closed again mid-slide", () => {
    show(KEY);
    show(null);
    slideEnds();

    expect(panelIsMounted()).toBe(false);
  });
});

// Restoring a panel used to be one capability's private business: writable_document
// shipped a `sessionProbes` entry and nothing else did, so the HTML viewer's open
// state was recorded and never read back. The host restores every declared panel
// from the same record, over the `useHasContent` each one already declares.
describe("CapabilitySidePanelHost — restoring whichever panel was left open", () => {
  let container: HTMLDivElement;
  let root: Root;

  const TEXT = "writable_document:writable_document_pane";
  const HTML = "html_artifact:html_artifact_pane";

  const mount = () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <CapabilitySidePanelHost
          capabilityIds={["writable_document"]}
          activeKey={null}
          onActiveKeyChange={() => undefined}
        />,
      );
    });
  };

  const rerender = () =>
    act(() => {
      root.render(
        <CapabilitySidePanelHost
          capabilityIds={["writable_document"]}
          activeKey={null}
          onActiveKeyChange={() => undefined}
        />,
      );
    });

  const requestedPanels = () =>
    dispatch.mock.calls.map(
      ([action]: [{ payload: { capabilityId: string; widget: string } }]) =>
        `${action.payload.capabilityId}:${action.payload.widget}`,
    );

  beforeEach(() => {
    vi.useFakeTimers();
    dispatch.mockClear();
    restore.sessionId = "session-1";
    restore.openPanels = [];
    hasContent.value = true;
    state.entries = [entry("writable_document", "edit_document"), entry("html_artifact", "html")];
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.useRealTimers();
  });

  it("restores the HTML viewer from the same record as the text one — no per-capability wiring", () => {
    restore.openPanels = [HTML];
    mount();

    expect(requestedPanels()).toEqual([HTML]);
  });

  it("restores only the panel that was left open", () => {
    restore.openPanels = [TEXT];
    mount();

    expect(requestedPanels()).toEqual([TEXT]);
  });

  it("restores nothing for a conversation with no record", () => {
    mount();

    expect(requestedPanels()).toEqual([]);
  });

  // Content arrives asynchronously — a list that has not landed, a card that has
  // not replayed. Concluding "nothing to show" on the first render would mean
  // never restoring anything.
  it("waits for the content rather than concluding it is absent", () => {
    restore.openPanels = [TEXT];
    hasContent.value = false;
    mount();

    expect(requestedPanels()).toEqual([]);

    hasContent.value = true;
    rerender();

    expect(requestedPanels()).toEqual([TEXT]);
  });

  it("decides once per conversation — a later content change does not re-open it", () => {
    restore.openPanels = [TEXT];
    mount();
    dispatch.mockClear();

    hasContent.value = false;
    rerender();
    hasContent.value = true;
    rerender();

    expect(requestedPanels()).toEqual([]);
  });

  // The detour matters: an intervening conversation that never had content takes
  // no decision, so remembering only which session was decided would leave the
  // marker on the first one and read the return as already handled.
  it("restores again on the way back, after a conversation that had nothing", () => {
    restore.openPanels = [TEXT];
    mount();
    dispatch.mockClear();

    restore.sessionId = "session-2";
    hasContent.value = false;
    rerender();

    restore.sessionId = "session-1";
    hasContent.value = true;
    rerender();

    expect(requestedPanels()).toEqual([TEXT]);
  });

  it("decides again for another conversation", () => {
    restore.openPanels = [TEXT];
    mount();
    dispatch.mockClear();

    restore.sessionId = "session-2";
    rerender();

    expect(requestedPanels()).toEqual([TEXT]);
  });
});
