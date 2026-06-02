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

import { useState } from "react";
import styles from "./FilterChips.module.scss";

export interface FilterChipsOption<T extends string = string> {
  id: T;
  label: string;
}

export interface FilterChipsProps<T extends string = string> {
  options: FilterChipsOption<T>[];
  value: T | null;
  onChange: (value: T | null) => void;
  /** Label for the "All" chip. When undefined, no "All" chip is rendered. */
  allLabel?: string;
  /** Maximum chips shown before a "show more" toggle appears. */
  maxVisible?: number;
  /** Called with the hidden count to produce the "show more" label. */
  showMoreLabel?: (hiddenCount: number) => string;
  showLessLabel?: string;
}

export default function FilterChips<T extends string = string>({
  options,
  value,
  onChange,
  allLabel,
  maxVisible,
  showMoreLabel,
  showLessLabel = "−",
}: FilterChipsProps<T>) {
  const [expanded, setExpanded] = useState(false);

  if (options.length === 0) return null;

  const hasMore = maxVisible !== undefined && options.length > maxVisible;
  const visible = hasMore && !expanded ? options.slice(0, maxVisible) : options;
  const hiddenCount = hasMore ? options.length - maxVisible! : 0;

  return (
    <div className={styles.chips} role="group">
      {allLabel !== undefined && (
        <button
          type="button"
          className={styles.chip}
          data-active={value === null}
          aria-pressed={value === null}
          onClick={() => onChange(null)}
        >
          {allLabel}
        </button>
      )}
      {visible.map((opt) => (
        <button
          key={opt.id}
          type="button"
          className={styles.chip}
          data-active={value === opt.id}
          aria-pressed={value === opt.id}
          onClick={() => onChange(value === opt.id ? null : opt.id)}
        >
          {opt.label}
        </button>
      ))}
      {hasMore && (
        <button type="button" className={styles.chipMore} onClick={() => setExpanded((e) => !e)}>
          {expanded ? showLessLabel : showMoreLabel ? showMoreLabel(hiddenCount) : `+${hiddenCount}`}
        </button>
      )}
    </div>
  );
}
