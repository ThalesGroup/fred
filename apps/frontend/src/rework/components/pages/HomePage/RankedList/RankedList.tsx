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
import styles from "./RankedList.module.scss";

export interface RankedItem {
  key: string;
  label: string;
  sublabel?: string;
  value: number;
  unit?: string;
  /** Optional leading visual (e.g. a team avatar) rendered before the label. */
  leading?: ReactNode;
}

interface RankedListProps {
  items: RankedItem[];
  emptyLabel: string;
}

/** A compact "top N" leaderboard: rank, label (+ optional sublabel), a bar sized
 * relative to the leader, and the value. Shared by the home page's most-used
 * agents and most-active teams. */
export default function RankedList({ items, emptyLabel }: RankedListProps) {
  if (items.length === 0) return <div className={styles.empty}>{emptyLabel}</div>;
  const max = Math.max(...items.map((i) => i.value), 1);

  return (
    <div className={styles.list}>
      {items.map((item, index) => (
        <div key={item.key} className={styles.row}>
          <span className={styles.rank}>{index + 1}</span>
          {item.leading && <span className={styles.leading}>{item.leading}</span>}
          <div className={styles.main}>
            <div className={styles.label}>
              {item.label}
              {item.sublabel && <span className={styles.sublabel}> · {item.sublabel}</span>}
            </div>
            <div className={styles.bar}>
              <span style={{ width: `${Math.round((item.value / max) * 100)}%` }} />
            </div>
          </div>
          <div className={styles.value}>
            {item.value.toLocaleString("fr-FR")}
            {item.unit && <span className={styles.unit}> {item.unit}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}
