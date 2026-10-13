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

// What these pin: toggling a row goes through the dedicated enabled endpoint
// rather than a full content update, which would bump a banner's
// content_version and bring it back for every user. Deleting asks
// first, because an announcement is not recoverable. And the header reports
// how many banners are actually live, the number an admin loses track of.
// Patch notes share the list in a neutral row whose preview is the users'
// dialog itself, and never records a dismissal. One create button asks for the
// type first, and the history is a second view holding a full-width table.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Announcement } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const listMock = vi.fn();
const createMock = vi.fn();
const updateMock = vi.fn();
const setEnabledMock = vi.fn();
const deleteMock = vi.fn();
const confirmMock = vi.fn();
const showError = vi.fn();
const showSuccess = vi.fn();
const refetchMock = vi.fn();
const dismissMock = vi.fn();
const historyMock = vi.fn();

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useAnnouncementsQuery: () => listMock(),
  useCreateAnnouncementMutation: () => [createMock, { isLoading: false }],
  useUpdateAnnouncementMutation: () => [updateMock, { isLoading: false }],
  useSetAnnouncementEnabledMutation: () => [setEnabledMock, { isLoading: false }],
  useDeleteAnnouncementMutation: () => [deleteMock, { isLoading: false }],
  useDismissPatchNoteMutation: () => [dismissMock, { isLoading: false }],
  useAnnouncementActivationHistoryQuery: () => historyMock(),
  useUsersByIdsQuery: () => ({ data: [] }),
}));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: confirmMock }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess, showError, showInfo: vi.fn(), showWarning: vi.fn() }),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && "count" in options ? `${key}:${options.count}` : key,
    i18n: { language: "en" },
  }),
}));
// The editors have their own tests; these are about the list and the view switch.
vi.mock("./AnnouncementEditorDialog", () => ({
  default: ({ announcement }: { announcement: Announcement | null }) => (
    <div data-testid="editor" data-id={announcement?.id ?? "new"} />
  ),
}));
const patchNoteEditor = vi.hoisted(() => ({
  props: null as null | {
    onSave: (payload: Record<string, unknown>, activate: boolean) => void;
    replacesTitle?: string;
  },
}));
vi.mock("./PatchNoteEditorDialog", () => ({
  default: (props: { announcement: Announcement | null } & NonNullable<typeof patchNoteEditor.props>) => {
    patchNoteEditor.props = props;
    return <div data-testid="patch-note-editor" data-id={props.announcement?.id ?? "new"} />;
  },
}));

import AnnouncementsPage from "./AnnouncementsPage";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function announcement(overrides: Partial<Announcement> = {}): Announcement {
  return {
    id: "a1",
    kind: "banner",
    severity: "info",
    title: { en: "Scheduled maintenance" },
    description_short: { en: "Down on Sunday." },
    description_long: {},
    enabled: false,
    dismissible: true,
    content_version: 1,
    created_at: "2026-09-01T10:00:00Z",
    updated_at: "2026-09-01T10:00:00Z",
    ...overrides,
  };
}

let container: HTMLDivElement | null = null;
let root: Root | null = null;

function render(): HTMLDivElement {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<AnnouncementsPage />));
  return container;
}

function patchNote(overrides: Partial<Announcement> = {}): Announcement {
  return announcement({
    id: "p1",
    kind: "patch_note",
    title: { en: "What's new in 3.4" },
    description_short: {},
    description_long: { en: "# Release 3.4 (2026-10-09)\n\n- Faster search" },
    ...overrides,
  });
}

const buttonWith = (el: HTMLElement, label: string) =>
  [...el.querySelectorAll("button")].filter((b) => b.textContent?.includes(label));

beforeEach(() => {
  listMock.mockReturnValue({ data: [], isLoading: false, refetch: refetchMock });
  historyMock.mockReturnValue({
    data: [
      {
        id: "e1",
        announcement_id: "p1",
        kind: "patch_note",
        label: { en: "Release 3.4" },
        action: "activated",
        actor_uid: "u-alice",
        occurred_at: "2026-10-09T08:00:00Z",
      },
    ],
    isLoading: false,
  });
  setEnabledMock.mockReturnValue({ unwrap: () => Promise.resolve({}) });
  deleteMock.mockReturnValue({ unwrap: () => Promise.resolve({}) });
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  document.getElementById("modal-portal")?.remove();
  vi.clearAllMocks();
});

