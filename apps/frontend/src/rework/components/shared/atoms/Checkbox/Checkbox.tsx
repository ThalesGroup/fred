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

import styles from "./Checkbox.module.scss";
import { ComponentPropsWithRef, useEffect, useRef } from "react";

interface CheckboxProps extends ComponentPropsWithRef<"input"> {
  /** Neither checked nor unchecked — e.g. a "select all" header checkbox when
   *  only some rows on the page are selected. */
  indeterminate?: boolean;
}

export default function Checkbox({ ref: externalRef, indeterminate = false, className, ...rest }: CheckboxProps) {
  const containerClasses = [styles["checkbox-container"]];
  if (className) containerClasses.push(className);

  // The visual/ARIA state above is enough for the custom `.box` and modern
  // screen readers, but the native `.indeterminate` DOM property (unlike
  // `.checked`, it has no HTML attribute) is what the rest of this codebase's
  // other checkboxes set (e.g. DocumentLibraryScopePicker) and what anything
  // reading the input directly — assistive tech, tests, autofill — expects.
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (inputRef.current) inputRef.current.indeterminate = indeterminate;
  }, [indeterminate]);

  return (
    <label className={containerClasses.join(" ")}>
      <input
        type="checkbox"
        ref={(el) => {
          inputRef.current = el;
          if (typeof externalRef === "function") externalRef(el);
          else if (externalRef) externalRef.current = el;
        }}
        className={styles["native-input"]}
        aria-checked={indeterminate ? "mixed" : undefined}
        data-indeterminate={indeterminate || undefined}
        {...rest}
      />
      <div className={styles["box"]}>
        <div className={styles["state-layer"]}>
          {indeterminate ? (
            <svg className={styles["mark"]} viewBox="0 0 16 16" aria-hidden="true">
              <line x1="4" y1="8" x2="12" y2="8" />
            </svg>
          ) : (
            <svg className={styles["mark"]} viewBox="0 0 16 16" aria-hidden="true">
              <polyline points="3.5,8.5 6.5,11.5 12.5,4.5" />
            </svg>
          )}
        </div>
      </div>
    </label>
  );
}
