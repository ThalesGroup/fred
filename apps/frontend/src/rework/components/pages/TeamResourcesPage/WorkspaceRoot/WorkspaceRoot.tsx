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
import { DetailedTooltip } from "../../../../../shared/ui/tooltips/Tooltips";
import styles from "./WorkspaceRoot.module.css";

interface WorkspaceRootProps {
  /** Distinctive icon for this root (database / person / groups). */
  icon: IconProps;
  title: string;
  /** One-line, user-facing explanation of this space, shown via an info-icon tooltip so a
   * first-time visitor understands what it's for without leaving the page. */
  hint?: string;
  /** Right-aligned nature marker (badge, "privé · personnel · vide", file count…). */
  meta?: ReactNode;
  defaultOpen?: boolean;
  /** The discreet "+" add control, rendered right after the title (a menu trigger). */
  action?: ReactNode;
  /** false renders a static panel header (no chevron, always expanded, not a button) —
   *  for hosts that already gate visibility themselves (e.g. a tab switcher, FRONT-09.G),
   *  so this root doesn't also try to collapse/expand on top of that. Default true keeps
   *  the original accordion-row behavior for existing callers. */
  collapsible?: boolean;
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
  hint,
  meta,
  defaultOpen = false,
  action,
  collapsible = true,
  children,
}: WorkspaceRootProps) {
  const [open, setOpen] = useState(defaultOpen);
  const isOpen = collapsible ? open : true;

  const titleNode = hint ? (
    <DetailedTooltip label={title} description={hint} placement="bottom-start">
      <span className={styles.title}>{title}</span>
    </DetailedTooltip>
  ) : (
    <span className={styles.title}>{title}</span>
  );

  return (
    <div className={styles.root} data-collapsible={collapsible}>
      <div className={styles.headerRow}>
        {collapsible ? (
          <button
            type="button"
            className={styles.toggle}
            onClick={() => setOpen((value) => !value)}
            aria-expanded={isOpen}
          >
            <span className={styles.chevron} data-expanded={isOpen || undefined}>
              <Icon category="outlined" type="chevron_right" />
            </span>
            <span className={styles.icon}>
              <Icon {...icon} />
            </span>
            {titleNode}
          </button>
        ) : (
          <div className={styles.toggle}>
            <span className={styles.icon}>
              <Icon {...icon} />
            </span>
            {titleNode}
          </div>
        )}
        {action && <span className={styles.add}>{action}</span>}
        {meta != null && <span className={styles.meta}>{meta}</span>}
      </div>
      {isOpen && <div className={collapsible ? styles.body : styles.bodyFlush}>{children}</div>}
    </div>
  );
}
