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

import styles from "./ButtonGroupItem.module.scss";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import { ComponentSize, ColorTheme } from "@shared/utils/Type.ts";
import { ComponentPropsWithRef } from "react";

export interface ButtonGroupItemProps extends ComponentPropsWithRef<"button"> {
  label: string;
  icon?: IconProps;
  hasError?: boolean;
  /** Overrides the group's `color` for this item only — e.g. a joining-mode
   * picker where each option's selected state uses a different semantic
   * color (success/secondary/error) rather than one color for the whole
   * group. Falls back to the group-level `color` when omitted. */
  color?: ColorTheme;
}

export interface ButtonGroupItemPrivateProps {
  size: ComponentSize;
  color: ColorTheme;
  selected: boolean;
  /** Drives ARIA role/state: a mutually-exclusive "radio" pick or a "tabs" strip. */
  variant: "radio" | "tabs";
}

export default function ButtonGroupItem({
  color,
  label,
  icon,
  selected,
  size,
  hasError,
  variant,
  ref,
  ...props
}: ButtonGroupItemProps & ButtonGroupItemPrivateProps) {
  return (
    <button
      ref={ref}
      className={styles.buttonGroupItem}
      data-color={color}
      data-size={size}
      role={variant === "radio" ? "radio" : "tab"}
      aria-checked={variant === "radio" ? selected : undefined}
      aria-selected={variant === "tabs" ? selected : undefined}
      {...props}
    >
      <div className={`${styles.stateLayer}`} data-selected={selected}>
        {icon && (
          <span className={styles.icon}>
            <Icon {...icon} />
          </span>
        )}
        <span className={styles.label}>{label}</span>
        {hasError && <span className={styles.errorDot} aria-hidden="true" />}
      </div>
    </button>
  );
}
