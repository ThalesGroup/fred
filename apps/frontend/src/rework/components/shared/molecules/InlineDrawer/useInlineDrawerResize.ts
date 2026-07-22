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
 * useInlineDrawerResize
 * ---------------------
 * Pointer-drag resize for a right-hand push InlineDrawer. Ported from the
 * legacy chat's `useResizablePane` (ResizablePaneShell, pre-rework), which the
 * writable-document editor and the PPT preview shared on `main`: the drawer
 * width is the distance from the drawer's right edge to the pointer, clamped
 * to [minWidth, min(maxWidth, 45vw)] — the same viewport guard the push layout
 * applies in CSS — and the last chosen width persists per `persistKey` so it
 * survives reloads.
 *
 * Pointer capture keeps every move/up event on the handle element itself, so
 * no window listeners are needed and the drag stays 1:1 with the pointer even
 * when it leaves the handle.
 */

import { useCallback, useRef, useState } from "react";
import { useLocalStorageState } from "src/hooks/useLocalStorageState";

interface UseInlineDrawerResizeOptions {
  /** localStorage identity for the persisted width — one key per drawer family. */
  persistKey: string;
  /** Width (px) before the user ever drags. */
  initialWidth: number;
  minWidth?: number;
  maxWidth?: number;
  /** The drawer element — its right edge anchors the width computation. */
  drawerRef: React.RefObject<HTMLElement | null>;
}

export interface InlineDrawerResizeHandleProps {
  onPointerDown: (e: React.PointerEvent) => void;
  onPointerMove: (e: React.PointerEvent) => void;
  onPointerUp: (e: React.PointerEvent) => void;
  onPointerCancel: (e: React.PointerEvent) => void;
}

export function useInlineDrawerResize({
  persistKey,
  initialWidth,
  minWidth = 320,
  maxWidth = 900,
  drawerRef,
}: UseInlineDrawerResizeOptions): {
  width: number;
  dragging: boolean;
  handleProps: InlineDrawerResizeHandleProps;
} {
  const [width, setWidth] = useLocalStorageState(`inline-drawer:${persistKey}:width`, initialWidth);
  const [dragging, setDragging] = useState(false);
  // The drawer's right edge is fixed while dragging (only the left edge moves);
  // captured once per drag so pointermove never forces a layout read.
  const dragRightEdgeRef = useRef(0);

  const clamp = useCallback(
    (value: number) => {
      // Mirror the CSS `min(width, 45vw)` cap so the stored width can never
      // diverge from the rendered one (a diverged drag feels dead past the cap).
      const cap = Math.min(maxWidth, Math.floor(window.innerWidth * 0.45));
      return Math.min(cap, Math.max(minWidth, value));
    },
    [minWidth, maxWidth],
  );

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      const drawer = drawerRef.current;
      if (!drawer) return;
      dragRightEdgeRef.current = drawer.getBoundingClientRect().right;
      e.currentTarget.setPointerCapture(e.pointerId);
      setDragging(true);
      e.preventDefault();
    },
    [drawerRef],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      // Capture doubles as the "is a drag in progress" flag — a plain hover
      // emits moves too, but never holds the capture.
      if (!e.currentTarget.hasPointerCapture(e.pointerId)) return;
      setWidth(clamp(Math.round(dragRightEdgeRef.current - e.clientX)));
    },
    [clamp, setWidth],
  );

  const endDrag = useCallback(() => setDragging(false), []);

  return {
    // Clamp on read so a persisted value left over from different bounds (or a
    // narrower window) can never produce an out-of-range drawer.
    width: clamp(width),
    dragging,
    handleProps: { onPointerDown, onPointerMove, onPointerUp: endDrag, onPointerCancel: endDrag },
  };
}
