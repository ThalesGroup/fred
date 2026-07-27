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

import styles from "./Tabs.module.scss";

export interface TabItem<T extends string = string> {
  value: T;
  label: string;
}

export interface TabsProps<T extends string = string> {
  tabs: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
}

/**
 * Horizontal tab switcher — one panel visible at a time, with a sliding
 * active-indicator underline. Not tied to any domain; any feature that needs
 * to switch between a small, fixed set of top-level views can reuse this.
 */
export default function Tabs<T extends string = string>({ tabs, value, onChange }: TabsProps<T>) {
  return (
    <div className={styles["tabs"]} role="tablist">
      {tabs.map((tab) => {
        const isActive = tab.value === value;
        return (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={isActive}
            className={styles["tab"]}
            data-active={isActive || undefined}
            onClick={() => onChange(tab.value)}
          >
            <span className={styles["tab-label"]}>{tab.label}</span>
            <span className={styles["tab-indicator"]} />
          </button>
        );
      })}
    </div>
  );
}
