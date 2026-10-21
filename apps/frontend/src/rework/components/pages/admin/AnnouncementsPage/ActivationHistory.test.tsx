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

// What these pin: the history is one line per exposure (type, title,
// activation, deactivation, author) in the API's newest-first order, with no
// action column; a patch-note line is named after its first note and how many
// follow, and reopens its package in the users' dialog without recording
// anything; the filter is by type and remembered.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AnnouncementExposure } from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";

const historyMock = vi.fn();
const usersMock = vi.fn();
const packageMock = vi.fn();
const seenMock = vi.fn();
const showError = vi.fn();
const showInfo = vi.fn();

vi.mock("../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements", () => ({
  useAnnouncementExposureHistoryQuery: () => historyMock(),
  useLazyPatchNotePackageQuery: () => [packageMock],
  useUsersByIdsQuery: (...args: unknown[]) => usersMock(...args),
  usePatchNoteHistoryQuery: () => ({ data: undefined }),
  useMarkPatchNoteAnnouncementSeenMutation: () => [seenMock],
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError, showInfo, showSuccess: vi.fn() }),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => (options ? `${key}:${JSON.stringify(options)}` : key),
    i18n: { language: "en" },
  }),
}));

import ActivationHistory from "./ActivationHistory";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function exposure(overrides: Partial<AnnouncementExposure> = {}): AnnouncementExposure {
  return {
    id: "e1",
    announcement_id: "a1",
    kind: "banner",
    label: { en: "Scheduled maintenance" },
    actor_uid: "u-alice",
    activated_at: "2026-10-09T08:00:00Z",
    ...overrides,
  };
}
const announcement = (overrides: Partial<AnnouncementExposure> = {}) =>
  exposure({ id: "n1", kind: "patch_note", label: { en: "Release 3.4" }, note_count: 3, ...overrides });

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
  document.getElementById("modal-portal")?.remove();
  vi.clearAllMocks();
});

// The DataTable has no table roles: rows are the body's direct children.
const rows = (el: HTMLElement) => [...el.querySelectorAll<HTMLElement>('[class*="datatable-body"] > div')];
const cells = (row: HTMLElement) => [...row.children].map((cell) => cell.textContent);
const buttonWith = (el: HTMLElement, label: string) =>
  [...el.querySelectorAll("button")].find((button) => button.textContent?.includes(label))!;
const openButton = (row: HTMLElement) =>
  row.querySelector<HTMLButtonElement>('[aria-label="rework.announcements.history.openPackage"]');
const when = (iso: string) => new Date(iso).toLocaleString("en", { dateStyle: "medium", timeStyle: "short" });
const HISTORY = "rework.announcements.history";

