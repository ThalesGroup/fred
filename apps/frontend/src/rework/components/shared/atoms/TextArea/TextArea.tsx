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

import { ComponentPropsWithRef, useEffect, useId, useImperativeHandle, useRef, useState } from "react";
import styles from "./TextArea.module.scss";

interface TextAreaBaseProps extends Omit<ComponentPropsWithRef<"textarea">, "value" | "defaultValue"> {
  label: string;
  explanation?: string;
  error?: string;
}

export type TextAreaProps = TextAreaBaseProps &
  (
    | ({ value: NonNullable<ComponentPropsWithRef<"textarea">["value"]>; defaultValue?: never } & (
        | { onChange: NonNullable<ComponentPropsWithRef<"textarea">["onChange"]> }
        | { readOnly: true }
        | { disabled: true }
      ))
    | { value?: undefined; defaultValue?: ComponentPropsWithRef<"textarea">["defaultValue"] }
  );

export default function TextArea({
  label,
  explanation,
  error,
  maxLength,
  value,
  defaultValue,
  ref,
  onChange,
  required,
  id: suppliedId,
  ...props
}: TextAreaProps) {
  const generatedId = useId();
  const id = suppliedId ?? generatedId;
  const controlled = value !== undefined;
  const inputRef = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(ref, () => inputRef.current!, []);
  const [uncontrolledValue, setUncontrolledValue] = useState(() => String(defaultValue ?? ""));
  useEffect(() => {
    if (controlled) return;
    const input = inputRef.current;
    const form = input?.form;
    let resetTimer: ReturnType<typeof setTimeout> | undefined;
    if (input) setUncontrolledValue(input.value);
    const onReset = (event: Event) => {
      // The browser restores defaultValue after dispatching the cancelable reset event.
      clearTimeout(resetTimer);
      resetTimer = setTimeout(() => {
        if (!event.defaultPrevented && inputRef.current === input && input) setUncontrolledValue(input.value);
      });
    };
    form?.addEventListener("reset", onReset);
    return () => {
      clearTimeout(resetTimer);
      form?.removeEventListener("reset", onReset);
    };
  });
  if (value === null || (controlled && defaultValue !== undefined)) {
    throw new Error("TextArea: use either a non-null controlled value or defaultValue, not both.");
  }
  if (controlled && !onChange && !props.readOnly && !props.disabled) {
    throw new Error("TextArea requires onChange, readOnly or disabled for a controlled value.");
  }
  const characterCounter = String(controlled ? value : uncontrolledValue).length;
  // No hint/error/counter to show — drop the container entirely rather than
  // leaving an empty row under the field.
  const hasInformation = !!error || !!explanation || !!maxLength;

  return (
    <div
      className={`${styles.input} ${props.disabled ? styles.disabled : ""} ${!props.disabled && error ? styles.error : ""}`}
    >
      <label className={styles.label} htmlFor={id}>
        {required ? `${label} *` : label}
      </label>

      <textarea
        {...props}
        ref={inputRef}
        id={id}
        value={value}
        defaultValue={defaultValue}
        maxLength={maxLength}
        required={required}
        onChange={(event) => {
          if (!controlled) setUncontrolledValue(event.currentTarget.value);
          onChange?.(event);
        }}
      />

      {hasInformation && (
        <span className={styles.information}>
          <span className={styles.hint}>{error || explanation || null}</span>
          <span className={styles.maxLength}>{maxLength && `${characterCounter} / ${maxLength}`}</span>
        </span>
      )}
    </div>
  );
}
