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

import styles from "./BetaBadge.module.css";

interface BetaBadgeProps {
  label?: string;
}

/** Marks a feature still open to change — pair with `Tooltip` at the call
 *  site to explain why, since this atom carries no feature-specific text. */
export function BetaBadge({ label = "Beta" }: BetaBadgeProps) {
  return (
    <span className={styles.badge} aria-label={label}>
      <span className="material-symbols-outlined" aria-hidden>
        science
      </span>
      <span className={styles.label}>{label}</span>
    </span>
  );
}
