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

import { ReactNode } from "react";
import Icon from "@shared/atoms/Icon/Icon";
import styles from "./Chip.module.css";

export interface ChipProps {
  /** Primary label; truncates with an ellipsis when it overflows. */
  label: string;
  /** Full text for the title tooltip when the label is truncated. Defaults to `label`. */
  title?: string;
  /** Muted secondary line under the label (e.g. a file status). */
  secondary?: string;
  /**
   * Leading visual. A bare `Icon` inherits the chip's muted (and tone) color;
   * a self-styled badge sets its own color and overrides it.
   */
  leading?: ReactNode;
  /** Extra content shown just before the remove button (e.g. a task indicator). */
  trailing?: ReactNode;
  /** When provided, renders a trailing remove (close) affordance. */
  onRemove?: () => void;
  removeAriaLabel?: string;
  /** Semantic tone. "error" flips the container to the error-container role. */
  tone?: "default" | "error";
}

/**
 * Removable input chip (M3): a compact pill with an optional leading visual, a
 * truncating label, an optional secondary line, optional trailing content and
 * an optional remove button. The shared surface behind the composer's
 * attachment and context-prompt chips so both read as one component.
 */
export default function Chip({
  label,
  title,
  secondary,
  leading,
  trailing,
  onRemove,
  removeAriaLabel,
  tone = "default",
}: ChipProps) {
  return (
    <span className={styles.chip} data-tone={tone}>
      {leading && (
        <span className={styles.leading} aria-hidden>
          {leading}
        </span>
      )}
      <span className={styles.text}>
        <span className={styles.label} title={title ?? label}>
          {label}
        </span>
        {secondary != null && <span className={styles.secondary}>{secondary}</span>}
      </span>
      {trailing}
      {onRemove && (
        <button type="button" className={styles.remove} onClick={onRemove} aria-label={removeAriaLabel}>
          <Icon category="outlined" type="close" />
        </button>
      )}
    </span>
  );
}
