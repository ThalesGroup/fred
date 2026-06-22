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

import { ReactNode, useState } from "react";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import styles from "./WorkspaceRoot.module.css";

interface WorkspaceRootProps {
  /** Distinctive icon for this root (database / person / groups). */
  icon: IconProps;
  title: string;
  /** Right-aligned nature marker (badge, "privé · personnel · vide", file count…). */
  meta?: ReactNode;
  defaultOpen?: boolean;
  /** The discreet "+" add control, rendered right after the title (a menu trigger). */
  action?: ReactNode;
  children: ReactNode;
}

/**
 * One root branch of the unified workspace tree (FILES-04).
 *
 * Renders a collapsible root row — chevron + distinctive icon + bold (600) title, then the
 * small "+" add control glued after the name, a flex spacer, and the right-aligned nature
 * marker — over an expandable body. Rows are separated by thin filets, no bounding frame.
 */
export default function WorkspaceRoot({
  icon,
  title,
  meta,
  defaultOpen = false,
  action,
  children,
}: WorkspaceRootProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={styles.root}>
      <div className={styles.headerRow}>
        <button type="button" className={styles.toggle} onClick={() => setOpen((value) => !value)} aria-expanded={open}>
          <span className={styles.chevron} data-expanded={open || undefined}>
            <Icon category="outlined" type="chevron_right" />
          </span>
          <span className={styles.icon}>
            <Icon {...icon} />
          </span>
          <span className={styles.title}>{title}</span>
        </button>
        {action && <span className={styles.add}>{action}</span>}
        {meta != null && <span className={styles.meta}>{meta}</span>}
      </div>
      {open && <div className={styles.body}>{children}</div>}
    </div>
  );
}
