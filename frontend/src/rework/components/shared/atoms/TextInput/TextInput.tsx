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

import styles from "./TextInput.module.scss";
import { ComponentPropsWithRef, useId } from "react";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";

export interface TextInputProps extends ComponentPropsWithRef<"input"> {
  label?: string;
  explanation?: string;
  error?: string;
  icon?: IconProps;
  compact?: boolean;
}

export default function TextInput({
  label,
  explanation,
  error,
  icon,
  compact = false,
  maxLength,
  value,
  required,
  ...props
}: TextInputProps) {
  const id = useId();

  const characterCounter = String(value).length;

  return (
    <div
      className={`${styles.input} ${props.disabled ? styles.disabled : ""} ${!props.disabled && error ? styles.error : ""}`}
      data-compact={compact}
    >
      {label && (
        <label className={styles.label} htmlFor={id}>
          {required ? `${label} *` : label}
        </label>
      )}
      {icon && (
        <span className={styles.icon}>
          <Icon {...icon} />
        </span>
      )}
      <input
        id={id}
        type={"text"}
        value={value}
        maxLength={maxLength}
        required={required}
        autoComplete="off"
        {...props}
      />
      <span className={styles.information}>
        <span className={styles.hint}>{error || explanation || null}</span>
        <span className={styles.maxLength}>{maxLength && `${characterCounter} / ${maxLength}`}</span>
      </span>
    </div>
  );
}
