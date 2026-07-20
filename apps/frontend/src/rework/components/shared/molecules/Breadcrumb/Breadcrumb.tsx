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
import styles from "./Breadcrumb.module.css";

export interface BreadcrumbSegment {
  /** Text shown for this level of the trail. */
  label: string;
  /**
   * Navigates back to this level. Omit on the current (last) segment — it
   * renders as plain, non-interactive text instead of a link.
   */
  onClick?: () => void;
}

export interface BreadcrumbProps {
  /** Ordered from the shallowest (root) to the deepest (current) level. */
  segments: BreadcrumbSegment[];
}

/**
 * Generic "you are here" trail for multi-level views (e.g. evaluations list
 * → one evaluation's runs → one run's cases). Every segment but the last is
 * a clickable link back to that level; the last segment is the current
 * location and is rendered as plain emphasized text.
 *
 * Not tied to any domain — any feature with a drill-down hierarchy can reuse
 * this by supplying its own segments and `onClick` handlers.
 */
export function Breadcrumb({ segments }: BreadcrumbProps) {
  if (segments.length === 0) return null;

  const lastIndex = segments.length - 1;

  return (
    <nav aria-label="Breadcrumb" className={styles.nav}>
      <ol className={styles.list}>
        {segments.map((segment, index) => {
          const isCurrent = index === lastIndex;
          return (
            <li key={`${segment.label}-${index}`} className={styles.item}>
              {isCurrent ? (
                <span className={styles.current} aria-current="page">
                  {segment.label}
                </span>
              ) : (
                <button type="button" className={styles.link} onClick={segment.onClick}>
                  {segment.label}
                </button>
              )}
              {!isCurrent && (
                <span className={styles.separator} aria-hidden="true">
                  <Icon category="outlined" type="chevron_right" />
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
