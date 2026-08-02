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

import Icon from "@shared/atoms/Icon/Icon.tsx";
import type { IconType } from "@shared/utils/Type.ts";
import { type ReactNode, useState } from "react";
import styles from "./ExpandableInfoContainer.module.css";

export type ExpandableInfoContainerColor = "info" | "warning" | "error" | "success" | "neutral";

interface ExpandableInfoContainerProps {
  /** Container/on-container token pair: info, warning, error, success, or
   *  "neutral" (surface-container-high / on-surface-retreat). */
  color: ExpandableInfoContainerColor;
  icon: IconType;
  title: ReactNode;
  children: ReactNode;
}

/**
 * Retractable info card: an icon + title header that toggles a body region
 * below it. Closed by default, uncontrolled, not persisted — every mount
 * starts collapsed. Generalized from the agent form's "what are capabilities
 * for" banner (#2202-era) so any surface can reuse it in a different color.
 *
 * The whole header is one `<button>`, not a row with a nested icon button —
 * a `<button>` can't contain another `<button>`, and the whole row is meant
 * to be the click target, not just the chevron.
 */
export function ExpandableInfoContainer({ color, icon, title, children }: ExpandableInfoContainerProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className={styles.container} data-color={color}>
      <button type="button" className={styles.header} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className={styles.icon} aria-hidden>
          <Icon category="outlined" type={icon} />
        </span>
        <span className={styles.title}>{title}</span>
        <span className={styles.chevron} aria-hidden style={{ transform: open ? "rotate(180deg)" : undefined }}>
          <Icon category="outlined" type="keyboard_arrow_down" />
        </span>
      </button>
      <div className={open ? `${styles.content} ${styles.contentOpen}` : styles.content}>
        <div className={styles.body}>{children}</div>
      </div>
    </div>
  );
}
