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
import styles from "./KpiSection.module.scss";

interface KpiSectionProps {
  title: string;
  children: ReactNode;
}

interface KpiRowProps {
  children: ReactNode;
  /** Fix the first child at 200px (stat card on the left). */
  compactFirst?: boolean;
  /** Fix the last child at 200px (stat card on the right). */
  compactLast?: boolean;
}

export function KpiRow({ children, compactFirst = false, compactLast = false }: KpiRowProps) {
  const cls = [styles.row, compactFirst ? styles.rowCompactFirst : "", compactLast ? styles.rowCompactLast : ""]
    .filter(Boolean)
    .join(" ");
  return <div className={cls}>{children}</div>;
}

export default function KpiSection({ title, children }: KpiSectionProps) {
  return (
    <section className={styles.section}>
      <h2 className={styles.title}>{title}</h2>
      <div className={styles.rows}>{children}</div>
    </section>
  );
}
