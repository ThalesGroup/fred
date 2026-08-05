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

// Clamps an anchored dialog's height to the space above its row. Extracted
// from the former bespoke `SearchConfig` molecule (CAPAB-01 #1976): both the
// chat-context-prompts row and the document/library picker row anchor a
// `pickerMenu` at `bottom: 0` that grows upward, so a tall list would overflow
// past the top of the viewport without this clamp. Shared so every anchored
// "dialog" row (capability-driven or not) gets the same behavior.
//
// A page can lower the top limit below the viewport edge by marking one element
// with `data-picker-top-boundary` (e.g. the chat session title bar): the picker
// then stops just below that element instead of sliding under it. Without a
// marked element the viewport top stays the limit.

import { type CSSProperties, type RefObject, useEffect, useState } from "react";

export const PICKER_TOP_BOUNDARY_SELECTOR = "[data-picker-top-boundary]";

const PICKER_VIEWPORT_MARGIN_PX = 16;
const PICKER_MOBILE_MAX_HEIGHT_PX = 480;
const PICKER_MIN_HEIGHT_PX = 160;

export function usePickerMenuMaxHeight(
  open: boolean,
  wrapRef: RefObject<HTMLElement | null>,
  desktopMaxHeightPx: number,
): CSSProperties {
  const [maxHeight, setMaxHeight] = useState(360);

  useEffect(() => {
    if (!open) return;

    const update = () => {
      const rect = wrapRef.current?.getBoundingClientRect();
      if (!rect) return;

      const boundary = document.querySelector(PICKER_TOP_BOUNDARY_SELECTOR);
      const topLimit = boundary ? Math.max(0, boundary.getBoundingClientRect().bottom) : 0;
      const viewportHeight = window.visualViewport?.height ?? window.innerHeight;
      const viewportWidth = window.visualViewport?.width ?? window.innerWidth;
      const heightCap = viewportWidth <= 720 ? PICKER_MOBILE_MAX_HEIGHT_PX : desktopMaxHeightPx;
      const availableHeight = Math.floor(Math.min(rect.bottom, viewportHeight) - topLimit - PICKER_VIEWPORT_MARGIN_PX);
      setMaxHeight(Math.min(heightCap, Math.max(PICKER_MIN_HEIGHT_PX, availableHeight)));
    };

    update();

    // The boundary's height can change while the picker is open (the session
    // title appears once the first answer names the conversation).
    const boundary = document.querySelector(PICKER_TOP_BOUNDARY_SELECTOR);
    const boundaryObserver = boundary ? new ResizeObserver(update) : null;
    if (boundary && boundaryObserver) boundaryObserver.observe(boundary);

    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    window.visualViewport?.addEventListener("resize", update);
    window.visualViewport?.addEventListener("scroll", update);

    return () => {
      boundaryObserver?.disconnect();
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
      window.visualViewport?.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("scroll", update);
    };
  }, [open, wrapRef, desktopMaxHeightPx]);

  return { maxHeight };
}
