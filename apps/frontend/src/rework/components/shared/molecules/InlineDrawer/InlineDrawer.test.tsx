// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import { InlineDrawer } from "./InlineDrawer";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

it("sizes an opening on the parent width plus what onOpening frees", () => {
  localStorage.clear();
  window.innerWidth = 4000;
  const parent = document.createElement("div");
  Object.defineProperty(parent, "clientWidth", { value: 1000 });
  document.body.appendChild(parent);
  const root = createRoot(parent);
  const onOpening = vi.fn(() => 254);

  act(() =>
    root.render(
      <InlineDrawer
        open
        onClose={() => {}}
        title="Viewer"
        layout="push"
        resizable={{ persistKey: "test-drawer", openFraction: 0.5, maxViewportFraction: 1, onOpening }}
      >
        content
      </InlineDrawer>,
    ),
  );

  expect(onOpening).toHaveBeenCalledWith(1000);
  expect(parent.innerHTML).toContain("627px");
  act(() => root.unmount());
  parent.remove();
});

it("keeps a rail launcher available when its content is collapsed", () => {
  const parent = document.createElement("div");
  document.body.appendChild(parent);
  const root = createRoot(parent);
  const onOpen = vi.fn();
  const onClose = vi.fn();
  const render = (open: boolean) =>
    act(() =>
      root.render(
        <InlineDrawer
          open={open}
          onOpen={onOpen}
          onClose={onClose}
          title="File browser"
          layout="rail"
          railExpandLabel="Open file browser"
          railCollapseLabel="Collapse file browser"
        >
          Folder tree
        </InlineDrawer>,
      ),
    );

  render(true);
  expect(parent.textContent).toContain("Folder tree");
  act(() => parent.querySelector<HTMLButtonElement>('button[aria-label="Collapse file browser"]')!.click());
  expect(onClose).toHaveBeenCalledOnce();

  render(false);
  expect(parent.querySelector("aside")?.hasAttribute("aria-hidden")).toBe(false);
  expect(parent.textContent).not.toContain("Folder tree");
  act(() => parent.querySelector<HTMLButtonElement>('button[aria-label="Open file browser"]')!.click());
  expect(onOpen).toHaveBeenCalledOnce();

  render(true);
  expect(parent.textContent).toContain("Folder tree");
  act(() => root.unmount());
  parent.remove();
});

it("omits an opted-in collapsed launcher and lets the host reclaim focus", () => {
  const parent = document.createElement("div");
  document.body.appendChild(parent);
  const root = createRoot(parent);
  let opener: HTMLButtonElement | null = null;
  const onClose = vi.fn(() => opener?.focus());
  const render = (open: boolean) =>
    act(() =>
      root.render(
        <>
          <button
            ref={(node) => {
              opener = node;
            }}
          >
            Open file browser
          </button>
          <InlineDrawer open={open} onClose={onClose} title="File browser" layout="rail" hideRailLauncher>
            Folder tree
          </InlineDrawer>
        </>,
      ),
    );
  render(false);
  expect(parent.querySelector("aside")?.getAttribute("aria-hidden")).toBe("true");
  expect(parent.querySelector("aside button")).toBeNull();
  render(true);
  act(() => parent.querySelector<HTMLButtonElement>("aside button")!.click());
  expect(onClose).toHaveBeenCalledOnce();
  expect(document.activeElement).toBe(opener);
  act(() => root.unmount());
  parent.remove();
});
