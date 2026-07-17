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

import { Fragment, ReactNode, Ref } from "react";
import styles from "./MenuPopover.module.scss";

export interface MenuPopoverProps {
  /** Ref to the popover surface, e.g. for click-outside detection. */
  ref?: Ref<HTMLDivElement>;
  /** Optional header title (e.g. user full name). */
  headerTitle?: string;
  /** Optional header subtitle (e.g. user email). */
  headerSubtitle?: string;
  /** Escape hatch for a fully custom header; overrides title/subtitle. */
  header?: ReactNode;
  /**
   * Item rows grouped into logical sections. Each group is rendered as a block
   * and groups are separated by thin dividers. Falsy items and empty groups are
   * dropped, so callers can gate rows inline.
   */
  groups: ReactNode[][];
  role?: string;
  className?: string;
  "aria-label"?: string;
}

/**
 * The shared menu-popover box: optional header + groups of homogeneous rows
 * separated by thin dividers. It owns the visual surface (shadow, border,
 * radius, padding) but not its placement — consumers position it. The profile
 * menu and the chat options menu are both instances of this component.
 */
export default function MenuPopover({
  ref,
  headerTitle,
  headerSubtitle,
  header,
  groups,
  role = "menu",
  className,
  "aria-label": ariaLabel,
}: MenuPopoverProps) {
  const visibleGroups = groups.map((group) => group.filter(Boolean)).filter((group) => group.length > 0);
  const hasHeader = header != null || headerTitle != null;

  return (
    <div ref={ref} className={`${styles.popover} ${className ?? ""}`} role={role} aria-label={ariaLabel}>
      {hasHeader && (
        <div className={styles.header}>
          {header ?? (
            <>
              {headerTitle != null && <span className={styles.headerTitle}>{headerTitle}</span>}
              {headerSubtitle != null && <span className={styles.headerSubtitle}>{headerSubtitle}</span>}
            </>
          )}
        </div>
      )}
      {visibleGroups.map((group, groupIndex) => (
        <Fragment key={groupIndex}>
          {(groupIndex > 0 || hasHeader) && <div className={styles.separator} />}
          {group}
        </Fragment>
      ))}
    </div>
  );
}
