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

import type { ReactNode, Ref } from "react";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import styles from "./SpaceHeader.module.css";

export interface SpaceHeaderProps {
  /** Small line: whose section this is, e.g. the organization's name. */
  eyebrow?: string;
  /** The section, e.g. "Accueil": the panel heading. */
  title: string;
  /** Turns the block into the trigger of a space menu, rendered as `children`. */
  menu?: { open: boolean; onToggle: () => void; ref?: Ref<HTMLButtonElement> };
  children?: ReactNode;
}

/** A nav panel's heading with its space: read-only, or the trigger of a space menu. */
export default function SpaceHeader({ eyebrow, title, menu, children }: SpaceHeaderProps) {
  const eyebrowLine = eyebrow && <span className={styles.eyebrow}>{eyebrow}</span>;
  return (
    <div className={styles.root}>
      {menu ? (
        // The trigger stays the panel heading: the heading wraps the button.
        <h2 className={styles.heading}>
          <button
            type="button"
            ref={menu.ref}
            className={`${styles.block} ${styles.trigger}`}
            aria-haspopup="menu"
            aria-expanded={menu.open}
            onClick={menu.onToggle}
          >
            <span className={styles.text}>
              {eyebrowLine}
              <span className={styles.title}>{title}</span>
            </span>
            <span className={styles.chevron} aria-hidden>
              <Icon category="outlined" type={menu.open ? "expand_less" : "expand_more"} />
            </span>
          </button>
        </h2>
      ) : (
        <div className={styles.block}>
          <span className={styles.text}>
            {eyebrowLine}
            <h2 className={styles.title}>{title}</h2>
          </span>
        </div>
      )}
      {children}
    </div>
  );
}
