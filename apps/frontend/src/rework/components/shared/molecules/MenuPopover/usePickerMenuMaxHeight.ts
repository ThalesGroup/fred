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

import { type CSSProperties, type RefObject, useEffect, useState } from "react";

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

      const viewportHeight = window.visualViewport?.height ?? window.innerHeight;
      const viewportWidth = window.visualViewport?.width ?? window.innerWidth;
      const heightCap = viewportWidth <= 720 ? PICKER_MOBILE_MAX_HEIGHT_PX : desktopMaxHeightPx;
      const availableHeight = Math.floor(Math.min(rect.bottom, viewportHeight) - PICKER_VIEWPORT_MARGIN_PX);
      setMaxHeight(Math.min(heightCap, Math.max(PICKER_MIN_HEIGHT_PX, availableHeight)));
    };

    update();

    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    window.visualViewport?.addEventListener("resize", update);
    window.visualViewport?.addEventListener("scroll", update);

    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
      window.visualViewport?.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("scroll", update);
    };
  }, [open, wrapRef, desktopMaxHeightPx]);

  return { maxHeight };
}
