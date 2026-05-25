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

import styles from "./NumberedChip.module.css";

interface NumberedChipProps {
  value: number;
  onClick?: () => void;
  /** Accessible label for screen readers. Defaults to "Source {value}". */
  label?: string;
}

export function NumberedChip({ value, onClick, label }: NumberedChipProps) {
  const ariaLabel = label ?? `Source ${value}`;

  if (onClick) {
    return (
      <button
        type="button"
        className={`${styles.chip} ${styles.clickable}`}
        onClick={onClick}
        aria-label={ariaLabel}
      >
        {value}
      </button>
    );
  }

  return (
    <span className={styles.chip} aria-label={ariaLabel}>
      {value}
    </span>
  );
}
