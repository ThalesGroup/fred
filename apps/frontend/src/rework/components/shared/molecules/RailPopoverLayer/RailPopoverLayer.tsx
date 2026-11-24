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

import { useLayoutEffect, useState, type CSSProperties, type ReactNode, type Ref, type RefObject } from "react";
import { Portal, uiPortalRoot } from "@shared/utils/Portal.tsx";
import { viewportHeight } from "@shared/utils/viewport.ts";
import styles from "./RailPopoverLayer.module.scss";

// --spacing-xs, restated: the portaled layer is placed in viewport pixels.
const POPOVER_GAP_PX = 8;

interface RailPopoverLayerProps {
  /** The rail entry the popover opens beside, bottoms aligned. */
  anchor: RefObject<HTMLElement | null>;
  /** For click-outside detection: the layer is outside the anchor's DOM. */
  ref?: Ref<HTMLDivElement>;
  children: ReactNode;
}

/**
 * A zero-size point beside a rail entry, portaled to the floating-menu layer so
 * no page content later in the DOM paints over the popover hanging from it.
 */
export default function RailPopoverLayer({ anchor, ref, children }: RailPopoverLayerProps) {
  const [position, setPosition] = useState<CSSProperties | undefined>(undefined);
  useLayoutEffect(() => {
    const update = () => {
      const rect = anchor.current?.getBoundingClientRect();
      if (rect) setPosition({ left: rect.right + POPOVER_GAP_PX, bottom: viewportHeight() - rect.bottom });
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [anchor]);

  return (
    <Portal root={uiPortalRoot(anchor.current)}>
      <div ref={ref} className={styles.layer} style={position}>
        {children}
      </div>
    </Portal>
  );
}
