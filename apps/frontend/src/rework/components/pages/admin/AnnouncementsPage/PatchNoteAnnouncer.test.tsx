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

// What these pin: announcing first shows the included patch notes, numbered in
// their order, and only then calls the server; it is unavailable while nothing
// is included. The line beside the button says when and by whom it was last
// used, and withdrawing, offered only while an announcement is in effect, asks
// through the critical confirmation.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import en from "../../../../../locales/en/translation.json";
import fr from "../../../../../locales/fr/translation.json";
import type { Announcement } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const announcementMock = vi.fn();
const announceMock = vi.fn();
const withdrawMock = vi.fn();
const usersMock = vi.fn();
const confirmMock = vi.fn();
const showError = vi.fn();
const showSuccess = vi.fn();

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePatchNoteAnnouncementQuery: () => announcementMock(),
  useAnnouncePatchNotesMutation: () => [announceMock, { isLoading: false }],
  useWithdrawPatchNoteAnnouncementMutation: () => [withdrawMock, { isLoading: false }],
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

import PatchNoteAnnouncer, { MAX_PATCH_NOTES_PER_ANNOUNCEMENT } from "./PatchNoteAnnouncer";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const note = (id: string, title: string) => ({ id, title: { en: title }, enabled: true }) as unknown as Announcement;
const INCLUDED = [note("p2", "What's new in 3.5"), note("p1", "What's new in 3.4")];
const ANNOUNCED_AT = "2026-10-12T14:03:00Z";
const KEYS = "rework.announcements.patchNote.announce";

let container: HTMLDivElement | null = null;
let root: Root | null = null;

const onSelectionChanged = vi.fn();

function render(includedNotes = INCLUDED, settling = false): HTMLDivElement {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() =>
    root!.render(
      <PatchNoteAnnouncer includedNotes={includedNotes} settling={settling} onSelectionChanged={onSelectionChanged} />,
    ),
  );
  return container;
}

const buttonWith = (el: ParentNode, label: string) =>
  [...el.querySelectorAll("button")].find((b) => b.textContent?.includes(label));
const announceButton = () => buttonWith(container!, `${KEYS}.action`)!;
const withdrawButton = () => buttonWith(container!, `${KEYS}.withdraw.action`);
const line = () => container!.querySelector("p")!.textContent;
const confirmation = () => document.body.querySelector<HTMLElement>('[role="alertdialog"]');
const inEffect = () =>
  announcementMock.mockReturnValue({ data: { id: "ann-1", announced_at: ANNOUNCED_AT, announced_by: "u-alice" } });

beforeEach(() => {
  announcementMock.mockReturnValue({ data: null });
  usersMock.mockReturnValue({ data: [] });
  announceMock.mockReturnValue({ unwrap: () => Promise.resolve({}) });
  withdrawMock.mockReturnValue({ unwrap: () => Promise.resolve(undefined) });
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  document.getElementById("modal-portal")?.remove();
  vi.clearAllMocks();
});

