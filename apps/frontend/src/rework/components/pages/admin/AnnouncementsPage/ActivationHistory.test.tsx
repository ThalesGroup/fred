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

// What these pin: the history is a five-column table that keeps the API's
// newest-first order, colours a banner's type by its severity, names the actor
// through /users/by-ids and still shows the uid when that user is gone, filters
// by action and remembers that filter; loading, error and empty states replace it.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AnnouncementActivationEvent } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const historyMock = vi.fn();
const usersMock = vi.fn();

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useAnnouncementActivationHistoryQuery: () => historyMock(),
  useUsersByIdsQuery: (...args: unknown[]) => usersMock(...args),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en" },
  }),
}));

import ActivationHistory from "./ActivationHistory";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function event(overrides: Partial<AnnouncementActivationEvent> = {}): AnnouncementActivationEvent {
  return {
    id: "e1",
    announcement_id: "a1",
    kind: "banner",
    label: { en: "Scheduled maintenance" },
    action: "activated",
    actor_uid: "u-alice",
    occurred_at: "2026-10-09T08:00:00Z",
    ...overrides,
  };
}

let container: HTMLDivElement | null = null;
let root: Root | null = null;

function render(): HTMLDivElement {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<ActivationHistory />));
  return container;
}

beforeEach(() => {
  usersMock.mockReturnValue({ data: [] });
});

afterEach(() => {
  window.localStorage.clear();
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  vi.clearAllMocks();
});

// The DataTable has no table roles: rows are the body's direct children.
const rows = (el: HTMLElement) => [...el.querySelectorAll<HTMLElement>('[class*="datatable-body"] > div')];
const cells = (row: HTMLElement) => [...row.children].map((cell) => cell.textContent);
const buttonWith = (el: HTMLElement, label: string) =>
  [...el.querySelectorAll("button")].find((button) => button.textContent?.includes(label))!;

