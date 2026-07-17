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
import { ComponentPropsWithoutRef } from "react";

export interface ButtonGroupItemProps extends ComponentPropsWithoutRef<"button"> {
  label: string;
  icon?: IconProps;
  hasError?: boolean;
}

export interface ButtonGroupItemPrivateProps {
  size: ComponentSize;
  color: ColorTheme;
  selected: boolean;
}

export default function ButtonGroupItem({
  color,
  label,
  icon,
  selected,
  size,
  hasError,
  ...props
}: ButtonGroupItemProps & ButtonGroupItemPrivateProps) {
  return (
    <button
      className={styles.buttonGroupItem}
      data-color={color}
      data-size={size}
      role="radio"
      aria-checked={selected}
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
