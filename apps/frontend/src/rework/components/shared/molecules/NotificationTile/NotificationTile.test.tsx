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

// Pins what a click opens, the always
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
    dismissLabel: "Dismiss notification",
    viewLabel: "View",
    onView: vi.fn(),
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
  it("opens through its View button, placed before the actions", () => {
    const { el, props } = renderTile({ actions: [{ id: "accept", label: "Accept", onClick: vi.fn() }] });

    const labels = [...el.querySelectorAll(".actions button, [class*='actions'] button")].map((b) => b.textContent);
    expect(labels).toEqual(["View", "Accept"]);
    click([...el.querySelectorAll("button")].find((b) => b.textContent === "View"));

    expect(props.onView).toHaveBeenCalledOnce();
  });

  it("does nothing on a click on the card itself", () => {
    const { el, props } = renderTile();

    click(el.querySelector("li"));
    click(el.querySelector("p"));

    expect(props.onView).not.toHaveBeenCalled();
    expect(el.querySelector("p")?.closest("button")).toBeNull();
  });

  it("has no View button without one to show", () => {
    const { el } = renderTile({ viewLabel: undefined });

    expect([...el.querySelectorAll("button")].some((b) => b.textContent === "View")).toBe(false);
  });

  it("runs a button's own handler without opening the subject", () => {
    const onAction = vi.fn();
    const { el, props } = renderTile({ actions: [{ id: "open", label: "Open the agent", onClick: onAction }] });

    click([...el.querySelectorAll("button")].find((b) => b.textContent === "Open the agent"));

    expect(onAction).toHaveBeenCalledOnce();
    expect(props.onView).not.toHaveBeenCalled();
  });

  it("dismisses through its close button, present without hover", () => {
    const { el, props } = renderTile();

    const close = el.querySelector<HTMLButtonElement>('button[aria-label="Dismiss notification"]');
    expect(close).not.toBeNull();
    expect(close!.className).not.toMatch(/delete/);
    click(close);

    expect(props.onDismiss).toHaveBeenCalledOnce();
    expect(props.onView).not.toHaveBeenCalled();
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

  it("keeps the full title, body and handled line on hover once truncated", () => {
    const { el } = renderTile({ handledLabel: "Handled by Bob" });
    expect(el.querySelector('[title="Published agent changed"]')?.textContent).toBe("Published agent changed");
    expect(el.querySelector('[title="Léa changed the agent."]')?.textContent).toBe("Léa changed the agent.");
    expect(el.querySelector('[title="Handled by Bob"]')?.textContent).toBe("Handled by Bob");
  });

  it("puts its subtitle on a second truncated line, between the title and the body", () => {
    const { el } = renderTile({ title: "Purchasing", subtitle: "Alice Martin asked to join.", body: "Hello" });

    const lines = [...el.querySelectorAll("p")].map((p) => [p.textContent, p.getAttribute("title")]);
    expect(lines.slice(0, 3)).toEqual([
      ["Purchasing", "Purchasing"],
      ["Alice Martin asked to join.", "Alice Martin asked to join."],
      ["Hello", "Hello"],
    ]);
  });

  it("names its unread dot for screen readers, and has none once read", () => {
    const unread = renderTile({ unread: true, unreadLabel: "Unread" }).el;
    expect(unread.querySelector('[role="img"][aria-label="Unread"]')).not.toBeNull();
    act(() => root?.unmount());
    unread.remove();

    expect(renderTile().el.querySelector('[role="img"]')).toBeNull();
  });

  it("ties every button to its title for screen readers, and dates its time in full on hover", () => {
    const { el } = renderTile({
      dateTitle: "Tuesday, October 20, 2026 at 10:00 AM",
      actions: [{ id: "accept", label: "Accept", onClick: vi.fn() }],
    });

    const titleId = el.querySelector('[title="Published agent changed"]')!.id;
    expect(titleId).not.toBe("");
    const buttons = [...el.querySelectorAll("button")];
    expect(buttons).toHaveLength(3);
    for (const button of buttons) expect(button.getAttribute("aria-describedby")).toBe(titleId);
    expect(el.querySelector("time")?.getAttribute("title")).toBe("Tuesday, October 20, 2026 at 10:00 AM");
  });

  it("has no subtitle line without one", () => {
    const { el } = renderTile();

    expect(el.querySelectorAll("p")).toHaveLength(2);
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