describe("ActivationHistory", () => {
  it("renders the five columns", () => {
    historyMock.mockReturnValue({ data: [event()], isLoading: false });

    const labels = [...render().querySelectorAll('[class*="datatable-header"] [class*="header-content"]')];

    expect(labels.map((label) => label.textContent)).toEqual([
      "rework.announcements.history.column.announcement",
      "rework.announcements.history.column.type",
      "rework.announcements.history.column.action",
      "rework.announcements.history.column.date",
      "rework.announcements.history.column.by",
    ]);
  });

  it("lists events newest first with type, action, date and actor names", () => {
    historyMock.mockReturnValue({
      data: [
        event({ id: "e2", action: "deactivated", actor_uid: "u-bob", occurred_at: "2026-10-09T09:00:00Z" }),
        event({ id: "e1", kind: "patch_note", label: { fr: "Version 3.4" } }),
      ],
      isLoading: false,
    });
    usersMock.mockReturnValue({
      data: [
        { id: "u-alice", first_name: "Alice", last_name: "Martin" },
        { id: "u-bob", username: "bob" },
      ],
    });

    const [first, second] = rows(render());

    expect(usersMock).toHaveBeenCalledWith({ ids: ["u-bob", "u-alice"] }, { skip: false });
    expect(cells(first)).toEqual([
      "Scheduled maintenance",
      "rework.announcements.kind.banner",
      "visibility_offrework.announcements.history.deactivated",
      new Date("2026-10-09T09:00:00Z").toLocaleString("en", { dateStyle: "medium", timeStyle: "short" }),
      "bob",
    ]);
    // A French-only label still names the patch note for an English viewer.
    expect(cells(second)[0]).toBe("Version 3.4");
    expect(cells(second)[1]).toBe("rework.announcements.kind.patch_note");
    expect(cells(second)[2]).toBe("visibilityrework.announcements.history.activated");
    expect(cells(second)[4]).toBe("Alice Martin");
    expect(second.querySelector("time")?.getAttribute("dateTime")).toBe("2026-10-09T08:00:00Z");
  });

  it("colours a banner's type chip by its severity and keeps patch notes neutral", () => {
    historyMock.mockReturnValue({
      data: [
        event({ id: "e3", severity: "warning" }),
        event({ id: "e2", severity: null }),
        event({ id: "e1", kind: "patch_note", severity: null }),
      ],
      isLoading: false,
    });

    const chips = rows(render()).map((row) => row.children[1].querySelector("span")!.className);

    expect(chips[0]).toContain("toneWarning");
    // Recorded before severity was kept: no colour to give it.
    expect(chips[1]).toContain("toneNeutral");
    expect(chips[2]).toContain("toneNeutral");
  });

  it("sorts by date from the column header", () => {
    historyMock.mockReturnValue({
      data: [event({ id: "e2", occurred_at: "2026-10-09T09:00:00Z" }), event({ id: "e1" })],
      isLoading: false,
    });
    const el = render();
    const dateHeader = buttonWith(el, "rework.announcements.history.column.date");

    act(() => dateHeader.click());

    expect(rows(el).map((row) => row.querySelector("time")?.getAttribute("dateTime"))).toEqual([
      "2026-10-09T08:00:00Z",
      "2026-10-09T09:00:00Z",
    ]);
  });

  it("filters by action and remembers the choice", () => {
    historyMock.mockReturnValue({
      data: [event({ id: "e2", action: "deactivated" }), event({ id: "e1" })],
      isLoading: false,
    });
    const el = render();
    expect(rows(el)).toHaveLength(2);

    act(() => buttonWith(el, "rework.announcements.history.filter.activated").click());
    expect(rows(el).map((row) => row.querySelector("[data-action]")?.getAttribute("data-action"))).toEqual([
      "activated",
    ]);

    // A fresh mount starts on the remembered filter.
    act(() => root?.unmount());
    container?.remove();
    expect(rows(render())).toHaveLength(1);
  });

  it("names its filter group and ignores an unknown remembered filter", () => {
    historyMock.mockReturnValue({
      data: [event({ id: "e2", action: "deactivated" }), event({ id: "e1" })],
      isLoading: false,
    });
    const el = render();
    act(() => buttonWith(el, "rework.announcements.history.filter.activated").click());
    const key = Object.keys(window.localStorage).find((k) => k.endsWith("announcements.historyActionFilter"))!;
    act(() => root?.unmount());
    container?.remove();

    window.localStorage.setItem(key, JSON.stringify("archived"));
    const fresh = render();

    expect(fresh.querySelector('[role="group"]')?.getAttribute("aria-label")).toBe(
      "rework.announcements.history.filter.group",
    );
    expect(rows(fresh)).toHaveLength(2);
  });

  it("pages the events, 20 per page", () => {
    historyMock.mockReturnValue({
      data: Array.from({ length: 25 }, (_, i) => event({ id: `e${i}` })),
      isLoading: false,
    });

    expect(rows(render())).toHaveLength(20);
  });

  it("falls back to the uid, and says when there is no actor", () => {
    historyMock.mockReturnValue({
      data: [event({ id: "e2", actor_uid: "u-deleted" }), event({ id: "e1", actor_uid: null })],
      isLoading: false,
    });

    const [first, second] = rows(render());

    expect(cells(first)[4]).toBe("u-deleted");
    expect(cells(second)[4]).toBe("rework.announcements.history.unknownActor");
  });

  it("shows the empty state", () => {
    historyMock.mockReturnValue({ data: [], isLoading: false });

    const el = render();

    expect(el.textContent).toContain("rework.announcements.history.empty");
    expect(el.querySelector('[class*="datatable"]')).toBeNull();
    expect(usersMock).toHaveBeenCalledWith({ ids: [] }, { skip: true });
  });

  it("shows the error state", () => {
    historyMock.mockReturnValue({ data: undefined, isLoading: false, isError: true });

    const el = render();

    expect(el.textContent).toContain("rework.announcements.history.error");
    expect(el.querySelector('[class*="datatable"]')).toBeNull();
  });
});