describe("PatchNoteAnnouncer", () => {
  it("asks first, listing the included patch notes in their order", () => {
    render();

    act(() => announceButton().click());

    expect(announceMock).not.toHaveBeenCalled();
    expect(confirmation()!.textContent).toContain(`${KEYS}.confirm.title`);
    expect(confirmation()!.textContent).toContain(`${KEYS}.confirm.message`);
    expect([...confirmation()!.querySelectorAll("ol > li")].map((item) => item.textContent)).toEqual([
      "What's new in 3.5",
      "What's new in 3.4",
    ]);
    // Not destructive: the confirm button is the filled primary one.
    expect(buttonWith(confirmation()!, `${KEYS}.confirm.confirm`)!.className).toMatch(/btn-filled/);
  });

  it("announces once confirmed, and says so", async () => {
    render();
    act(() => announceButton().click());

    await act(async () => buttonWith(confirmation()!, `${KEYS}.confirm.confirm`)!.click());

    // The ids of the list just confirmed, in its order: the server freezes those or refuses.
    expect(announceMock.mock.calls).toEqual([[{ patchNoteAnnounceRequest: { ids: ["p2", "p1"] } }]]);
    expect(confirmation()).toBeNull();
    expect(showSuccess).toHaveBeenCalledWith({ summary: `${KEYS}.done` });
  });

  it("announces nothing when the confirmation is cancelled", () => {
    render();
    act(() => announceButton().click());

    act(() => buttonWith(confirmation()!, "common.cancel")!.click());

    expect(confirmation()).toBeNull();
    expect(announceMock).not.toHaveBeenCalled();
  });

  it("reports a failed announcement", async () => {
    announceMock.mockReturnValue({
      unwrap: () => Promise.reject({ status: 500, data: { detail: "boom" } }),
    });
    render();
    act(() => announceButton().click());

    await act(async () => buttonWith(confirmation()!, `${KEYS}.confirm.confirm`)!.click());

    expect(showError).toHaveBeenCalledWith({ summary: `${KEYS}.failed`, detail: "boom" });
    expect(onSelectionChanged).not.toHaveBeenCalled();
  });

  it("reloads the list and says the selection changed when the server refuses the confirmed one", async () => {
    announceMock.mockReturnValue({
      unwrap: () => Promise.reject({ status: 409, data: { detail: "the included patch notes changed" } }),
    });
    render();
    act(() => announceButton().click());

    await act(async () => buttonWith(confirmation()!, `${KEYS}.confirm.confirm`)!.click());

    expect(onSelectionChanged).toHaveBeenCalledOnce();
    expect(showError).toHaveBeenCalledWith({ summary: `${KEYS}.changed` });
    expect(showSuccess).not.toHaveBeenCalled();
  });

  it("waits for a toggle or a reorder under way before it can announce", () => {
    render(INCLUDED, true);

    expect(announceButton().disabled).toBe(true);
  });

  it("is unavailable above the most an announcement holds, and says to deselect some", () => {
    const eleven = Array.from({ length: MAX_PATCH_NOTES_PER_ANNOUNCEMENT + 1 }, (_, index) => note(`p${index}`, "N"));
    inEffect();

    render(eleven);

    expect(announceButton().disabled).toBe(true);
    expect(line()).toBe(`${KEYS}.tooMany:{"max":${MAX_PATCH_NOTES_PER_ANNOUNCEMENT}}`);
    act(() => root!.render(<PatchNoteAnnouncer includedNotes={eleven.slice(1)} />));
    expect(announceButton().disabled).toBe(false);
  });

  it("is unavailable while no patch note is included, and says what to do", () => {
    render([]);

    expect(announceButton().disabled).toBe(true);
    expect(line()).toBe(`${KEYS}.noneVisible`);
  });

  it("shows no last use and no withdraw action when no announcement is in effect", () => {
    render();

    expect(announceButton().disabled).toBe(false);
    expect(line()).toBe("");
    expect(withdrawButton()).toBeUndefined();
  });

  it("shows when it was last used and the administrator's display name", () => {
    inEffect();
    usersMock.mockReturnValue({
      data: [{ id: "u-alice", first_name: "Alice", last_name: "Martin", username: "amartin" }],
    });

    render();

    expect(usersMock).toHaveBeenCalledWith({ ids: ["u-alice"] }, { skip: false });
    expect(line()).toBe(
      `${KEYS}.lastUse:${JSON.stringify({
        date: new Date(ANNOUNCED_AT).toLocaleString("en", { dateStyle: "medium", timeStyle: "short" }),
        name: "Alice Martin",
      })}`,
    );
  });

  it("keeps the last use in view when nothing is included any more", () => {
    // The announcement in effect is a frozen package: excluding every note does not end it.
    inEffect();

    render([]);

    expect(line()).toContain(`${KEYS}.lastUse`);
    expect(withdrawButton()).toBeDefined();
    expect(announceButton().disabled).toBe(true);
  });

  it("offers to withdraw as a secondary action, and asks through the critical confirmation", () => {
    inEffect();
    render();

    expect(withdrawButton()!.className).toMatch(/btn-text/);
    act(() => withdrawButton()!.click());

    expect(withdrawMock).not.toHaveBeenCalled();
    const options = confirmMock.mock.calls[0][0];
    expect([options.criticalAction, options.title, options.message]).toEqual([
      true,
      `${KEYS}.withdraw.title`,
      `${KEYS}.withdraw.message`,
    ]);
    // Cancelling only closes the dialog: there is no cancel callback to run.
    expect(options.onCancel).toBeUndefined();
  });

  it("withdraws once confirmed, and says so", async () => {
    inEffect();
    render();
    act(() => withdrawButton()!.click());

    await act(async () => confirmMock.mock.calls[0][0].onConfirm());

    expect(withdrawMock).toHaveBeenCalledOnce();
    expect(showSuccess).toHaveBeenCalledWith({ summary: `${KEYS}.withdraw.done` });
  });

  it("tells the administrator what announcing and withdrawing do, in French and English", () => {
    for (const locale of [fr, en]) {
      const { confirm, withdraw } = locale.rework.announcements.patchNote.announce;
      for (const text of [...Object.values(confirm), ...Object.values(withdraw)]) expect(text.trim()).not.toBe("");
    }
  });
});
