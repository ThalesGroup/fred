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

import { ComponentPropsWithRef, memo, ReactNode, useId } from "react";
import styles from "./MenuItem.module.scss";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";

export interface MenuItemProps extends ComponentPropsWithRef<"li"> {
  label?: string;
  description?: string;
  children?: ReactNode;
  icon?: IconProps;
  role?: "option" | "menuitem";
  selected?: boolean;
  focused?: boolean;
  disabled?: boolean;
  /** Renders the label/icon in the error color (e.g. a "Delete" action). */
  destructive?: boolean;
}

function MenuItem({
  label,
  description,
  children,
  icon,
  role = "option",
  selected = false,
  focused = false,
  disabled = false,
  destructive = false,
  onClick,
  id: providedId,
  ref, // La ref arrive ici
  ...rest
}: MenuItemProps) {
  const generatedId = useId();
  const id = providedId ?? generatedId;

  return (
    <li
      {...rest}
      ref={ref}
      id={id}
      className={styles["menu-item"]}
      role={role}
      aria-selected={role === "option" ? selected : undefined}
      aria-disabled={disabled}
      data-selected={selected}
      data-focused={focused}
      data-disabled={disabled}
      data-destructive={destructive}
      tabIndex={focused ? 0 : -1}
      onClick={disabled ? undefined : onClick}
    >
      <div className={styles["state-layer"]}>
        {icon && (
          <span className={styles["icon-wrapper"]} aria-hidden="true">
            <Icon {...icon} />
          </span>
        )}

        {children ? (
          children
        ) : description ? (
          <span className={styles["content"]}>
            <span className={styles["label"]}>{label}</span>
            <span className={styles["description"]}>{description}</span>
          </span>
        ) : (
          <span className={styles["label"]}>{label}</span>
        )}
      </div>
    </li>
  );
}

export default memo(MenuItem);
