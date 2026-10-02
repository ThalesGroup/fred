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

/**
 * usePaneResize
 * -------------
 * Pointer-drag resize for a side pane. Ported from the legacy chat's
 * `useResizablePane` (ResizablePaneShell, pre-rework), which the writable-
 * document editor and the PPT preview shared on `main`: the width is the
 * distance between the pane's fixed edge and the pointer, clamped to
 * [minWidth, min(maxWidth, 45vw)] — the same viewport guard a push layout
 * applies in CSS — and the last chosen width persists per `storageKey` so it
 * survives reloads.
 *
 * Pointer capture keeps every move/up event on the handle element itself, so
 * no window listeners are needed and the drag stays 1:1 with the pointer even
 * when it leaves the handle.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useLocalStorageState } from "../../../hooks/useLocalStorageState.ts";

interface UsePaneResizeOptions {
  /** Full localStorage key for the persisted width. */
  storageKey: string;
  /** Width (px) before the user ever drags. */
  initialWidth: number;
  minWidth?: number;
  maxWidth?: number;
  /** Viewport-width cap as a fraction (0–1). Mirrors the CSS `min(width, Nvw)`
   * guard so the stored width never diverges from the rendered one. Default 0.45. */
  maxViewportFraction?: number;
  /** The pane's FIXED edge — the one the drag does not move. A right-hand
   *  drawer grows leftwards from its right edge; a left-hand rail grows
   *  rightwards from its left one. Default "right". */
  anchor?: "left" | "right";
  /** The pane element, whose anchored edge the width is measured from. */
  paneRef: React.RefObject<HTMLElement | null>;
}

export interface PaneResizeHandleProps {
  tabIndex: number;
  "aria-valuemin": number;
  "aria-valuemax": number;
  "aria-valuenow": number;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onPointerDown: (e: React.PointerEvent) => void;
  onPointerMove: (e: React.PointerEvent) => void;
  onPointerUp: (e: React.PointerEvent) => void;
  onPointerCancel: (e: React.PointerEvent) => void;
}

export function usePaneResize({
  storageKey,
  initialWidth,
  minWidth = 320,
  maxWidth = 900,
  maxViewportFraction = 0.45,
  anchor = "right",
  paneRef,
}: UsePaneResizeOptions): {
  width: number;
  dragging: boolean;
  handleProps: PaneResizeHandleProps;
} {
  if (
    ![initialWidth, minWidth, maxWidth].every((value) => Number.isFinite(value) && value > 0) ||
    minWidth > maxWidth
  ) {
    throw new Error("usePaneResize: widths must be finite positive numbers with minWidth <= maxWidth.");
  }
  if (!Number.isFinite(maxViewportFraction) || maxViewportFraction <= 0 || maxViewportFraction > 1) {
    throw new Error("usePaneResize: maxViewportFraction must be in (0, 1].");
  }
  const [storedWidth, setWidth] = useLocalStorageState(storageKey, initialWidth);
  const width = typeof storedWidth === "number" && Number.isFinite(storedWidth) ? storedWidth : initialWidth;
  const [dragging, setDragging] = useState(false);
  const [viewportWidth, setViewportWidth] = useState(() =>
    typeof window !== "undefined" ? window.innerWidth : maxWidth,
  );
  useEffect(() => {
    const update = () => setViewportWidth(window.innerWidth);
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);
  // The anchored edge does not move while dragging; captured once per drag so
  // pointermove never forces a layout read.
  const dragAnchorRef = useRef(0);

  const clamp = useCallback(
    (value: number) => {
      // Mirror the CSS `min(width, 45vw)` cap so the stored width can never
      // diverge from the rendered one (a diverged drag feels dead past the cap).
      // `window` is absent outside a browser (SSR / non-jsdom test render) —
      // this hook runs unconditionally from every InlineDrawer, so it must not
      // assume one exists.
      const cap = Math.min(maxWidth, Math.floor(viewportWidth * maxViewportFraction));
      return Math.min(cap, Math.max(minWidth, value));
    },
    [minWidth, maxWidth, maxViewportFraction, viewportWidth],
  );

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      const pane = paneRef.current;
      if (!pane) return;
      const rect = pane.getBoundingClientRect();
      dragAnchorRef.current = anchor === "right" ? rect.right : rect.left;
      e.currentTarget.setPointerCapture(e.pointerId);
      setDragging(true);
      e.preventDefault();
    },
    [paneRef, anchor],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      // Capture doubles as the "is a drag in progress" flag — a plain hover
      // emits moves too, but never holds the capture.
      if (!e.currentTarget.hasPointerCapture(e.pointerId)) return;
      const distance = anchor === "right" ? dragAnchorRef.current - e.clientX : e.clientX - dragAnchorRef.current;
      setWidth(clamp(Math.round(distance)));
    },
    [clamp, setWidth, anchor],
  );

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const direction = (event.key === "ArrowLeft" ? 1 : -1) * (anchor === "right" ? 1 : -1);
      setWidth((previous) =>
        clamp(
          event.key === "Home"
            ? 0
            : event.key === "End"
              ? Infinity
              : clamp(typeof previous === "number" && Number.isFinite(previous) ? previous : initialWidth) +
                direction * 10,
        ),
      );
    },
    [anchor, clamp, setWidth, initialWidth],
  );

  const endDrag = useCallback(() => setDragging(false), []);

  return {
    // Clamp on read so a persisted value left over from different bounds (or a
    // narrower window) can never produce an out-of-range drawer.
    width: clamp(width),
    dragging,
    handleProps: {
      tabIndex: 0,
      "aria-valuemin": clamp(0),
      "aria-valuemax": clamp(Infinity),
      "aria-valuenow": clamp(width),
      onKeyDown,
      onPointerDown,
      onPointerMove,
      onPointerUp: endDrag,
      onPointerCancel: endDrag,
    },
  };
}
