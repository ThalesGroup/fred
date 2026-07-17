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
  return (
    <button
      ref={ref}
      type="button"
      role={role}
      className={`${styles.item} ${danger ? styles.danger : ""}`}
      disabled={disabled}
      data-selected={selected}
      aria-selected={role === "option" ? selected : undefined}
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
      {trailingIcon && (
        <span className={styles.itemTrailing} aria-hidden>
          <Icon category="outlined" type={trailingIcon} />
        </span>
      )}
    </button>
  );
}
