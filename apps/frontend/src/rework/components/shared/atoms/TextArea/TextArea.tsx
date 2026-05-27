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
  explanation?: string;
  error?: string;
}

export default function TextArea({ label, explanation, error, maxLength, value, required, ...props }: TextAreaProps) {
  const id = useId();
  const characterCounter = String(value).length;

  return (
    <div
      className={`${styles.input} ${props.disabled ? styles.disabled : ""} ${!props.disabled && error ? styles.error : ""}`}
    >
      <label className={styles.label} htmlFor={id}>
        {required ? `${label} *` : label}
      </label>

      <textarea id={id} value={value} maxLength={maxLength} required={required} {...props} />

      <span className={styles.information}>
        <span className={styles.hint}>{error || explanation || null}</span>
        <span className={styles.maxLength}>{maxLength && `${characterCounter} / ${maxLength}`}</span>
      </span>
    </div>
  );
}
