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

// Generic enum select row: a `MenuPopoverItem` that expands into an anchored
// listbox of options. Extracted from the former bespoke `SearchConfig`
// molecule (CAPAB-01 #1976) so the composer control stock kit
// (`features/capabilities/stockKit/`) can reuse the exact same row for the
// `search_policy` and `rag_scope` chat controls, and any future capability
// exposing a small closed-set choice can reuse it too.

import type { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import MenuPopoverItem from "@shared/molecules/MenuPopover/MenuPopoverItem.tsx";
import styles from "./EnumSelectRow.module.css";

export interface EnumSelectOption<T extends string> {
  value: T;
  label: string;
}

export interface EnumSelectRowProps<T extends string> {
  icon: IconProps;
  label: string;
  title: string;
  value: T;
  options: EnumSelectOption<T>[];
  open: boolean;
  onToggle: () => void;
  onChange: (value: T) => void;
}

export function EnumSelectRow<T extends string>({
  icon,
  label,
  title,
  value,
  options,
  open,
  onToggle,
  onChange,
}: EnumSelectRowProps<T>) {
  const selected = options.find((option) => option.value === value) ?? options[0];

  return (
    <div className={styles.rowWrap}>
      <MenuPopoverItem
        icon={icon}
        label={label}
        value={selected.label}
        trailingIcon="chevron_right"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`${title}: ${selected.label}`}
        onClick={onToggle}
      />

      {open && (
        <ul className={styles.selectMenu} role="listbox" aria-label={title}>
          {options.map((option) => {
            const isActive = option.value === value;
            return (
              <li key={option.value} className={styles.menuItemWrap}>
                <button
                  type="button"
                  role="option"
                  aria-selected={isActive}
                  className={styles.menuItem}
                  data-active={isActive}
                  onClick={() => onChange(option.value)}
                >
                  <span className={styles.menuItemLabel}>{option.label}</span>
                  {isActive && (
                    <span className={`${styles.menuItemCheck} material-symbols-outlined`} aria-hidden>
                      check
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
