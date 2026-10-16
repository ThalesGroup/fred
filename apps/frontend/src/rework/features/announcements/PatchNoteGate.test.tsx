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
// @vitest-environment happy-dom

// What these pin: the gate opens the history only when an announcement is
// pending for this user at load, records that announcement as seen however the
// dialog is closed, and stays closed for the page view even if the record fails.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Announcement } from "../../../slices/controlPlane/controlPlaneOpenApi";

const queryMock = vi.fn();
const seenMock = vi.fn();
let language = "en";

vi.mock("../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePatchNoteHistoryQuery: (...args: unknown[]) => queryMock(...args),
  useMarkPatchNoteAnnouncementSeenMutation: () => [seenMock],
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language } }),
}));

import PatchNoteGate from "./PatchNoteGate";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function patchNote(overrides: Partial<Announcement> = {}): Announcement {
  return {
    id: "p1",
    kind: "patch_note",
    severity: "info",
    title: { en: "What's new in 3.4", fr: "Nouveautés 3.4" },
    description_short: {},
    description_long: { en: "# Release 3.4", fr: "# Version 3.4" },
    enabled: true,
    dismissible: true,
    content_version: 1,
    position: 1,
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-01T10:00:00Z",
    ...overrides,
  };
}

const older = () =>
  patchNote({ id: "p0", position: 2, title: { en: "What's new in 3.3" }, description_long: { en: "# Release 3.3" } });

function deliver(notes: Announcement[], pending: string | null = "ann-1") {
  queryMock.mockReturnValue({ data: { patch_notes: notes, pending_announcement_id: pending } });
}

let container: HTMLDivElement | null = null;
let root: Root | null = null;

function mount() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<PatchNoteGate />));
}

function unmount() {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  document.getElementById("modal-portal")?.remove();
}

const dialog = () => document.body.querySelector('[role="dialog"]');
const heading = () => document.body.querySelector("h1")?.textContent;
const closeButton = () =>
  [...document.body.querySelectorAll("button")].find((b) =>
    b.textContent?.includes("rework.announcements.dialog.close"),
  )!;

beforeEach(() => {
  language = "en";
  seenMock.mockReturnValue(Promise.resolve({ data: undefined }));
});

afterEach(() => {
  unmount();
  queryMock.mockReset();
  seenMock.mockReset();
});

describe("PatchNoteGate", () => {
  it("opens on the first note when an announcement is pending, with the navigation and no checkbox", () => {
    deliver([patchNote(), older()]);
    mount();

    expect(dialog()!.textContent).toContain("What's new in 3.4");
    expect(heading()).toBe("Release 3.4");
    expect(dialog()!.querySelector("nav")?.textContent).toContain("1 / 2");
    expect(dialog()!.querySelector('input[type="checkbox"]')).toBeNull();
    // One read per load: no polling interval, no refetch on focus.
    expect(queryMock.mock.calls[0]).toHaveLength(0);
  });

  it("stays closed when no announcement is pending", () => {
    deliver([patchNote()], null);
    mount();

    expect(dialog()).toBeNull();
  });

  it("stays closed when nothing is visible, and while the history is loading", () => {
    deliver([]);
    mount();
    expect(dialog()).toBeNull();
    unmount();

    queryMock.mockReturnValue({ data: undefined });
    mount();
    expect(dialog()).toBeNull();
  });

  it("records the announcement as seen on Close, and does not reopen", () => {
    deliver([patchNote()]);
    mount();

    act(() => closeButton().click());

    expect(seenMock).toHaveBeenCalledExactlyOnceWith({ announcementId: "ann-1" });
    expect(dialog()).toBeNull();
    act(() => root!.render(<PatchNoteGate />));
    expect(dialog()).toBeNull();
  });

  it("records it on Escape too", () => {
    deliver([patchNote()]);
    mount();

    act(() => void window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));

    expect(seenMock).toHaveBeenCalledExactlyOnceWith({ announcementId: "ann-1" });
    expect(dialog()).toBeNull();
  });

  it("records the announcement that opened it, whichever note the user moved to", () => {
    deliver([patchNote(), older()]);
    mount();

    act(() =>
      document.body
        .querySelector<HTMLButtonElement>('[aria-label="rework.announcements.patchNote.dialog.older"]')!
        .click(),
    );
    expect(heading()).toBe("Release 3.3");
    act(() => closeButton().click());

    expect(seenMock).toHaveBeenCalledExactlyOnceWith({ announcementId: "ann-1" });
  });

  it("keeps showing, and records, the announcement it opened on when a newer one is read meanwhile", () => {
    deliver([patchNote()]);
    mount();

    deliver([older()], "ann-2");
    act(() => root!.render(<PatchNoteGate />));
    expect(dialog()!.textContent).toContain("What's new in 3.4");
    act(() => closeButton().click());

    // "ann-2" was never shown: it stays pending for the next load.
    expect(seenMock).toHaveBeenCalledExactlyOnceWith({ announcementId: "ann-1" });
  });

  it("stays closed for the page view when the record fails", async () => {
    // RTK's trigger resolves with the error rather than rejecting.
    seenMock.mockReturnValue(Promise.resolve({ error: { status: 500 } }));
    const consoleError = vi.spyOn(console, "error");
    deliver([patchNote()]);
    mount();

    await act(async () => closeButton().click());
    act(() => root!.render(<PatchNoteGate />));

    expect(dialog()).toBeNull();
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it("does not open for an announcement made during this page view", () => {
    deliver([patchNote()], null);
    mount();

    // The administrator's own mutations refresh the history under the gate.
    deliver([patchNote()], "ann-2");
    act(() => root!.render(<PatchNoteGate />));

    expect(dialog()).toBeNull();
    expect(seenMock).not.toHaveBeenCalled();
  });

  it("shows title and body in the UI language, falling back to English", () => {
    language = "fr";
    deliver([patchNote()]);
    mount();
    expect(dialog()!.textContent).toContain("Nouveautés 3.4");
    expect(heading()).toBe("Version 3.4");
    unmount();

    deliver([patchNote({ id: "p3", title: { en: "3.4" }, description_long: { en: "# Release 3.4" } })]);
    mount();
    expect(heading()).toBe("Release 3.4");
  });
});
