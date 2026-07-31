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

import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import { IconType } from "@shared/utils/Type.ts";
import { type KeyboardEvent, type Ref } from "react";
import styles from "./MenuPopover.module.scss";

export interface MenuPopoverItemProps {
  /** Leading icon. */
  icon?: IconProps;
  /** Primary row label. */
  label: string;
  /** Current value shown on the right in muted text (e.g. "Hybride", "aucun"). */
  value?: string;
  /** Pill shown on the right (e.g. the "admin" badge). */
  badge?: string;
  /** Trailing affordance icon, e.g. "chevron_right" for sub-rows or "add" for actions. */
  trailingIcon?: IconType;
  /**
   * Renders a switch as the trailing affordance and makes the row a boolean
   * control (`menuitemcheckbox` + `aria-checked` from `selected`).
   *
   * The switch is drawn by this row, not composed from the `Switch` atom: the
   * atom is a `<label><input>` pair and this row is a `<button>`, so nesting it
   * would put an interactive element inside a button — invalid, and a double
   * click target. Drawn here, the whole row stays one button: click anywhere,
   * Space/Enter, one tab stop.
   */
  trailingToggle?: boolean;
  /** Destructive styling (red label + icon), e.g. logout. */
  danger?: boolean;
  disabled?: boolean;
  selected?: boolean;
  onClick?: () => void;
  role?: "menuitem" | "option";
  /** Roving-tabindex support for consumers driving keyboard nav across rows (e.g. `EnumSelectRow`). */
  ref?: Ref<HTMLButtonElement>;
  tabIndex?: number;
  onKeyDown?: (event: KeyboardEvent<HTMLButtonElement>) => void;
  "aria-haspopup"?: "menu" | "dialog" | "listbox" | "true";
  "aria-expanded"?: boolean;
  "aria-label"?: string;
}

/**
 * A single homogeneous menu row: icon + label + optional value/badge + optional
 * trailing affordance. Shared by the profile menu and the chat options menu so
 * both read as instances of the same component. Sub-menu rows are just rows with
 * a chevron whose anchored panel is rendered by the parent as a sibling.
 */
export default function MenuPopoverItem({
  icon,
  label,
  value,
  badge,
  trailingIcon,
  trailingToggle = false,
  danger = false,
  disabled = false,
  selected = false,
  onClick,
  role = "menuitem",
  ref,
  tabIndex,
  onKeyDown,
  ...aria
}: MenuPopoverItemProps) {
  const effectiveRole = trailingToggle ? "menuitemcheckbox" : role;
  return (
    <button
      ref={ref}
      type="button"
      role={effectiveRole}
      className={`${styles.item} ${danger ? styles.danger : ""}`}
      disabled={disabled}
      // A toggle row is NOT "selected" the way a picked option is — the row
      // stays in the menu either way, so highlighting it as chosen would read
      // as a selection. `aria-checked` carries the state instead.
      data-selected={trailingToggle ? undefined : selected}
      aria-selected={role === "option" && !trailingToggle ? selected : undefined}
      aria-checked={trailingToggle ? selected : undefined}
      onClick={onClick}
      tabIndex={tabIndex}
      onKeyDown={onKeyDown}
      {...aria}
    >
      {icon && (
        <span className={styles.itemIcon} aria-hidden>
          <Icon {...icon} />
        </span>
      )}
      <span className={styles.itemLabel}>{label}</span>
      {value != null && <span className={styles.itemValue}>{value}</span>}
      {badge != null && <span className={styles.badge}>{badge}</span>}
      {trailingToggle && (
        <span className={styles.itemToggle} data-on={selected} aria-hidden>
          <span className={styles.itemToggleHandle} />
        </span>
      )}
      {trailingIcon && (
        <span className={styles.itemTrailing} aria-hidden>
          <Icon category="outlined" type={trailingIcon} />
        </span>
      )}
    </button>
  );
}
