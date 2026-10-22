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

// Pins the unread mark (visible and spoken), what a click opens, the always
// visible close button, busy buttons and the handled line.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import NotificationTile, { type NotificationTileProps } from "./NotificationTile";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement | null = null;
let root: Root | null = null;

function renderTile(overrides: Partial<NotificationTileProps> = {}) {
  const props: NotificationTileProps = {
    icon: "sync_problem",
    category: "action_required",
    title: "Published agent changed",
    body: "Léa changed the agent.",
    time: "5 min ago",
    dateTime: "2026-10-20T10:00:00Z",
    unread: true,
    unreadLabel: "Unread",
    dismissLabel: "Dismiss notification",
    onOpen: vi.fn(),
    onDismiss: vi.fn(),
    ...overrides,
  };
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() =>
    root!.render(
      <ul>
        <NotificationTile {...props} />
      </ul>,
    ),
  );
  return { props, el: container };
}

const click = (element: Element | null | undefined) => act(() => (element as HTMLElement).click());

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
});

describe("NotificationTile", () => {
  it("marks an unread tile, with an accessible prefix on its title", () => {
    const { el } = renderTile();

    expect(el.querySelector("li")?.hasAttribute("data-unread")).toBe(true);
    expect(el.querySelector("li button")?.textContent).toBe("Unread: Published agent changed");
  });

  it("drops the unread style and prefix once read", () => {
    const { el } = renderTile({ unread: false });

    expect(el.querySelector("li")?.hasAttribute("data-unread")).toBe(false);
    expect(el.querySelector("li button")?.textContent).toBe("Published agent changed");
  });

  it("opens on a click on its title", () => {
    const { el, props } = renderTile();

    click(el.querySelector("li button"));

    expect(props.onOpen).toHaveBeenCalledOnce();
  });

  it("runs a button's own handler without opening the tile", () => {
    const onAction = vi.fn();
    const { el, props } = renderTile({ actions: [{ id: "open", label: "Open the agent", onClick: onAction }] });

    const button = [...el.querySelectorAll("button")].find((b) => b.textContent === "Open the agent");
    click(button);

    expect(onAction).toHaveBeenCalledOnce();
    expect(props.onOpen).not.toHaveBeenCalled();
  });

  it("dismisses through its close button, present without hover", () => {
    const { el, props } = renderTile();

    const close = el.querySelector<HTMLButtonElement>('button[aria-label="Dismiss notification"]');
    expect(close).not.toBeNull();
    expect(close!.className).not.toMatch(/delete/);
    click(close);

    expect(props.onDismiss).toHaveBeenCalledOnce();
    expect(props.onOpen).not.toHaveBeenCalled();
  });

  it("disables its buttons while busy", () => {
    const onAction = vi.fn();
    const { el } = renderTile({ busy: true, actions: [{ id: "accept", label: "Accept", onClick: onAction }] });

    const button = [...el.querySelectorAll("button")].find((b) => b.textContent === "Accept")!;
    expect(button.disabled).toBe(true);
    click(button);
    expect(onAction).not.toHaveBeenCalled();
  });

  it("has no close button while it waits for a decision", () => {
    const { el } = renderTile({ dismissible: false });

    expect(el.querySelector('button[aria-label="Dismiss notification"]')).toBeNull();
  });

  it("shows who handled it instead of its buttons", () => {
    const { el } = renderTile({
      handledLabel: "Handled by Bob",
      actions: [{ id: "open", label: "Open the agent", onClick: vi.fn() }],
    });

    expect(el.textContent).toContain("Handled by Bob");
    expect(el.textContent).not.toContain("Open the agent");
  });
});
