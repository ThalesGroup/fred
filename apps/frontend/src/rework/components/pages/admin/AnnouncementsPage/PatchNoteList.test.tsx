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

// What these pin: a drop sends the whole new order in one call and shows it at
// once, a refused order puts the list back and says so, and the handle carries
// the keyboard and screen-reader wiring (instructions, spoken positions).
// happy-dom has no layout, so a move is driven through the drag-end callback
// the drag-and-drop context was given rather than through pointer coordinates.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DndContextProps } from "@dnd-kit/core";
import en from "../../../../../locales/en/translation.json";
import fr from "../../../../../locales/fr/translation.json";
import type { Announcement } from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";

const orderMock = vi.fn();
const showError = vi.fn();
const dnd = vi.hoisted(() => ({ props: null as null | DndContextProps }));

vi.mock("../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements", () => ({
  useSetPatchNoteOrderMutation: () => [orderMock, { isLoading: false }],
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError, showSuccess: vi.fn() }),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => (options ? `${key}:${JSON.stringify(options)}` : key),
    i18n: { language: "en" },
  }),
}));
vi.mock("@dnd-kit/core", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@dnd-kit/core")>();
  return {
    ...actual,
    DndContext: (props: DndContextProps) => {
      dnd.props = props;
      return <actual.DndContext {...props} />;
    },
  };
});

import PatchNoteList from "./PatchNoteList";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function patchNote(id: string, position: number): Announcement {
  return {
    id,
    kind: "patch_note",
    severity: "info",
    title: { en: `Note ${id}` },
    description_short: {},
    description_long: { en: "Body" },
    enabled: true,
    dismissible: true,
    content_version: 1,
    position,
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-01T10:00:00Z",
  };
}

const SERVED = [patchNote("a", 1), patchNote("b", 2), patchNote("c", 3)];

let container: HTMLDivElement | null = null;
let root: Root | null = null;

function show(notes: Announcement[]) {
  act(() =>
    root!.render(
      <PatchNoteList
        notes={notes}
        pendingIds={new Set()}
        onPreview={vi.fn()}
        onToggle={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onReorderingChange={reorderingMock}
      />,
    ),
  );
}

const reorderingMock = vi.fn();

function render(notes = SERVED): HTMLDivElement {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  show(notes);
  return container;
}

const order = () =>
  [...container!.querySelectorAll("li")].map((row) => row.querySelector('[class*="title"]')?.textContent);
type DragEnd = Parameters<NonNullable<DndContextProps["onDragEnd"]>>[0];
const drop = (active: string, over: string | null) =>
  dnd.props!.onDragEnd!({ active: { id: active }, over: over && { id: over } } as unknown as DragEnd);
const handles = () => [...container!.querySelectorAll<HTMLButtonElement>("button[aria-roledescription]")];

beforeEach(() => {
  orderMock.mockReturnValue({ unwrap: () => Promise.resolve(undefined) });
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  vi.clearAllMocks();
});

describe("PatchNoteList", () => {
  it("a drop sends the whole new order once and shows it at once", () => {
    render();

    act(() => drop("c", "a"));

    expect(orderMock).toHaveBeenCalledExactlyOnceWith({ patchNoteOrderRequest: { ids: ["c", "a", "b"] } });
    expect(order()).toEqual(["Note c", "Note a", "Note b"]);
  });

  it("keeps the dropped order while the save is in flight, then follows the server", async () => {
    let settle!: () => void;
    orderMock.mockReturnValue({ unwrap: () => new Promise<void>((resolve) => (settle = resolve)) });
    render();

    act(() => drop("a", "b"));
    // A refetch that still carries the old order must not undo the drop.
    show([...SERVED]);
    expect(order()).toEqual(["Note b", "Note a", "Note c"]);

    // Told while the save is in flight, so nothing announces the old order.
    expect(reorderingMock.mock.calls).toEqual([[true]]);
    await act(async () => settle());
    expect(reorderingMock.mock.calls).toEqual([[true], [false]]);
    show([patchNote("b", 1), patchNote("a", 2), patchNote("c", 3)]);
    expect(order()).toEqual(["Note b", "Note a", "Note c"]);
  });

  it("puts the list back and says so when the order is refused", async () => {
    orderMock.mockReturnValue({ unwrap: () => Promise.reject({ status: 409, data: { detail: "stale order" } }) });
    render();

    await act(async () => drop("c", "a"));

    expect(order()).toEqual(["Note a", "Note b", "Note c"]);
    expect(showError).toHaveBeenCalledExactlyOnceWith({
      summary: "rework.announcements.patchNote.reorder.failed",
      detail: "stale order",
    });
  });

  it("sends nothing when the card is dropped where it was, or outside the list", () => {
    render();

    act(() => drop("b", "b"));
    act(() => drop("b", null));

    expect(orderMock).not.toHaveBeenCalled();
    expect(order()).toEqual(["Note a", "Note b", "Note c"]);
  });

  it("gives each card a focusable handle described by the keyboard instructions", () => {
    render();

    expect(handles()).toHaveLength(3);
    const handle = handles()[1];
    expect(handle.getAttribute("aria-label")).toBe('rework.announcements.patchNote.row.move:{"title":"Note b"}');
    expect(handle.getAttribute("aria-roledescription")).toBe("rework.announcements.patchNote.reorder.role");
    expect(handle.tabIndex).toBe(0);
    expect(document.getElementById(handle.getAttribute("aria-describedby")!)?.textContent).toBe(
      "rework.announcements.patchNote.reorder.instructions",
    );
    // The handle comes first in its card: it sits at the left.
    expect(handle.parentElement!.firstElementChild).toBe(handle);
  });

  it("speaks the card's title and the position it takes at each step of a move", () => {
    render();
    const { onDragStart, onDragOver, onDragEnd, onDragCancel } = dnd.props!.accessibility!.announcements!;
    const step = (over: string | null) => ({ active: { id: "a" }, over: over && { id: over } }) as never;
    const said = (key: string, position: number) =>
      `rework.announcements.patchNote.reorder.${key}:${JSON.stringify({ title: "Note a", position, total: 3 })}`;

    expect(onDragStart(step(null))).toBe(said("picked", 1));
    expect(onDragOver(step("c"))).toBe(said("moved", 3));
    expect(onDragEnd(step("b"))).toBe(said("dropped", 2));
    expect(onDragCancel(step("c"))).toBe(said("cancelled", 1));
  });

  it("listens to the pointer and to the keyboard, which steps card by card", () => {
    render();
    const [pointer, keyboard] = dnd.props!.sensors!;

    expect(pointer.sensor.name).toBe("PointerSensor");
    expect(keyboard.sensor.name).toBe("KeyboardSensor");
    // Arrow keys step one card at a time rather than a fixed number of pixels.
    expect(keyboard.options).toHaveProperty("coordinateGetter");
  });

  it("has its reorder strings in French and English", () => {
    for (const locale of [fr, en]) {
      const { reorder, row } = locale.rework.announcements.patchNote;
      for (const text of [...Object.values(reorder), row.move]) expect(text.trim()).not.toBe("");
      for (const key of ["picked", "moved", "dropped", "cancelled"] as const) {
        expect(reorder[key]).toContain("{{title}}");
        expect(reorder[key]).toContain("{{position}}");
      }
    }
  });
});
