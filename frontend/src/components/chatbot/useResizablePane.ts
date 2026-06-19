// Copyright Thales 2025
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
 * useResizablePane
 * ----------------
 * Minimal pointer-drag resizer for a right-hand pane. Returns the current pane
 * width (px) and the handlers to attach to a vertical divider. The pane width is
 * measured from the right edge of the window, clamped to [min, max].
 */

import { useCallback, useEffect, useRef, useState } from "react";

export function useResizablePane(initialWidth = 460, minWidth = 320, maxWidth = 900) {
  const [width, setWidth] = useState(initialWidth);
  const draggingRef = useRef(false);

  const clamp = useCallback((value: number) => Math.min(maxWidth, Math.max(minWidth, value)), [minWidth, maxWidth]);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    draggingRef.current = true;
    (e.target as Element).setPointerCapture?.(e.pointerId);
    e.preventDefault();
  }, []);

  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      if (!draggingRef.current) return;
      // Distance from the pointer to the right edge of the viewport = pane width.
      setWidth(clamp(window.innerWidth - e.clientX));
    };
    const onUp = () => {
      draggingRef.current = false;
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [clamp]);

  return { width, onPointerDown };
}
