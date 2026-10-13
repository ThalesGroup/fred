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
// Banners and patch notes each have their tab, their empty state and their
// create button; a patch note's switch only decides whether the next announcement includes it,
// so it never asks, and its preview is the users' dialog with that single note.

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
const seenMock = vi.fn();
const historyMock = vi.fn();

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useAnnouncementsQuery: () => listMock(),
  useCreateAnnouncementMutation: () => [createMock, { isLoading: false }],
  useUpdateAnnouncementMutation: () => [updateMock, { isLoading: false }],
  useSetAnnouncementEnabledMutation: () => [setEnabledMock, { isLoading: false }],
  useDeleteAnnouncementMutation: () => [deleteMock, { isLoading: false }],
  useMarkPatchNoteAnnouncementSeenMutation: () => [seenMock, { isLoading: false }],
  useSetPatchNoteOrderMutation: () => [vi.fn(), { isLoading: false }],
  useAnnouncementExposureHistoryQuery: () => historyMock(),
  useLazyPatchNotePackageQuery: () => [vi.fn()],
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
// The editors, the reorderable list's drag and drop and the announce action
// have their own tests; these are about the tabs and what each row does.
vi.mock("./AnnouncementEditorDialog", () => ({
  default: ({ announcement }: { announcement: Announcement | null }) => (
    <div data-testid="editor" data-id={announcement?.id ?? "new"} />
  ),
}));
const patchNoteEditor = vi.hoisted(() => ({
  props: null as null | {
    onSave: (payload: Record<string, unknown>, activate: boolean) => void;
  },
}));
vi.mock("./PatchNoteAnnouncer", () => ({
  default: (props: { includedNotes: Announcement[]; settling?: boolean; onSelectionChanged?: () => void }) => (
    <button
      data-testid="announcer"
      data-included={props.includedNotes.map((note) => note.id).join()}
      data-settling={props.settling || undefined}
      onClick={props.onSelectionChanged}
    />
  ),
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
const tab = (el: HTMLElement, view: string) =>
  [...el.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find(
    (button) => button.textContent === `rework.announcements.view.${view}`,
  )!;
/** Renders the page on its Patch notes tab. */
function renderPatchNotes(): HTMLDivElement {
  const el = render();
  act(() => tab(el, "patchNotes").click());
  return el;
}
const ROW = "rework.announcements.row";
const NOTE_ROW = "rework.announcements.patchNote.row";
const NOTE_CHECKBOX = '[data-kind="patch_note"] input[type="checkbox"]';

beforeEach(() => {
  listMock.mockReturnValue({ data: [], isLoading: false, refetch: refetchMock });
  historyMock.mockReturnValue({
    data: [
      {
        id: "e1",
        announcement_id: "p1",
        kind: "patch_note",
        label: { en: "Release 3.4" },
        note_count: 1,
        actor_uid: "u-alice",
        activated_at: "2026-10-09T08:00:00Z",
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
  it("offers three tabs, banners first, then patch notes, then the history", () => {
    const el = render();

    expect([...el.querySelectorAll('[role="tab"]')].map((button) => button.textContent)).toEqual([
      "rework.announcements.view.banners",
      "rework.announcements.view.patchNotes",
      "rework.announcements.view.history",
    ]);
    expect(tab(el, "banners").getAttribute("aria-selected")).toBe("true");
  });

  it("lists banners only in the banners tab, with title and short description", () => {
    listMock.mockReturnValue({ data: [announcement(), patchNote()], isLoading: false, refetch: refetchMock });

    const el = render();

    expect(el.textContent).toContain("Scheduled maintenance");
    expect(el.textContent).toContain("Down on Sunday.");
    expect(el.querySelectorAll("li")).toHaveLength(1);
    expect(el.querySelector('[data-kind="patch_note"]')).toBeNull();
    expect(el.querySelector('[data-testid="announcer"]')).toBeNull();
  });

  it("lists patch notes only in the patch notes tab, in the order served", () => {
    listMock.mockReturnValue({
      data: [
        announcement(),
        patchNote({ id: "p2", position: 1, title: { en: "What's new in 3.5" } }),
        patchNote({ id: "p1", position: 2 }),
      ],
      isLoading: false,
    });

    const el = renderPatchNotes();

    expect([...el.querySelectorAll("li")].map((row) => row.querySelector('[class*="title"]')?.textContent)).toEqual([
      "What's new in 3.5",
      "What's new in 3.4",
    ]);
    expect(el.querySelector("[data-severity]")).toBeNull();
  });

  it("gives each tab its own empty state, whatever the other holds", () => {
    listMock.mockReturnValue({ data: [announcement()], isLoading: false });
    const el = render();
    expect(el.textContent).not.toContain("rework.announcements.page.emptyBanners");

    act(() => tab(el, "patchNotes").click());
    expect(el.textContent).toContain("rework.announcements.page.emptyPatchNotes");
    // An announcement can outlive its patch notes: withdrawing stays reachable.
    expect(el.querySelector('[data-testid="announcer"]')?.getAttribute("data-included")).toBe("");

    act(() => tab(el, "banners").click());
    expect(el.querySelectorAll("li")).toHaveLength(1);
  });

  it("holds the announce action while the list reloads, and reloads it when the server refuses a stale one", () => {
    listMock.mockReturnValue({ data: [patchNote()], isLoading: false, isFetching: true, refetch: refetchMock });
    const el = renderPatchNotes();
    const announcer = el.querySelector<HTMLButtonElement>('[data-testid="announcer"]')!;

    expect(announcer.dataset.settling).toBe("true");
    act(() => announcer.click());

    expect(refetchMock).toHaveBeenCalledOnce();
  });

  it("empty state shows no duplicate action", () => {
    // The header button is always there; an action in the empty state would
    // be the same button, said twice. The other three are the tabs.
    const el = render();

    expect(el.textContent).toContain("rework.announcements.page.emptyBanners");
    expect([...el.querySelectorAll("button")].map((b) => b.textContent)).toEqual([
      "addrework.announcements.page.createBanner",
      "rework.announcements.view.banners",
      "rework.announcements.view.patchNotes",
      "rework.announcements.view.history",
    ]);
  });

  it("creates the kind of its tab, with no choice to make", () => {
    const el = render();

    act(() => buttonWith(el, "rework.announcements.page.createBanner")[0].click());
    expect(el.querySelector('[data-testid="editor"]')?.getAttribute("data-id")).toBe("new");
    expect(el.querySelector('[data-testid="patch-note-editor"]')).toBeNull();
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();

    act(() => tab(el, "patchNotes").click());
    expect(buttonWith(el, "rework.announcements.page.createBanner")).toHaveLength(0);
    act(() => buttonWith(el, "rework.announcements.page.createPatchNote")[0].click());
    expect(el.querySelector('[data-testid="patch-note-editor"]')?.getAttribute("data-id")).toBe("new");
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
  });

  it("reports how many banners are live, not how many exist", () => {
    // Patch notes are left out: a visible one is read on demand, not shown to everyone.
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

  it("previews each banner with the real banner component", () => {
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
    const trigger = el.querySelector(`[aria-label="${ROW}.enabled"]`)!.closest("span")!;

    act(() => void trigger.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));

    expect(document.body.textContent).toContain(`${ROW}.enableHint`);
    expect(document.body.textContent).not.toContain(`${ROW}.disableHint`);
  });

  it("renders a patch note card with its handle and switch at the left, then its title, state and actions", () => {
    listMock.mockReturnValue({ data: [patchNote({ enabled: true })], isLoading: false, refetch: refetchMock });
    const row = renderPatchNotes().querySelector('[data-kind="patch_note"]')!;

    expect(row.textContent).toContain("What's new in 3.4");
    expect(row.textContent).not.toContain("Release 3.4");
    expect(row.textContent).toContain(`${NOTE_ROW}.statusIncluded`);
    // The checkbox has no label of its own: the title and status beside it name it.
    expect([...row.querySelectorAll("button, input")].map((control) => control.getAttribute("aria-label"))).toEqual([
      `${NOTE_ROW}.move`,
      null,
      `${NOTE_ROW}.preview`,
      `${NOTE_ROW}.edit`,
      `${NOTE_ROW}.delete`,
    ]);
    expect(row.querySelector<HTMLInputElement>(NOTE_CHECKBOX)!.checked).toBe(true);
    const checkbox = row.querySelector<HTMLInputElement>(NOTE_CHECKBOX)!;
    expect(row.querySelector(`label[for="${checkbox.id}"]`)!.textContent).toContain("What's new in 3.4");
    // No banner is rendered for a patch note.
    expect(row.querySelector("[data-severity]")).toBeNull();
  });

  it("includes a second patch note at once, without asking and without touching the first", () => {
    listMock.mockReturnValue({
      data: [patchNote({ id: "p1", enabled: true }), patchNote({ id: "p2" })],
      isLoading: false,
      refetch: refetchMock,
    });
    const el = renderPatchNotes();
    const switches = el.querySelectorAll<HTMLInputElement>(NOTE_CHECKBOX);

    act(() => switches[1].click());

    expect(confirmMock).not.toHaveBeenCalled();
    expect(setEnabledMock).toHaveBeenCalledExactlyOnceWith({
      announcementId: "p2",
      setAnnouncementEnabledRequest: { enabled: true },
    });
  });

  it("hands the announce action the included patch notes, in order", () => {
    listMock.mockReturnValue({
      data: [patchNote({ id: "p3", enabled: true }), patchNote({ id: "p2" }), patchNote({ id: "p1", enabled: true })],
      isLoading: false,
    });

    const el = renderPatchNotes();

    expect(el.querySelector('[data-testid="announcer"]')?.getAttribute("data-included")).toBe("p3,p1");
  });

  it("disables a row's switch while its toggle is saving, and only that row's", async () => {
    let settle!: () => void;
    setEnabledMock.mockReturnValue({ unwrap: () => new Promise<void>((resolve) => (settle = resolve)) });
    listMock.mockReturnValue({ data: [announcement({ id: "a1" }), announcement({ id: "a2" })], isLoading: false });
    const el = render();
    const switches = () => el.querySelectorAll<HTMLInputElement>(`[aria-label="${ROW}.enabled"]`);

    act(() => switches()[0].click());
    expect([...switches()].map((s) => s.disabled)).toEqual([true, false]);

    await act(async () => settle());
    expect(switches()[0].disabled).toBe(false);
  });

  it("keeps the switch disabled during save and make visible", async () => {
    let settle!: () => void;
    updateMock.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    setEnabledMock.mockReturnValue({ unwrap: () => new Promise<void>((resolve) => (settle = resolve)) });
    listMock.mockReturnValue({ data: [patchNote()], isLoading: false });
    const el = renderPatchNotes();
    const toggle = () => el.querySelector<HTMLInputElement>(NOTE_CHECKBOX)!;
    act(() => el.querySelector<HTMLButtonElement>(`[aria-label="${NOTE_ROW}.edit"]`)!.click());

    await act(async () => patchNoteEditor.props!.onSave({ kind: "patch_note" }, true));
    expect(toggle().disabled).toBe(true);

    await act(async () => settle());
    expect(toggle().disabled).toBe(false);
  });

  it("save and make visible saves the note, then switches it on, and says so", async () => {
    updateMock.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    listMock.mockReturnValue({
      data: [patchNote({ id: "p1", enabled: true }), patchNote({ id: "p2" })],
      isLoading: false,
      refetch: refetchMock,
    });
    const el = renderPatchNotes();
    act(() => el.querySelectorAll<HTMLButtonElement>(`[aria-label="${NOTE_ROW}.edit"]`)[1].click());

    await act(async () => patchNoteEditor.props!.onSave({ kind: "patch_note" }, true));

    expect(updateMock).toHaveBeenCalledWith(expect.objectContaining({ announcementId: "p2" }));
    // Only the saved note is switched: the other visible one is left alone.
    expect(setEnabledMock).toHaveBeenCalledExactlyOnceWith({
      announcementId: "p2",
      setAnnouncementEnabledRequest: { enabled: true },
    });
    expect(showSuccess).toHaveBeenCalledWith({ summary: "rework.announcements.patchNote.savedIncluded" });
  });

  it("creates a patch note hidden, and tells the admin users do not see it", async () => {
    createMock.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    const el = renderPatchNotes();
    act(() => buttonWith(el, "rework.announcements.page.createPatchNote")[0].click());

    await act(async () => patchNoteEditor.props!.onSave({ kind: "patch_note", enabled: false }, false));

    expect(createMock).toHaveBeenCalledWith({ announcementWriteRequest: { kind: "patch_note", enabled: false } });
    expect(setEnabledMock).not.toHaveBeenCalled();
    expect(showSuccess).toHaveBeenCalledWith({ summary: "rework.announcements.patchNote.savedNotIncluded" });
  });

  it("preview opens the user dialog with that single note and records nothing as seen", () => {
    listMock.mockReturnValue({ data: [patchNote(), patchNote({ id: "p0" })], isLoading: false, refetch: refetchMock });
    const el = renderPatchNotes();

    act(() => el.querySelector<HTMLButtonElement>(`[aria-label="${NOTE_ROW}.preview"]`)!.click());

    const dialog = document.body.querySelector('[role="dialog"]')!;
    expect(dialog.textContent).toContain("What's new in 3.4");
    expect(dialog.querySelector("h1")?.textContent).toBe("Release 3.4 (2026-10-09)");
    // One note, so no history navigation, even with others in the list.
    expect(dialog.querySelector("nav")).toBeNull();

    act(() => buttonWith(dialog as HTMLElement, "rework.announcements.dialog.close")[0].click());

    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
    expect(seenMock).not.toHaveBeenCalled();
  });

  it("a failed toggle shows an error and leaves the refresh to tag invalidation", async () => {
    listMock.mockReturnValue({ data: [patchNote()], isLoading: false, refetch: refetchMock });
    setEnabledMock.mockReturnValue({ unwrap: () => Promise.reject({ status: 500, data: { detail: "boom" } }) });
    const el = renderPatchNotes();

    await act(async () => el.querySelector<HTMLInputElement>(NOTE_CHECKBOX)!.click());

    expect(showError).toHaveBeenCalledWith(expect.objectContaining({ summary: "rework.announcements.toggleFailed" }));
    // RTK Query invalidates the LIST tag on a rejected mutation too.
    expect(refetchMock).not.toHaveBeenCalled();
  });

  it("edit opens the editor matching the tab", () => {
    listMock.mockReturnValue({ data: [announcement(), patchNote()], isLoading: false, refetch: refetchMock });
    const el = render();

    act(() => el.querySelector<HTMLButtonElement>(`[aria-label="${ROW}.edit"]`)!.click());
    expect(el.querySelector('[data-testid="editor"]')?.getAttribute("data-id")).toBe("a1");
    expect(el.querySelector('[data-testid="patch-note-editor"]')).toBeNull();

    act(() => tab(el, "patchNotes").click());
    act(() => el.querySelector<HTMLButtonElement>(`[aria-label="${NOTE_ROW}.edit"]`)!.click());
    expect(el.querySelector('[data-testid="patch-note-editor"]')?.getAttribute("data-id")).toBe("p1");
    expect(el.querySelector('[data-testid="editor"]')).toBeNull();
  });

  it("toggles through the dedicated enabled endpoint, not a content update", () => {
    listMock.mockReturnValue({ data: [announcement()], isLoading: false, refetch: refetchMock });
    const el = render();
    const toggle = el.querySelector<HTMLInputElement>(`[aria-label="${ROW}.enabled"]`);

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
    const remove = el.querySelector<HTMLButtonElement>(`[aria-label="${ROW}.delete"]`);

    act(() => remove!.click());

    expect(confirmMock).toHaveBeenCalledTimes(1);
    expect(deleteMock).not.toHaveBeenCalled();

    const options = confirmMock.mock.calls[0][0];
    expect(options.criticalAction).toBe(true);
    expect(options.title).toBe("rework.announcements.delete.title");
    act(() => void options.onConfirm());

    expect(deleteMock).toHaveBeenCalledWith({ announcementId: "a1" });
  });

  it("asks before deleting a patch note, in its own words", async () => {
    listMock.mockReturnValue({ data: [patchNote()], isLoading: false });
    const el = renderPatchNotes();

    act(() => el.querySelector<HTMLButtonElement>(`[aria-label="${NOTE_ROW}.delete"]`)!.click());

    const options = confirmMock.mock.calls[0][0];
    expect([options.criticalAction, options.title]).toEqual([true, "rework.announcements.patchNote.delete.title"]);
    expect(deleteMock).not.toHaveBeenCalled();
    await act(async () => void options.onConfirm());

    expect(deleteMock).toHaveBeenCalledWith({ announcementId: "p1" });
    expect(showSuccess).toHaveBeenCalledWith({ summary: "rework.announcements.patchNote.deleted" });
  });

  it("shows the history table in the third tab, with nothing to create", () => {
    listMock.mockReturnValue({ data: [announcement()], isLoading: false, refetch: refetchMock });
    const el = render();
    const columnLabels = () => [...el.querySelectorAll('[class*="header-content"]')].map((label) => label.textContent);

    expect(el.querySelector("li")).not.toBeNull();
    expect(columnLabels()).toEqual([]);

    act(() => tab(el, "history").click());

    expect(tab(el, "history").getAttribute("aria-selected")).toBe("true");
    expect(el.querySelector("li")).toBeNull();
    expect(buttonWith(el, "rework.announcements.page.create")).toHaveLength(0);
    expect(columnLabels()).toEqual([
      "rework.announcements.history.column.type",
      "rework.announcements.history.column.title",
      "rework.announcements.history.column.activation",
      "rework.announcements.history.column.deactivation",
      "rework.announcements.history.column.by",
      "rework.announcements.history.column.open",
    ]);
    expect(el.textContent).toContain("Release 3.4");

    act(() => tab(el, "banners").click());

    expect(el.querySelector("li")).not.toBeNull();
    expect(buttonWith(el, "rework.announcements.page.createBanner")).toHaveLength(1);
    expect(columnLabels()).toEqual([]);
  });
});
