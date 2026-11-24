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

// Pins the badge and its accessible name, polling only while the tab is visible,
// Escape closing the portaled popover onto the bell, and no tooltip over it.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const summaryMock = vi.fn();
const refetch = vi.fn();

vi.mock("../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useNotificationSummaryQuery: (...args: unknown[]) => summaryMock(...args),
}));
vi.mock("./NotificationsPopover", () => ({
  default: ({ id }: { id: string }) => <div id={id} role="dialog" />,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) => (options?.count === undefined ? key : `${key}:${options.count}`),
    i18n: { language: "en" },
  }),
}));

import NotificationsEntry from "./NotificationsEntry";
import { NOTIFICATION_POLL_INTERVAL_MS } from "./useNotificationSummary";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let visibility: DocumentVisibilityState = "visible";
let container: HTMLDivElement | null = null;
let root: Root | null = null;

function render(unseen: number) {
  summaryMock.mockReturnValue({ data: { unseen_count: unseen }, refetch });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<NotificationsEntry />));
  return container;
}

function setVisibility(next: DocumentVisibilityState) {
  visibility = next;
  act(() => document.dispatchEvent(new Event("visibilitychange")));
}

// Everything but the bell's icon ligature: the badge, when there is one.
const badgeText = (el: Element) => el.textContent?.replace("notifications", "");
const bell = (el: Element) => el.querySelector<HTMLButtonElement>("button[aria-haspopup]")!;
const lastOptions = () => summaryMock.mock.lastCall![1] as { skip: boolean; pollingInterval: number };

beforeEach(() => {
  visibility = "visible";
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => visibility });
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  vi.clearAllMocks();
});

describe("NotificationsEntry", () => {
  it("shows the unseen count as a badge and in the bell's name", () => {
    const el = render(3);

    expect(badgeText(el)).toBe("3");
    expect(bell(el).getAttribute("aria-label")).toBe("rework.mainNav.notificationsUnseen:3");
  });

  it("caps the badge at 99+", () => {
    const el = render(100);

    expect(badgeText(el)).toBe("99+");
  });

  it("shows no badge at zero", () => {
    const el = render(0);

    expect(badgeText(el)).toBe("");
    expect(bell(el).getAttribute("aria-label")).toBe("rework.mainNav.notifications");
  });

  it("stops polling while hidden and refreshes at once on return", () => {
    render(0);

    setVisibility("hidden");
    expect(lastOptions().pollingInterval).toBe(0);
    expect(refetch).not.toHaveBeenCalled();

    setVisibility("visible");
    expect(lastOptions().pollingInterval).toBe(NOTIFICATION_POLL_INTERVAL_MS);
    expect(refetch).toHaveBeenCalledOnce();
  });

  it("refreshes when the window regains focus", () => {
    render(0);

    act(() => window.dispatchEvent(new Event("focus")));

    expect(refetch).toHaveBeenCalledOnce();
  });

  it("sends nothing from a tab opened in the background until it is shown", () => {
    visibility = "hidden";
    render(0);

    expect(lastOptions()).toEqual({ skip: true, pollingInterval: 0 });

    setVisibility("visible");
    expect(lastOptions()).toEqual({ skip: false, pollingInterval: NOTIFICATION_POLL_INTERVAL_MS });
  });

  it("opens the popover outside the rail, and Escape closes it onto the bell", () => {
    const el = render(2);

    act(() => bell(el).click());
    const popover = document.querySelector('[role="dialog"]');
    expect(popover).not.toBeNull();
    // Portaled: page content later in the DOM cannot paint over it.
    expect(el.contains(popover)).toBe(false);
    expect(bell(el).getAttribute("aria-expanded")).toBe("true");

    act(() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(document.activeElement).toBe(bell(el));
  });

  it("closes on a click outside, not on one inside the popover", () => {
    const el = render(0);
    act(() => bell(el).click());

    act(() => document.querySelector('[role="dialog"]')!.dispatchEvent(new MouseEvent("mousedown", { bubbles: true })));
    expect(document.querySelector('[role="dialog"]')).not.toBeNull();

    act(() => document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true })));
    expect(document.querySelector('[role="dialog"]')).toBeNull();
  });

  it("hides the bell's tooltip while the popover is open", () => {
    const el = render(0);
    const hover = () => act(() => bell(el).dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));

    hover();
    expect(document.querySelector('[role="tooltip"]')).not.toBeNull();

    act(() => bell(el).click());
    expect(document.querySelector('[role="tooltip"]')).toBeNull();
    hover();
    expect(document.querySelector('[role="tooltip"]')).toBeNull();
  });
});
