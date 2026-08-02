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

import type { ReactNode } from "react";
import styles from "./PageHeader.module.css";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  /** Optional icon button (e.g. a page-level "more" menu) rendered immediately
   *  to the right of the `<h1>`, inside the title row — distinct from `actions`,
   *  which renders as a separate block right-aligned at the far end of the
   *  header. Omit to render nothing. */
  titleAction?: ReactNode;
  actions?: ReactNode;
  /** Optional "you are here" trail or one-off link rendered above the title row. */
  breadcrumb?: ReactNode;
  /** Optional tab strip or filter control rendered below the title row, full width. */
  tabs?: ReactNode;
}

/**
 * The single `<h1>` + optional subtitle + optional right-aligned actions row
 * every top-level admin/team page used to hand-roll slightly differently
 * (2026-07-30/31 harmonization). This is the only place a page title should
 * be rendered — do not hand-roll an `<h1>`/`<h2>` page title elsewhere.
 * Vertically centers the title against `actions` when there's no subtitle
 * (a single-line title reads oddly top-aligned against same-height controls);
 * aligns to the top when there is one, so `actions` sits at the title's
 * baseline instead of drifting down toward the two-line block's middle.
 */
export default function PageHeader({ title, subtitle, titleAction, actions, breadcrumb, tabs }: PageHeaderProps) {
  return (
    <div className={styles.wrapper}>
      {breadcrumb && <div className={styles.breadcrumb}>{breadcrumb}</div>}
      <div className={subtitle ? `${styles.header} ${styles.headerWithSubtitle}` : styles.header}>
        <div className={styles.titleBlock}>
          <div className={styles.titleRow}>
            <h1 className={styles.title}>{title}</h1>
            {titleAction}
          </div>
          {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
        </div>
        {actions && <div className={styles.actions}>{actions}</div>}
      </div>
      {tabs && <div className={styles.tabs}>{tabs}</div>}
    </div>
  );
}
