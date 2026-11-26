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
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import styles from "./FilterChips.module.scss";

export interface FilterChipsOption<T extends string = string> {
  id: T;
  label: string;
  /** Shown right after the label (e.g. a per-category prompt count). */
  count?: number;
  /** Says what the chip shows when the label alone is not enough. */
  tooltip?: string;
}

export interface FilterChipsProps<T extends string = string> {
  options: FilterChipsOption<T>[];
  value: T | null;
  onChange: (value: T | null) => void;
  /** Label for the "All" chip. When undefined, no "All" chip is rendered. */
  allLabel?: string;
  /** Tooltip of the "All" chip, like an option's `tooltip`. */
  allTooltip?: string;
  /** Maximum chips shown before a "show more" toggle appears. */
  maxVisible?: number;
  /** Called with the hidden count to produce the "show more" label. */
  showMoreLabel?: (hiddenCount: number) => string;
  showLessLabel?: string;
  /** Names the chip group for assistive technologies. */
  "aria-label"?: string;
}

export default function FilterChips<T extends string = string>({
  options,
  value,
  onChange,
  allLabel,
  allTooltip,
  maxVisible,
  showMoreLabel,
  showLessLabel = "−",
  "aria-label": ariaLabel,
}: FilterChipsProps<T>) {
  const [expanded, setExpanded] = useState(false);

  if (options.length === 0) return null;

  const hasMore = maxVisible !== undefined && options.length > maxVisible;
  const visible = hasMore && !expanded ? options.slice(0, maxVisible) : options;
  const hiddenCount = hasMore ? options.length - maxVisible! : 0;

  const renderChip = (key: string, active: boolean, onClick: () => void, opt: Omit<FilterChipsOption, "id">) => {
    const chip = (
      <button
        key={key}
        type="button"
        className={styles.chip}
        data-active={active}
        aria-pressed={active}
        onClick={onClick}
      >
        {opt.label}
        {opt.count !== undefined && <span className={styles.count}>{opt.count}</span>}
      </button>
    );
    return opt.tooltip ? (
      // As `content`, a sentence wraps into short lines instead of one long one.
      <Tooltip key={key} content={opt.tooltip}>
        {chip}
      </Tooltip>
    ) : (
      chip
    );
  };

  return (
    <div className={styles.chips} role="group" aria-label={ariaLabel}>
      {allLabel !== undefined &&
        renderChip("__all", value === null, () => onChange(null), { label: allLabel, tooltip: allTooltip })}
      {visible.map((opt) =>
        renderChip(opt.id, value === opt.id, () => onChange(value === opt.id ? null : opt.id), opt),
      )}
      {hasMore && (
        <button type="button" className={styles.chipMore} onClick={() => setExpanded((e) => !e)}>
          {expanded ? showLessLabel : showMoreLabel ? showMoreLabel(hiddenCount) : `+${hiddenCount}`}
        </button>
      )}
    </div>
  );
}