describe("ActivationHistory", () => {
  it("renders type, title, activation, deactivation and author, with no action column", () => {
    historyMock.mockReturnValue({ data: [exposure()], isLoading: false });

    const labels = [...render().querySelectorAll('[class*="datatable-header"] [class*="header-content"]')];

    expect(labels.map((label) => label.textContent)).toEqual([
      `${HISTORY}.column.type`,
      `${HISTORY}.column.title`,
      `${HISTORY}.column.activation`,
      `${HISTORY}.column.deactivation`,
      `${HISTORY}.column.by`,
      `${HISTORY}.column.open`,
    ]);
  });

  it("lists one line per exposure, newest first, with both dates and the author's name", () => {
    historyMock.mockReturnValue({
      data: [
        exposure({ id: "e2", actor_uid: "u-bob", activated_at: "2026-10-09T09:00:00Z" }),
        exposure({ id: "e1", label: { fr: "Maintenance" }, deactivated_at: "2026-10-09T08:30:00Z" }),
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
    // Still shown to users: the deactivation is empty.
    expect(cells(first)).toEqual([
      `${HISTORY}.type.banner`,
      "Scheduled maintenance",
      when("2026-10-09T09:00:00Z"),
      "",
      "bob",
      "",
    ]);
    // A French-only title still names the line for an English viewer.
    expect(cells(second).slice(1, 5)).toEqual([
      "Maintenance",
      when("2026-10-09T08:00:00Z"),
      when("2026-10-09T08:30:00Z"),
      "Alice Martin",
    ]);
  });

  it("names a patch-note line after its first note and how many follow", () => {
    historyMock.mockReturnValue({
      data: [announcement(), announcement({ id: "n0", note_count: 1 }), announcement({ id: "old", note_count: null })],
      isLoading: false,
    });

    const [several, single, old] = rows(render());

    expect(cells(several).slice(0, 2)).toEqual([
      `${HISTORY}.type.patch_note`,
      `${HISTORY}.more:${JSON.stringify({ title: "Release 3.4", count: 2 })}`,
    ]);
    expect(cells(single)[1]).toBe("Release 3.4");
    expect(cells(old)[1]).toBe("Release 3.4");
  });

  it("offers to open the package on a patch-note line that kept one, and on no other", () => {
    historyMock.mockReturnValue({
      data: [announcement(), announcement({ id: "old", note_count: null }), exposure()],
      isLoading: false,
    });

    const [withPackage, withoutPackage, banner] = rows(render());

    expect(openButton(withPackage)).not.toBeNull();
    expect(openButton(withoutPackage)).toBeNull();
    expect(openButton(banner)).toBeNull();
  });

  it("opens a line's package in the users' dialog, with its navigation, and records nothing", async () => {
    historyMock.mockReturnValue({ data: [announcement()], isLoading: false });
    packageMock.mockReturnValue({
      unwrap: () =>
        Promise.resolve([
          { id: "p2", title: { en: "Release 3.4" }, description_long: { en: "# Three point four" } },
          { id: "p1", title: { en: "Release 3.3" }, description_long: { en: "# Three point three" } },
        ]),
    });
    const el = render();

    await act(async () => openButton(rows(el)[0])!.click());

    expect(packageMock).toHaveBeenCalledExactlyOnceWith({ announcementId: "n1" }, true);
    const dialog = document.body.querySelector('[role="dialog"]')!;
    expect(dialog.querySelector("h1")?.textContent).toBe("Three point four");
    expect(dialog.querySelector("nav")?.textContent).toContain("1 / 2");

    act(() => void window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
    expect(seenMock).not.toHaveBeenCalled();
  });

  it("says so when the package cannot be read", async () => {
    historyMock.mockReturnValue({ data: [announcement()], isLoading: false });
    packageMock.mockReturnValue({ unwrap: () => Promise.reject({ status: 404 }) });
    const el = render();

    await act(async () => openButton(rows(el)[0])!.click());

    expect(showError).toHaveBeenCalledExactlyOnceWith({ summary: `${HISTORY}.packageFailed` });
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
  });

  it("says so when a package holds nothing readable", async () => {
    historyMock.mockReturnValue({ data: [announcement()], isLoading: false });
    packageMock.mockReturnValue({
      unwrap: () => Promise.resolve([{ id: "p1", title: {}, description_long: {} }]),
    });
    const el = render();

    await act(async () => openButton(rows(el)[0])!.click());

    expect(showInfo).toHaveBeenCalledExactlyOnceWith({ summary: `${HISTORY}.packageEmpty` });
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
  });

  it("colours a banner's type chip by its severity and keeps patch notes neutral", () => {
    historyMock.mockReturnValue({
      data: [exposure({ id: "e3", severity: "warning" }), exposure({ id: "e2", severity: null }), announcement()],
      isLoading: false,
    });

    const chips = rows(render()).map((row) => row.children[0].querySelector("span")!.className);

    expect(chips[0]).toContain("toneWarning");
    // Recorded before severity was kept: no colour to give it.
    expect(chips[1]).toContain("toneNeutral");
    expect(chips[2]).toContain("toneNeutral");
  });

  it("sorts by activation from the column header", () => {
    historyMock.mockReturnValue({
      data: [exposure({ id: "e2", activated_at: "2026-10-09T09:00:00Z" }), exposure({ id: "e1" })],
      isLoading: false,
    });
    const el = render();

    act(() => buttonWith(el, `${HISTORY}.column.activation`).click());

    expect(rows(el).map((row) => row.querySelector("time")?.getAttribute("dateTime"))).toEqual([
      "2026-10-09T08:00:00Z",
      "2026-10-09T09:00:00Z",
    ]);
  });

  it("filters by type and remembers the choice", () => {
    historyMock.mockReturnValue({ data: [announcement(), exposure()], isLoading: false });
    const el = render();
    expect(rows(el)).toHaveLength(2);

    act(() => buttonWith(el, `${HISTORY}.filter.patch_note`).click());
    expect(rows(el).map((row) => cells(row)[0])).toEqual([`${HISTORY}.type.patch_note`]);

    // A fresh mount starts on the remembered filter.
    act(() => root?.unmount());
    container?.remove();
    expect(rows(render())).toHaveLength(1);
  });

  it("names its filter group and ignores an unknown remembered filter", () => {
    historyMock.mockReturnValue({ data: [announcement(), exposure()], isLoading: false });
    const el = render();
    act(() => buttonWith(el, `${HISTORY}.filter.banner`).click());
    const key = Object.keys(window.localStorage).find((k) => k.endsWith("announcements.historyTypeFilter"))!;
    act(() => root?.unmount());
    container?.remove();

    window.localStorage.setItem(key, JSON.stringify("activated"));
    const fresh = render();

    expect(fresh.querySelector('[role="group"]')?.getAttribute("aria-label")).toBe(`${HISTORY}.filter.group`);
    expect(rows(fresh)).toHaveLength(2);
  });

  it("pages the lines, 20 per page", () => {
    historyMock.mockReturnValue({
      data: Array.from({ length: 25 }, (_, i) => exposure({ id: `e${i}` })),
      isLoading: false,
    });

    expect(rows(render())).toHaveLength(20);
  });

  it("falls back to the uid, and says when there is no author", () => {
    historyMock.mockReturnValue({
      data: [exposure({ id: "e2", actor_uid: "u-deleted" }), exposure({ id: "e1", actor_uid: null })],
      isLoading: false,
    });

    const [first, second] = rows(render());

    expect(cells(first)[4]).toBe("u-deleted");
    expect(cells(second)[4]).toBe(`${HISTORY}.unknownActor`);
  });

  it("shows the empty state", () => {
    historyMock.mockReturnValue({ data: [], isLoading: false });

    const el = render();

    expect(el.textContent).toContain(`${HISTORY}.empty`);
    expect(el.querySelector('[class*="datatable"]')).toBeNull();
    expect(usersMock).toHaveBeenCalledWith({ ids: [] }, { skip: true });
  });

  it("shows the error state", () => {
    historyMock.mockReturnValue({ data: undefined, isLoading: false, isError: true });

    const el = render();

    expect(el.textContent).toContain(`${HISTORY}.error`);
    expect(el.querySelector('[class*="datatable"]')).toBeNull();
  });
});
