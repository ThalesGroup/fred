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

import { ComponentPropsWithRef, useId } from "react";
import styles from "./TextArea.module.scss";

export interface TextAreaProps extends ComponentPropsWithRef<"textarea"> {
  label: string;
  /** What the field is for, shown between the label and the field. Use it for a
   *  sentence or more: `explanation` is a one-line hint and gets cut off. */
  description?: string;
  explanation?: string;
  error?: string;
}

export default function TextArea({
  label,
  description,
  explanation,
  error,
  maxLength,
  value,
  required,
  "aria-describedby": callerDescribedBy,
  "aria-invalid": callerInvalid,
  ...props
}: TextAreaProps) {
  const id = useId();
  const descriptionId = useId();
  const hintId = useId();
  const hint = error || explanation;
  const describedBy =
    [callerDescribedBy, description && descriptionId, hint && hintId].filter(Boolean).join(" ") || undefined;
  const characterCounter = String(value).length;
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

      {description && (
        <span id={descriptionId} className={styles.description}>
          {description}
        </span>
      )}

      <textarea
        id={id}
        value={value}
        maxLength={maxLength}
        required={required}
        aria-describedby={describedBy}
        aria-invalid={error ? true : callerInvalid}
        {...props}
      />

      {hasInformation && (
        <span className={styles.information}>
          <span className={styles.hint} id={hint ? hintId : undefined}>
            {hint || null}
          </span>
          <span className={styles.maxLength}>{maxLength && `${characterCounter} / ${maxLength}`}</span>
        </span>
      )}
    </div>
  );
}
