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
import { ComponentSize } from "@shared/utils/Type.ts";

export interface TextInputProps extends Omit<ComponentPropsWithRef<"input">, "size"> {
  label?: string;
  explanation?: string;
  error?: string;
  icon?: IconProps;
  /** Fixed, non-editable text shown right after the input's own text (e.g. a
   *  locked file extension). Purely presentational — callers own splitting
   *  the editable value from this suffix and recombining them on submit. */
  suffix?: string;
  compact?: boolean;
  /** Shrinks the input's own height (shared ComponentSize scale). Omit to
   *  keep the existing default height — every other TextInput call site is
   *  unaffected. Shadows the native HTML `size` attribute (character-width
   *  sizing), which this design system doesn't use. */
  size?: ComponentSize;
}

export default function TextInput({
  label,
  explanation,
  error,
  icon,
  suffix,
  compact = false,
  size,
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
      data-size={size}
    >
      {label && (
        <label className={styles.label} htmlFor={id}>
          {required ? `${label} *` : label}
        </label>
      )}
      <div className={styles.field}>
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
        {suffix && <span className={styles.suffix}>{suffix}</span>}
      </div>
      <span className={styles.information}>
        <span className={styles.hint}>{error || explanation || null}</span>
        <span className={styles.maxLength}>{maxLength && `${characterCounter} / ${maxLength}`}</span>
      </span>
    </div>
  );
}
