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

// What these pin: announcing asks first and only then calls the server, it is
// unavailable while no patch note is visible, and the line beside the button
// says when and by whom it was last used, or nothing once it was cancelled.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Announcement } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const announcementMock = vi.fn();
const announceMock = vi.fn();
const usersMock = vi.fn();
const confirmMock = vi.fn();
const showError = vi.fn();
const showSuccess = vi.fn();

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePatchNoteAnnouncementQuery: () => announcementMock(),
  useAnnouncePatchNotesMutation: () => [announceMock, { isLoading: false }],
  useUsersByIdsQuery: (...args: unknown[]) => usersMock(...args),
}));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: confirmMock }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess, showError }),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => (options ? `${key}:${JSON.stringify(options)}` : key),
    i18n: { language: "en" },
  }),
}));

import PatchNoteAnnouncer from "./PatchNoteAnnouncer";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const note = (id: string, title: string) => ({ id, title: { en: title }, enabled: true }) as unknown as Announcement;
const VISIBLE = [note("p2", "What's new in 3.5"), note("p1", "What's new in 3.4")];
const ANNOUNCED_AT = "2026-10-12T14:03:00Z";

let container: HTMLDivElement | null = null;
let root: Root | null = null;

function render(visibleNotes = VISIBLE): HTMLDivElement {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<PatchNoteAnnouncer visibleNotes={visibleNotes} />));
  return container;
}

const button = () => container!.querySelector<HTMLButtonElement>("button")!;
const line = () => container!.querySelector("p")!.textContent;

beforeEach(() => {
  announcementMock.mockReturnValue({ data: null });
  usersMock.mockReturnValue({ data: [] });
  announceMock.mockReturnValue({ unwrap: () => Promise.resolve({}) });
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  vi.clearAllMocks();
});

describe("PatchNoteAnnouncer", () => {
  it("asks first, saying how many patch notes users get and which one opens", () => {
    render();

    act(() => button().click());

    expect(button().textContent).toContain("rework.announcements.patchNote.announce.action");
    expect(announceMock).not.toHaveBeenCalled();
    const options = confirmMock.mock.calls[0][0];
    expect(options.title).toBe("rework.announcements.patchNote.announce.confirm.title");
    expect(options.message).toBe(
      `rework.announcements.patchNote.announce.confirm.message:${JSON.stringify({ count: 2, title: "What's new in 3.5" })}`,
    );
    // Not a destructive action: the plain confirmation, not the critical one.
    expect(options.criticalAction).toBeUndefined();
  });

  it("announces once confirmed, and says so", async () => {
    render();
    act(() => button().click());

    await act(async () => confirmMock.mock.calls[0][0].onConfirm());

    expect(announceMock).toHaveBeenCalledOnce();
    expect(showSuccess).toHaveBeenCalledWith({ summary: "rework.announcements.patchNote.announce.done" });
  });

  it("announces nothing when the confirmation is cancelled", () => {
    render();
    act(() => button().click());

    // Cancelling only closes the dialog: there is no cancel callback to run.
    expect(confirmMock.mock.calls[0][0].onCancel).toBeUndefined();
    expect(announceMock).not.toHaveBeenCalled();
  });

  it("reports a refused announcement", async () => {
    announceMock.mockReturnValue({
      unwrap: () => Promise.reject({ status: 409, data: { detail: "nothing visible" } }),
    });
    render();
    act(() => button().click());

    await act(async () => confirmMock.mock.calls[0][0].onConfirm());

    expect(showError).toHaveBeenCalledWith({
      summary: "rework.announcements.patchNote.announce.failed",
      detail: "nothing visible",
    });
  });

  it("is unavailable while no patch note is visible, and says what to do", () => {
    render([]);

    expect(button().disabled).toBe(true);
    expect(line()).toBe("rework.announcements.patchNote.announce.noneVisible");
  });

  it("shows nothing beside the button when no announcement is in effect", () => {
    render();

    expect(button().disabled).toBe(false);
    expect(line()).toBe("");
  });

  it("shows when it was last used and the administrator's display name", () => {
    announcementMock.mockReturnValue({ data: { id: "ann-1", announced_at: ANNOUNCED_AT, announced_by: "u-alice" } });
    usersMock.mockReturnValue({
      data: [{ id: "u-alice", first_name: "Alice", last_name: "Martin", username: "amartin" }],
    });

    render();

    expect(usersMock).toHaveBeenCalledWith({ ids: ["u-alice"] }, { skip: false });
    expect(line()).toBe(
      `rework.announcements.patchNote.announce.lastUse:${JSON.stringify({
        date: new Date(ANNOUNCED_AT).toLocaleString("en", { dateStyle: "medium", timeStyle: "short" }),
        name: "Alice Martin",
      })}`,
    );
  });

  it("empties the line when the announcement is cancelled under it", () => {
    announcementMock.mockReturnValue({ data: { id: "ann-1", announced_at: ANNOUNCED_AT, announced_by: null } });
    render();
    expect(line()).toContain("rework.announcements.history.unknownActor");

    // Hiding the last visible note cancels the announcement; the read comes back empty.
    announcementMock.mockReturnValue({ data: null });
    act(() => root!.render(<PatchNoteAnnouncer visibleNotes={[]} />));

    expect(line()).toBe("rework.announcements.patchNote.announce.noneVisible");
  });
});
