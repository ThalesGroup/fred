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

// What these pin: the gate opens the delivered note once per sign-in (per user)
// and edition, records a server dismissal only when the box is ticked, stays shut
// when the server flags the edition as dismissed, and survives throwing storage.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Announcement } from "../../../slices/controlPlane/controlPlaneOpenApi";

const queryMock = vi.fn();
const dismissMock = vi.fn();
const showError = vi.fn();
let language = "en";
let userId = "alice";
let claims: Record<string, unknown> = { sid: "login-1" };

vi.mock("../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useActivePatchNoteQuery: (...args: unknown[]) => queryMock(...args),
  useDismissPatchNoteMutation: () => [dismissMock],
}));
vi.mock("../../../security/KeycloakService", () => ({
  KeyCloakService: { GetUserId: () => userId, GetTokenParsed: () => claims },
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError }),
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
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-01T10:00:00Z",
    ...overrides,
  };
}

function deliver(note: Announcement | null, dismissed = false) {
  queryMock.mockReturnValue({ data: { patch_note: note, dismissed } });
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
const tickBox = () => act(() => document.body.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click());

const CLOSED_P1 = "fred.patchNote.closed.alice.login-1.p1.v1";

beforeEach(() => {
  language = "en";
  userId = "alice";
  claims = { sid: "login-1" };
  window.localStorage.clear();
  window.sessionStorage.clear();
  dismissMock.mockReturnValue({ unwrap: () => Promise.resolve(undefined) });
});

afterEach(() => {
  unmount();
  vi.restoreAllMocks();
  queryMock.mockReset();
  dismissMock.mockReset();
  showError.mockReset();
});

describe("PatchNoteGate", () => {
  it("titles the dialog with the note's title in the viewer's locale", () => {
    language = "fr";
    deliver(patchNote());
    mount();

    expect(dialog()!.textContent).toContain("Nouveautés 3.4");
  });

  it("opens at load when a note is delivered", () => {
    deliver(patchNote());
    mount();

    expect(dialog()).not.toBeNull();
    expect(heading()).toBe("Release 3.4");
    // One read per load: no polling interval, no refetch on focus.
    expect(queryMock.mock.calls[0]).toHaveLength(0);
  });

  it("stays closed when none is delivered", () => {
    deliver(null);
    mount();

    expect(dialog()).toBeNull();
  });

  it("stays closed when the user dismissed this edition", () => {
    deliver(patchNote(), true);
    mount();

    expect(dialog()).toBeNull();
  });

  it("opens again for a new edition of a note closed this session", () => {
    deliver(patchNote());
    mount();
    act(() => closeButton().click());
    unmount();

    deliver(patchNote({ content_version: 2 }));
    mount();

    expect(dialog()).not.toBeNull();
  });

  it("close without the box does not call the server and does not reopen on rerender", () => {
    deliver(patchNote());
    mount();

    act(() => closeButton().click());
    expect(dialog()).toBeNull();
    expect(dismissMock).not.toHaveBeenCalled();

    act(() => root!.render(<PatchNoteGate />));
    expect(dialog()).toBeNull();

    // Same sign-in, fresh mount (a reload or a new tab): still closed.
    unmount();
    mount();
    expect(dialog()).toBeNull();
  });

  it("close with the box records the dismissal", () => {
    deliver(patchNote());
    mount();

    tickBox();
    act(() => closeButton().click());

    expect(dismissMock).toHaveBeenCalledExactlyOnceWith({ announcementId: "p1" });
    expect(dialog()).toBeNull();
    expect(window.localStorage.getItem(CLOSED_P1)).not.toBeNull();
  });

  it("escape with the box ticked records the dismissal", () => {
    deliver(patchNote());
    mount();

    tickBox();
    act(() => void window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));

    expect(dismissMock).toHaveBeenCalledExactlyOnceWith({ announcementId: "p1" });
    expect(dialog()).toBeNull();
  });

  it("stays closed in a new tab of the same sign-in", () => {
    deliver(patchNote());
    mount();
    act(() => closeButton().click());
    unmount();

    window.sessionStorage.clear();
    mount();

    expect(dialog()).toBeNull();
  });

  it("reopens after a new sign-in", () => {
    deliver(patchNote());
    mount();
    act(() => closeButton().click());
    unmount();

    claims = { sid: "login-2" };
    mount();

    expect(dialog()).not.toBeNull();
  });

  it("opens for another user of the same browser", () => {
    deliver(patchNote());
    mount();
    act(() => closeButton().click());
    unmount();

    userId = "bob";
    mount();

    expect(dialog()).not.toBeNull();
  });

  it("opens a new patch note even when an older one was dismissed", () => {
    deliver(patchNote());
    mount();
    tickBox();
    act(() => closeButton().click());
    unmount();

    deliver(patchNote({ id: "p2", title: { en: "3.5" }, description_long: { en: "# Release 3.5" } }));
    mount();

    expect(dialog()).not.toBeNull();
    expect(heading()).toBe("Release 3.5");
  });

  it("keeps the session flag and shows an error when the dismissal fails", async () => {
    dismissMock.mockReturnValue({ unwrap: () => Promise.reject(new Error("boom")) });
    const consoleError = vi.spyOn(console, "error");
    deliver(patchNote());
    mount();

    tickBox();
    await act(async () => closeButton().click());

    expect(showError).toHaveBeenCalledExactlyOnceWith({
      summary: "rework.announcements.patchNote.dismissFailed",
    });
    expect(window.localStorage.getItem(CLOSED_P1)).not.toBeNull();
    expect(dialog()).toBeNull();
    expect(consoleError).not.toHaveBeenCalled();
  });

  it("works when storage throws", () => {
    // Blocked site data: reading the storage object itself throws a SecurityError.
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new Error("blocked");
    });
    deliver(patchNote());
    mount();

    expect(dialog()).not.toBeNull();
    act(() => closeButton().click());
    expect(dialog()).toBeNull();
    act(() => root!.render(<PatchNoteGate />));
    expect(dialog()).toBeNull();
  });

  it("shows the body in the UI language, falling back to English", () => {
    language = "fr";
    deliver(patchNote());
    mount();
    expect(heading()).toBe("Version 3.4");
    unmount();

    deliver(patchNote({ id: "p3", title: { en: "3.4" }, description_long: { en: "# Release 3.4" } }));
    mount();
    expect(heading()).toBe("Release 3.4");
  });
});
