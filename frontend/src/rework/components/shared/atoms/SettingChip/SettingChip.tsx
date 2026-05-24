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

import { ComponentPropsWithoutRef } from "react";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon";
import styles from "./SettingChip.module.css";

export interface SettingChipProps extends Omit<ComponentPropsWithoutRef<"button">, "color"> {
  label: string;
  open?: boolean;
  icon?: IconProps;
}

export function SettingChip({ label, open = false, icon, ...props }: SettingChipProps) {
  return (
    <button
      type="button"
      className={styles.chip}
      data-open={open}
      aria-expanded={open}
      {...props}
    >
      {icon && (
        <span className={styles.icon}>
          <Icon {...icon} />
        </span>
      )}
      <span className={styles.label}>{label}</span>
    </button>
  );
}
