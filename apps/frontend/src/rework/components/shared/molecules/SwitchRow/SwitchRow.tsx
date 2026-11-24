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

import { useId } from "react";
import Switch, { SwitchSize } from "@components/shared/atoms/Switch/Switch";
import styles from "./SwitchRow.module.css";

export interface SwitchRowProps {
  label: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** A read-only form still renders its switches; one that can be flicked
   *  promises a save the surface cannot make. */
  disabled?: boolean;
  size?: SwitchSize;
}

export function SwitchRow({ label, description, checked, onChange, disabled, size }: SwitchRowProps) {
  const id = useId();
  return (
    <div className={styles.switchRow}>
      <div className={styles.text}>
        <label className={styles.label} htmlFor={id}>
          {label}
        </label>
        <span id={`${id}-description`} className={styles.description}>
          {description}
        </span>
      </div>
      <Switch
        id={id}
        aria-describedby={`${id}-description`}
        size={size}
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
      />
    </div>
  );
}
