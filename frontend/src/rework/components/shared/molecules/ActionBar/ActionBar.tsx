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

import styles from "./ActionBar.module.css";

export interface Action {
  id: string;
  icon: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}

interface ActionBarProps {
  actions: Action[];
  /** When true, the bar is always visible regardless of parent hover state. */
  alwaysVisible?: boolean;
  className?: string;
}

export function ActionBar({ actions, alwaysVisible = false, className }: ActionBarProps) {
  return (
    <div
      className={`${styles.bar} ${alwaysVisible ? styles.alwaysVisible : ""} ${className ?? ""}`}
      role="toolbar"
    >
      {actions.map((action) => (
        <button
          key={action.id}
          type="button"
          className={styles.action}
          onClick={action.onClick}
          disabled={action.disabled}
          aria-label={action.label}
          title={action.label}
        >
          <span className="material-symbols-outlined" aria-hidden>
            {action.icon}
          </span>
        </button>
      ))}
    </div>
  );
}
