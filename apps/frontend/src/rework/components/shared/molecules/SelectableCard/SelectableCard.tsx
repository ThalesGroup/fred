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

import { MaterialIcon } from "../../atoms/Icon/Icon.tsx";
import type { MaterialIconType } from "../../utils/Type.ts";
import styles from "./SelectableCard.module.css";

export interface SelectableCardProps {
  /** Omit when picking a card acts at once rather than marking a choice: no pressed state is announced. */
  selected?: boolean;
  title: string;
  description: string;
  onSelect: () => void;
  disabled?: boolean;
  /** Decorative Material Symbols icon shown before the text (package-safe: no custom icons). */
  icon?: MaterialIconType;
}

/** A "pick one of N" card (radio-like). Design-tokens only. */
export default function SelectableCard({
  selected,
  title,
  description,
  onSelect,
  disabled,
  icon,
}: SelectableCardProps) {
  const text = (
    <>
      <span className={styles.title}>{title}</span>
      <span className={styles.description}>{description}</span>
    </>
  );
  return (
    <button
      type="button"
      className={styles.card}
      data-selected={selected ?? false}
      aria-pressed={selected}
      disabled={disabled}
      onClick={onSelect}
    >
      {icon ? (
        <span className={styles.withIcon}>
          <span className={styles.icon} aria-hidden="true">
            <MaterialIcon type={icon} />
          </span>
          <span className={styles.text}>{text}</span>
        </span>
      ) : (
        text
      )}
    </button>
  );
}