describe("AnnouncementsPage", () => {
  it("offers to create one when there is nothing yet", () => {
    const el = render();

    expect(el.textContent).toContain("rework.announcements.page.empty");
  });

  it("lists each announcement with its title and short description", () => {
    listMock.mockReturnValue({ data: [announcement()], isLoading: false, refetch: refetchMock });

    const el = render();

    expect(el.textContent).toContain("Scheduled maintenance");
    expect(el.textContent).toContain("Down on Sunday.");
  });

  it("reports how many banners are live, not how many exist", () => {
    // The active patch note is left out: users may have dismissed it.
    listMock.mockReturnValue({
      data: [
        announcement({ id: "a1", enabled: true }),
        announcement({ id: "a2", enabled: false }),
        patchNote({ enabled: true }),
      ],
      isLoading: false,
    });

    expect(render().textContent).toContain("rework.announcements.page.subtitle:1");
  });

  it("previews each announcement with the real banner component", () => {
    // Not a lookalike styled to match: the admin has to be able to trust that
    // this is what users will get, which only holds if it is the same code.
    listMock.mockReturnValue({
      data: [announcement({ severity: "error", description_long: { en: "The full story." } })],
      isLoading: false,
    });

    const el = render();

    expect(el.querySelector('[data-severity="error"]')).not.toBeNull();
    // The banner's own actions render too, so the admin sees what users get.
    expect(el.textContent).toContain("rework.announcements.banner.moreInfo");
    expect(el.querySelector('[aria-label="rework.announcements.banner.dismiss"]')).not.toBeNull();
  });

  it("says which way the switch goes, and that it lands for every user", () => {
    // The switch carries no visible label, so the hint is the only place that
    // spells out the reach of the flick — and it has to follow the state.
    listMock.mockReturnValue({ data: [announcement({ enabled: false })], isLoading: false });
    const el = render();
    const trigger = el.querySelector('[aria-label="rework.announcements.row.enabled"]')!.closest("span")!;

    act(() => void trigger.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));

    expect(document.body.textContent).toContain("rework.announcements.row.enableHint");
    expect(document.body.textContent).not.toContain("rework.announcements.row.disableHint");
  });

  it("offers a single creation action", () => {
    listMock.mockReturnValue({ data: [announcement()], isLoading: false, refetch: refetchMock });
    const el = render();

    expect(buttonWith(el, "rework.announcements.page.create")).toHaveLength(1);
  });

  it("empty state shows no duplicate action", () => {
    // The header button is always there; an action in the empty state would
    // be the same button, said twice. The other two are the view switch.
    const el = render();

    expect(el.textContent).toContain("rework.announcements.page.empty");
    expect([...el.querySelectorAll("button")].map((b) => b.textContent)).toEqual([
      "campaignrework.announcements.page.create",
      "rework.announcements.view.announcements",
      "rework.announcements.view.history",
    ]);
  });

  it("renders a patch note row with its title and four controls", () => {
    listMock.mockReturnValue({ data: [patchNote()], isLoading: false, refetch: refetchMock });
    const el = render();
    const row = el.querySelector('[data-kind="patch_note"]')!;

    expect(row.textContent).toContain("What's new in 3.4");
    expect(row.textContent).not.toContain("Release 3.4");
    expect(row.textContent).toContain("rework.announcements.kind.patch_note");
    for (const label of ["enabled", "preview", "edit", "delete"]) {
      expect(row.querySelector(`[aria-label="rework.announcements.row.${label}"]`)).not.toBeNull();
    }
    // No banner is rendered for a patch note.
    expect(row.querySelector("[data-severity]")).toBeNull();
  });

  it("says how many users chose to hide the patch note", () => {
    listMock.mockReturnValue({
      data: [{ ...patchNote(), dismissal_count: 12 }],
      isLoading: false,
      refetch: refetchMock,
    });
    const row = render().querySelector('[data-kind="patch_note"]')!;

    expect(row.textContent).toContain("rework.announcements.patchNote.dismissalCount:12");
  });

  it("names the active patch note that enabling another one switches off", () => {
    listMock.mockReturnValue({
      data: [patchNote({ id: "p1", enabled: true, title: { en: "Version 3.3" } }), patchNote({ id: "p2" })],
      isLoading: false,
      refetch: refetchMock,
    });
    const el = render();
    const switches = el.querySelectorAll<HTMLInputElement>('[aria-label="rework.announcements.row.enabled"]');

    act(() => switches[1].click());

    expect(setEnabledMock).not.toHaveBeenCalled();
    const options = confirmMock.mock.calls[0][0];
    expect(options.title).toBe("rework.announcements.patchNote.activate.title");
    act(() => void options.onConfirm());
    expect(setEnabledMock).toHaveBeenCalledWith({
      announcementId: "p2",
      setAnnouncementEnabledRequest: { enabled: true },
    });
  });

  it("enables a patch note at once when none is active", () => {
    listMock.mockReturnValue({ data: [patchNote()], isLoading: false, refetch: refetchMock });
    const el = render();

    act(() => el.querySelector<HTMLInputElement>('[aria-label="rework.announcements.row.enabled"]')!.click());

    expect(confirmMock).not.toHaveBeenCalled();
    expect(setEnabledMock).toHaveBeenCalledOnce();
  });

  it("disables a row's switch while its toggle is saving, and only that row's", async () => {
    let settle!: () => void;
    setEnabledMock.mockReturnValue({ unwrap: () => new Promise<void>((resolve) => (settle = resolve)) });
    listMock.mockReturnValue({ data: [announcement({ id: "a1" }), announcement({ id: "a2" })], isLoading: false });
    const el = render();
    const switches = () => el.querySelectorAll<HTMLInputElement>('[aria-label="rework.announcements.row.enabled"]');

    act(() => switches()[0].click());
    expect([...switches()].map((s) => s.disabled)).toEqual([true, false]);

    await act(async () => settle());
    expect(switches()[0].disabled).toBe(false);
  });

  it("keeps the switch disabled while the activation is being confirmed", () => {
    listMock.mockReturnValue({
      data: [patchNote({ id: "p1", enabled: true }), patchNote({ id: "p2" })],
      isLoading: false,
    });
    const el = render();
    const second = () => el.querySelectorAll<HTMLInputElement>('[aria-label="rework.announcements.row.enabled"]')[1];

    act(() => second().click());
    expect(second().disabled).toBe(true);

    act(() => confirmMock.mock.calls[0][0].onCancel());
    expect(second().disabled).toBe(false);
  });

  it("keeps the switch disabled during save and activate", async () => {
    let settle!: () => void;
    updateMock.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    setEnabledMock.mockReturnValue({ unwrap: () => new Promise<void>((resolve) => (settle = resolve)) });
    listMock.mockReturnValue({ data: [patchNote()], isLoading: false });
    const el = render();
    const toggle = () => el.querySelector<HTMLInputElement>('[aria-label="rework.announcements.row.enabled"]')!;
    act(() => el.querySelector<HTMLButtonElement>('[aria-label="rework.announcements.row.edit"]')!.click());

    await act(async () => patchNoteEditor.props!.onSave({ kind: "patch_note" }, true));
    expect(toggle().disabled).toBe(true);

    await act(async () => settle());
    expect(toggle().disabled).toBe(false);
  });

  it("save and activate saves the note, then switches it on, and says so", async () => {
    updateMock.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    listMock.mockReturnValue({
      data: [patchNote({ id: "p1", enabled: true, title: { en: "Version 3.3" } }), patchNote({ id: "p2" })],
      isLoading: false,
      refetch: refetchMock,
    });
    const el = render();
    act(() => el.querySelectorAll<HTMLButtonElement>('[aria-label="rework.announcements.row.edit"]')[1].click());
    expect(patchNoteEditor.props!.replacesTitle).toBe("Version 3.3");

    await act(async () => patchNoteEditor.props!.onSave({ kind: "patch_note" }, true));

    expect(updateMock).toHaveBeenCalledWith(expect.objectContaining({ announcementId: "p2" }));
    expect(setEnabledMock).toHaveBeenCalledWith({
      announcementId: "p2",
      setAnnouncementEnabledRequest: { enabled: true },
    });
    expect(showSuccess).toHaveBeenCalledWith({ summary: "rework.announcements.patchNote.savedActive" });
  });

  it("tells the admin a saved patch note is not active yet", async () => {
    createMock.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    const el = render();
    act(() => buttonWith(el, "rework.announcements.page.create")[0].click());
    act(() => document.body.querySelectorAll<HTMLButtonElement>("button[data-selected]")[1].click());

    await act(async () => patchNoteEditor.props!.onSave({ kind: "patch_note", enabled: false }, false));

    expect(createMock).toHaveBeenCalledWith({ announcementWriteRequest: { kind: "patch_note", enabled: false } });
    expect(setEnabledMock).not.toHaveBeenCalled();
    expect(showSuccess).toHaveBeenCalledWith({ summary: "rework.announcements.patchNote.savedInactive" });
  });

  it("banner rows are unchanged", () => {
    listMock.mockReturnValue({ data: [announcement(), patchNote()], isLoading: false, refetch: refetchMock });
    const el = render();
    const bannerRow = el.querySelector("li:not([data-kind])")!;

    expect(bannerRow.querySelector("[data-severity]")).not.toBeNull();
    expect(bannerRow.querySelector('[aria-label="rework.announcements.row.preview"]')).toBeNull();
    expect(bannerRow.querySelector('[aria-label="rework.announcements.row.edit"]')).not.toBeNull();
  });

  it("preview opens the user dialog and records no dismissal", () => {
    listMock.mockReturnValue({ data: [patchNote()], isLoading: false, refetch: refetchMock });
    const el = render();

    act(() => el.querySelector<HTMLButtonElement>('[aria-label="rework.announcements.row.preview"]')!.click());

    const dialog = document.body.querySelector('[role="dialog"]')!;
    expect(dialog.textContent).toContain("What's new in 3.4");
    expect(dialog.querySelector("h1")?.textContent).toBe("Release 3.4 (2026-10-09)");

    act(() => dialog.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click());
    act(() => buttonWith(dialog as HTMLElement, "rework.announcements.dialog.close")[0].click());

    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
    expect(dismissMock).not.toHaveBeenCalled();
  });

  it("a conflicting activation shows an error and leaves the refresh to tag invalidation", async () => {
    listMock.mockReturnValue({ data: [patchNote()], isLoading: false, refetch: refetchMock });
    setEnabledMock.mockReturnValue({ unwrap: () => Promise.reject({ status: 409, data: { detail: "conflict" } }) });
    const el = render();

    await act(async () =>
      el.querySelector<HTMLInputElement>('[aria-label="rework.announcements.row.enabled"]')!.click(),
    );

    expect(showError).toHaveBeenCalledWith(expect.objectContaining({ summary: "rework.announcements.toggleFailed" }));
    // RTK Query invalidates the LIST tag on a rejected mutation too.
    expect(refetchMock).not.toHaveBeenCalled();
  });

  it("edit opens the editor matching the type", () => {
    listMock.mockReturnValue({ data: [announcement(), patchNote()], isLoading: false, refetch: refetchMock });
    const el = render();
    const edits = el.querySelectorAll<HTMLButtonElement>('[aria-label="rework.announcements.row.edit"]');

    act(() => edits[1].click());
    expect(el.querySelector('[data-testid="patch-note-editor"]')?.getAttribute("data-id")).toBe("p1");
    expect(el.querySelector('[data-testid="editor"]')).toBeNull();

    act(() => edits[0].click());
    expect(el.querySelector('[data-testid="editor"]')?.getAttribute("data-id")).toBe("a1");
    expect(el.querySelector('[data-testid="patch-note-editor"]')).toBeNull();
  });

  it("toggles through the dedicated enabled endpoint, not a content update", () => {
    listMock.mockReturnValue({ data: [announcement()], isLoading: false, refetch: refetchMock });
    const el = render();
    const toggle = el.querySelector<HTMLInputElement>('[aria-label="rework.announcements.row.enabled"]');

    // React maps a checkbox's onChange onto the click event, not a synthetic
    // "change" — dispatching the latter reaches no handler at all.
    act(() => toggle!.click());

    expect(setEnabledMock).toHaveBeenCalledWith({
      announcementId: "a1",
      setAnnouncementEnabledRequest: { enabled: true },
    });
    // A toggle must never go through the content update — that would bump
    // content_version and resurrect every dismissed banner.
    expect(updateMock).not.toHaveBeenCalled();
  });

  it("asks before deleting, and does not delete until confirmed", () => {
    listMock.mockReturnValue({ data: [announcement()], isLoading: false, refetch: refetchMock });
    const el = render();
    const remove = el.querySelector<HTMLButtonElement>('[aria-label="rework.announcements.row.delete"]');

    act(() => remove!.click());

    expect(confirmMock).toHaveBeenCalledTimes(1);
    expect(deleteMock).not.toHaveBeenCalled();

    const options = confirmMock.mock.calls[0][0];
    expect(options.criticalAction).toBe(true);
    act(() => void options.onConfirm());

    expect(deleteMock).toHaveBeenCalledWith({ announcementId: "a1" });
  });

  describe("type chooser", () => {
    const openChooser = (el: HTMLElement) => {
      act(() => buttonWith(el, "rework.announcements.page.create")[0].click());
      return document.body.querySelector<HTMLElement>('[role="dialog"]')!;
    };
    const tiles = (dialog: HTMLElement) => [...dialog.querySelectorAll<HTMLButtonElement>("button[data-selected]")];

    it("offers exactly two tiles, banner and patch note, each with a description", () => {
      const dialog = openChooser(render());

      expect(dialog.textContent).toContain("rework.announcements.chooser.title");
      expect(tiles(dialog).map((tile) => tile.textContent)).toEqual([
        "campaignrework.announcements.kind.bannerrework.announcements.chooser.bannerDescription",
        "new_releasesrework.announcements.kind.patch_noterework.announcements.chooser.patchNoteDescription",
      ]);
      // A tile acts at once; it is not a toggle with a pressed state.
      expect(tiles(dialog).every((tile) => !tile.hasAttribute("aria-pressed"))).toBe(true);
    });

    it("the banner tile closes the chooser and opens the banner editor", () => {
      const el = render();

      const dialog = openChooser(el);
      act(() => tiles(dialog)[0].click());

      expect(document.body.querySelector('[role="dialog"]')).toBeNull();
      expect(el.querySelector('[data-testid="editor"]')?.getAttribute("data-id")).toBe("new");
      expect(el.querySelector('[data-testid="patch-note-editor"]')).toBeNull();
    });

    it("the patch-note tile closes the chooser and opens the patch-note editor", () => {
      const el = render();

      const dialog = openChooser(el);
      act(() => tiles(dialog)[1].click());

      expect(document.body.querySelector('[role="dialog"]')).toBeNull();
      expect(el.querySelector('[data-testid="patch-note-editor"]')?.getAttribute("data-id")).toBe("new");
      expect(el.querySelector('[data-testid="editor"]')).toBeNull();
    });

    it("its only action is a text Cancel, like other dialogs' cancel", () => {
      const dialog = openChooser(render());
      const actions = [...dialog.querySelectorAll("button:not([data-selected])")];

      expect(actions.map((button) => button.textContent)).toEqual(["common.cancel"]);
      expect(actions[0].className).toMatch(/btn-text/);
    });

    it("escape closes the chooser without opening an editor", () => {
      const el = render();
      const dialog = openChooser(el);
      // The first tile has the focus, so Enter or Space picks it like any button.
      expect(document.activeElement).toBe(tiles(dialog)[0]);

      act(() => void window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));

      expect(document.body.querySelector('[role="dialog"]')).toBeNull();
      expect(el.querySelector('[data-testid="editor"]')).toBeNull();
      expect(el.querySelector('[data-testid="patch-note-editor"]')).toBeNull();
    });
  });

  it("switches between the announcements and the history table", () => {
    listMock.mockReturnValue({ data: [announcement()], isLoading: false, refetch: refetchMock });
    const el = render();
    const tab = (view: string) =>
      [...el.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find(
        (button) => button.textContent === `rework.announcements.view.${view}`,
      )!;
    const columnLabels = () => [...el.querySelectorAll('[class*="header-content"]')].map((label) => label.textContent);

    // Announcements first, with the create button; no table yet.
    expect(tab("announcements").getAttribute("aria-selected")).toBe("true");
    expect(el.querySelector("li")).not.toBeNull();
    expect(buttonWith(el, "rework.announcements.page.create")).toHaveLength(1);
    expect(columnLabels()).toEqual([]);

    act(() => tab("history").click());

    expect(tab("history").getAttribute("aria-selected")).toBe("true");
    expect(el.querySelector("li")).toBeNull();
    expect(buttonWith(el, "rework.announcements.page.create")).toHaveLength(0);
    expect(columnLabels()).toEqual([
      "rework.announcements.history.column.announcement",
      "rework.announcements.history.column.type",
      "rework.announcements.history.column.action",
      "rework.announcements.history.column.date",
      "rework.announcements.history.column.by",
    ]);
    expect(el.textContent).toContain("Release 3.4");

    act(() => tab("announcements").click());

    expect(el.querySelector("li")).not.toBeNull();
    expect(buttonWith(el, "rework.announcements.page.create")).toHaveLength(1);
    expect(columnLabels()).toEqual([]);
  });
});
