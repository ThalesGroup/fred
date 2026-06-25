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

import Icon from "@shared/atoms/Icon/Icon.tsx";
import styles from "./Stepper.module.css";

interface StepperProps {
  /** Ordered step labels. */
  steps: string[];
  /** Zero-based index of the current step. */
  active: number;
}

/** Linear step indicator for multi-step flows (wizards). Design-tokens only. */
export default function Stepper({ steps, active }: StepperProps) {
  return (
    <ol className={styles.stepper}>
      {steps.map((label, index) => {
        const state = index < active ? "done" : index === active ? "active" : "upcoming";
        return (
          <li
            key={label}
            className={styles.step}
            data-state={state}
            aria-current={index === active ? "step" : undefined}
          >
            <span className={styles.marker} aria-hidden="true">
              {index < active ? <Icon category="outlined" type="check_circle" filled /> : index + 1}
            </span>
            <span className={styles.label}>{label}</span>
            {index < steps.length - 1 && <span className={styles.connector} aria-hidden="true" />}
          </li>
        );
      })}
    </ol>
  );
}
