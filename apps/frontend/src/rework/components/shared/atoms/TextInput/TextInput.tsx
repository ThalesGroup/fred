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
import { ComponentPropsWithRef, useId, useState } from "react";
import Icon, { IconProps } from "../Icon/Icon.tsx";
import { ComponentSize } from "../../utils/Type.ts";

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
  defaultValue,
  required,
  disabled,
  id: callerId,
  ref,
  onChange,
  type = "text",
  autoComplete = "off",
  "aria-describedby": callerDescription,
  "aria-invalid": callerInvalid,
  ...props
}: TextInputProps) {
  const generatedId = useId();
  const id = callerId ?? generatedId;
  const hintId = `${id}-description`;
  const [uncontrolledValue, setUncontrolledValue] = useState(() => String(defaultValue ?? ""));
  const characterCounter = value === undefined ? uncontrolledValue.length : String(value).length;
  const message = error || explanation;
  const hasError = !disabled && Boolean(error);
  const describedBy = [callerDescription, message ? hintId : undefined].filter(Boolean).join(" ") || undefined;

  const handleChange: React.ChangeEventHandler<HTMLInputElement> = (event) => {
    if (value === undefined) setUncontrolledValue(event.currentTarget.value);
    onChange?.(event);
  };

  return (
    <div
      className={`${styles.input} ${disabled ? styles.disabled : ""} ${hasError ? styles.error : ""}`}
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
          ref={ref}
          type={type}
          value={value}
          defaultValue={defaultValue}
          maxLength={maxLength}
          required={required}
          disabled={disabled}
          autoComplete={autoComplete}
          onChange={handleChange}
          aria-describedby={describedBy}
          aria-invalid={hasError ? true : callerInvalid}
          {...props}
        />
        {suffix && <span className={styles.suffix}>{suffix}</span>}
      </div>
      <span className={styles.information}>
        <span className={styles.hint} id={message ? hintId : undefined}>
          {message || null}
        </span>
        <span className={styles.maxLength}>{maxLength !== undefined && `${characterCounter} / ${maxLength}`}</span>
      </span>
    </div>
  );
}
