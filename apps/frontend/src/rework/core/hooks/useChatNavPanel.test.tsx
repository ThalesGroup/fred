// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ChatNavPanelProvider, useChatNavPanel, useChatNavRoom } from "./useChatNavPanel";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let panel: ReturnType<typeof useChatNavPanel> & ReturnType<typeof useChatNavRoom>;
function Probe() {
  panel = { ...useChatNavPanel(), ...useChatNavRoom() };
  return null;
}

const root = createRoot(document.createElement("div"));

beforeEach(() => {
  localStorage.clear();
  act(() =>
    root.render(
      <ChatNavPanelProvider key={Math.random()}>
        <Probe />
      </ChatNavPanelProvider>,
    ),
  );
});
afterEach(() => act(() => root.render(null)));

describe("useChatNavPanel beside a viewer", () => {
  it("folds on a narrow chat body, comes back on release and persists nothing", () => {
    let gained = 0;
    act(() => {
      gained = panel.makeRoom(800);
    });
    expect(gained).toBe(254);
    expect(panel.collapsed).toBe(true);
    expect(localStorage.getItem("chat-nav-panel-collapsed")).not.toBe("true");

    act(() => panel.releaseRoom());
    expect(panel.collapsed).toBe(false);
  });

  it("stays open when the chat body is wide enough", () => {
    act(() => {
      expect(panel.makeRoom(900)).toBe(0);
    });
    expect(panel.collapsed).toBe(false);
  });

  it("keeps a panel the user folded after the viewer closes", () => {
    act(() => panel.toggle());
    act(() => {
      expect(panel.makeRoom(800)).toBe(0);
    });
    act(() => panel.releaseRoom());
    expect(panel.collapsed).toBe(true);
  });

  it("respects a panel reopened by hand beside the viewer", () => {
    act(() => {
      panel.makeRoom(800);
    });
    act(() => panel.toggle());
    expect(panel.collapsed).toBe(false);
    act(() => panel.releaseRoom());
    expect(panel.collapsed).toBe(false);
  });
});
