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

// useResizablePane
// ----------------
// Minimal pointer-drag resizer for a right-hand pane (port of Kea's
// `useResizablePane`). Returns the current pane width (px), whether a drag is
// in progress (so the host can suppress its width transition), and the
// handler to attach to a vertical divider. The pane width is measured from
// the right edge of the window, clamped to [min, max], and the last chosen
// width is persisted to localStorage so it survives reloads.

import { useCallback, useEffect, useState } from "react";

function readStoredWidth(storageKey: string, fallback: number): number {
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (raw == null) return fallback;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
}

export function useResizablePane(storageKey: string, initialWidth = 460, minWidth = 320, maxWidth = 900) {
  const [width, setWidth] = useState<number>(() => readStoredWidth(storageKey, initialWidth));
  const [dragging, setDragging] = useState(false);

  const clamp = useCallback((value: number) => Math.min(maxWidth, Math.max(minWidth, value)), [minWidth, maxWidth]);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    setDragging(true);
    (e.target as Element).setPointerCapture?.(e.pointerId);
    e.preventDefault();
  }, []);

  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: PointerEvent) => {
      // Distance from the pointer to the right edge of the viewport = pane width.
      setWidth(clamp(window.innerWidth - e.clientX));
    };
    const onUp = () => setDragging(false);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [dragging, clamp]);

  // Persist the chosen width (only after a drag changes it).
  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, String(width));
    } catch {
      // Persistence is best-effort; a full storage never breaks resizing.
    }
  }, [storageKey, width]);

  // Clamp on read so a persisted value left over from different bounds can
  // never produce an out-of-range pane.
  return { width: clamp(width), dragging, onPointerDown };
}
